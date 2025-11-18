import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

# Database helpers
from database import db, create_document, get_documents

app = FastAPI(title="NutriTailor AI Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message")
    session_id: Optional[str] = Field(None, description="Conversation session id")
    context: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    timestamp: datetime


class OrderRequest(BaseModel):
    product_id: str
    quantity: int = Field(1, ge=1, le=20)
    email: Optional[str] = None


@app.get("/")
def read_root():
    return {"message": "NutriTailor AI Backend running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": [],
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            collections = db.list_collection_names()
            response["collections"] = collections
            response["connection_status"] = "Connected"
            response["database"] = "✅ Connected & Working"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    return response


# -------- Products (Ecommerce) --------
@app.get("/api/products")
def list_products() -> List[dict]:
    """Return a list of products. If empty, seed with a few defaults."""
    products = get_documents("product") if db else []
    if not products and db is not None:
        seed = [
            {
                "title": "Personalized Meal Plan",
                "description": "A 4-week tailored plan based on your goals and preferences.",
                "price": 49.0,
                "category": "plans",
                "in_stock": True,
                "image": "https://images.unsplash.com/photo-1543353071-087092ec393a?w=1200&q=80&auto=format&fit=crop",
            },
            {
                "title": "1:1 Nutrition Coaching (60 min)",
                "description": "Work directly with our AI-guided nutritionist and human expert.",
                "price": 89.0,
                "category": "coaching",
                "in_stock": True,
                "image": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=1200&q=80&auto=format&fit=crop",
            },
            {
                "title": "Grocery List Optimizer",
                "description": "Weekly optimized grocery list aligned to macros and budget.",
                "price": 15.0,
                "category": "tools",
                "in_stock": True,
                "image": "https://images.unsplash.com/photo-1511690656952-34342bb7c2f2?w=1200&q=80&auto=format&fit=crop",
            },
        ]
        for p in seed:
            create_document("product", p)
        products = get_documents("product")
    # Convert ObjectId to str
    for p in products:
        if "_id" in p:
            p["id"] = str(p.pop("_id"))
    return products


@app.post("/api/order")
def create_order(order: OrderRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    # verify product exists
    from bson import ObjectId

    try:
        product = db["product"].find_one({"_id": ObjectId(order.product_id)})
    except Exception:
        product = None

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    total = float(product.get("price", 0.0)) * order.quantity
    doc = {
        "product_id": order.product_id,
        "quantity": order.quantity,
        "email": order.email,
        "total": total,
        "status": "created",
    }
    oid = create_document("order", doc)
    return {"order_id": oid, "total": total, "status": "created"}


# -------- Chat (AI Nutritional Therapist) --------

def generate_nutrition_reply(user_text: str) -> str:
    text = user_text.lower()
    goals = []
    if any(k in text for k in ["weight loss", "lose weight", "fat loss"]):
        goals.append("weight loss")
    if any(k in text for k in ["muscle", "gain weight", "bulk"]):
        goals.append("muscle gain")
    if any(k in text for k in ["energy", "tired", "fatigue"]):
        goals.append("energy")
    if any(k in text for k in ["ibs", "gut", "bloat"]):
        goals.append("gut health")

    parts = [
        "Thanks for sharing. I'm your AI nutritional therapist.",
    ]
    if goals:
        parts.append(f"I detect goals around {', '.join(goals)}.")
    parts.append(
        "General guidance: focus on whole foods, 25–35g protein per meal, plenty of colorful veg, and hydrate."
    )
    if "breakfast" in text:
        parts.append(
            "For breakfast, try Greek yogurt with berries and nuts, or eggs with spinach and wholegrain toast."
        )
    if "vegan" in text:
        parts.append(
            "For a vegan approach, prioritize legumes, tofu/tempeh, whole grains, seeds, and B12-fortified foods."
        )
    if "meal plan" in text or "plan" in text:
        parts.append("I can also create a tailored 7‑day meal plan if you share preferences, allergies, and budget.")
    parts.append(
        "Would you like me to estimate your daily calorie target and macros based on age, height, weight, sex, activity?"
    )
    return " " .join(parts)


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    session_id = req.session_id or os.urandom(8).hex()
    reply = generate_nutrition_reply(req.message)

    if db is not None:
        # store both user and assistant messages
        create_document(
            "message",
            {
                "session_id": session_id,
                "role": "user",
                "content": req.message,
            },
        )
        create_document(
            "message",
            {
                "session_id": session_id,
                "role": "assistant",
                "content": reply,
            },
        )

    return ChatResponse(reply=reply, session_id=session_id, timestamp=datetime.now(timezone.utc))


@app.get("/api/messages")
def get_messages(session_id: str, limit: int = 50):
    if db is None:
        return []
    msgs = get_documents("message", {"session_id": session_id}, limit)
    for m in msgs:
        if "_id" in m:
            m["id"] = str(m.pop("_id"))
    return msgs


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
