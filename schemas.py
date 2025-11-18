"""
Database Schemas for NutriTailor AI

Each Pydantic model represents a MongoDB collection. The collection name is the
lowercased class name.
"""

from pydantic import BaseModel, Field
from typing import Optional


class Product(BaseModel):
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in USD")
    category: str = Field(..., description="Category e.g., plans, coaching, tools")
    in_stock: bool = Field(True)
    image: Optional[str] = Field(None, description="Image URL")


class Order(BaseModel):
    product_id: str
    quantity: int = Field(1, ge=1, le=20)
    email: Optional[str] = None
    total: Optional[float] = None
    status: str = Field("created")


class Message(BaseModel):
    session_id: str
    role: str = Field(..., description="user | assistant")
    content: str
