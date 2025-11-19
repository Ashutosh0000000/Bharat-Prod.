
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from sqlmodel import SQLModel, Field
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, confloat
from pydantic import field_validator
class ProductBase(SQLModel):
    name: str
    description: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None  # e.g. smartphones, accessories
    price: float
    region: Optional[str] = None  # e.g. India, Global, or city-specific
    tags: Optional[str] = None
    image_url: Optional[str] = None
    rating: Optional[confloat(ge=1.0, le=5.0)] = None  # Rating between 1.0 and 5.0
    stock: int = 0
    warranty: Optional[str] = None         # e.g. "12 months" for electronics
    size: Optional[str] = None             # For fashion items
    material: Optional[str] = None         # Fabric/material
    expiry_date: Optional[date] = None     # For FMCG/grocery — must be in YYYY-MM-DD format
    pack_size: Optional[str] = None        # e.g. "500g", "1kg"
    views: int = 0                         # Track popularity
    purchase_count: int = 0

@field_validator("image_url")
def validate_image_url(cls, v):
    if v:
        valid_extensions = (".jpg", ".jpeg", ".png", ".webp")
        if not any(v.lower().endswith(ext) for ext in valid_extensions):
            raise ValueError("Image URL must end with .jpg, .jpeg, .png, or .webp")
    return v

class Product(ProductBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ProductCreate(ProductBase):
    pass


class ProductRead(ProductBase):
    id: int
    created_at: datetime


class PaginatedProductResponse(BaseModel):
    total: int
    items: List[ProductRead]


class ProductUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    region: Optional[str] = None
    tags: Optional[str] = None
    image_url: Optional[str] = None
    rating: Optional[confloat(ge=1.0, le=5.0)] = None
    stock: Optional[int] = None
    warranty: Optional[str] = None
    size: Optional[str] = None
    material: Optional[str] = None
    expiry_date: Optional[date] = None
    pack_size: Optional[str] = None
    views: Optional[int] = None
    purchase_count: Optional[int] = None
