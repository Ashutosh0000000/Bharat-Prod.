
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from app.crud.product_crud import default_json_serializer
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlmodel import Session
from typing import List, Optional
from app.db import get_session
from app.models.product import (
    ProductRead,
    ProductCreate,
    ProductUpdate,
    PaginatedProductResponse
)
from app.crud import product_crud
import redis
import json

router = APIRouter()

# Initialize Redis
redis_client = redis.Redis.from_url("redis://redis:6379/0")

# ----------------------------------
# Create a new product
# ----------------------------------
@router.post("/products", response_model=ProductRead)
def create_product(product: ProductCreate, session: Session = Depends(get_session)):
    return product_crud.create_product(product, session)

# ----------------------------------
# Read/search products with filters
# ----------------------------------
@router.get("/products", response_model=PaginatedProductResponse)
def read_products(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = Query(None, description="Search product name"),
    category: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    sort_by: Optional[str] = Query(None, regex="^(price|created_at|name)$"),
    order: Optional[str] = Query("asc", regex="^(asc|desc)$"),
    session: Session = Depends(get_session)
):
    return product_crud.get_products(
        session=session,
        skip=skip,
        limit=limit,
        search=search,
        category=category,
        region=region,
        min_price=min_price,
        max_price=max_price,
        sort_by=sort_by,
        order=order,
    )

# ----------------------------------
# STATIC ROUTES BEFORE DYNAMIC ONES
@router.get("/products/trending", response_model=List[ProductRead])
def get_trending_products(response: Response, session: Session = Depends(get_session)):
    cache_key = "trending_products"
    cached_data = redis_client.get(cache_key)
    if cached_data:
        try:
            products = json.loads(cached_data)
            response.headers["X-Cache"] = "HIT"
            return products
        except json.JSONDecodeError:
            pass  # fallback to DB query

    products = product_crud.get_top_products_by_purchase_count(session, limit=10)
    products_json = [p.dict() for p in products]

    redis_client.setex(cache_key, 300, json.dumps(products_json, default=default_json_serializer))
    response.headers["X-Cache"] = "MISS"
    return products_json


@router.get("/products/{product_id}/suggestions", response_model=List[ProductRead])
def get_suggested_products(
    product_id: int,
    session: Session = Depends(get_session)
):
    product = product_crud.get_product(session, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    suggestions = product_crud.suggest_products(
        session=session,
        product_id=product_id,
        price_range=500,
        limit=5
    )

    return suggestions  # Empty list if none found


@router.get("/products/{product_id}", response_model=ProductRead)
def read_product(product_id: int, session: Session = Depends(get_session)):
    product = product_crud.get_product(session, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

# Update a product by ID
@router.put("/products/{product_id}", response_model=ProductRead)
def update_product(product_id: int, product_update: ProductUpdate, session: Session = Depends(get_session)):
    product_data = product_update.dict(exclude_unset=True)
    updated_product = product_crud.update_product(session, product_id, product_data)
    if not updated_product:
        raise HTTPException(status_code=404, detail="Product not found")
    return updated_product

# Delete a product by ID
@router.delete("/products/{product_id}")
def delete_product(product_id: int, session: Session = Depends(get_session)):
    success = product_crud.delete_product(session, product_id)
    if not success:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"deleted": True}
