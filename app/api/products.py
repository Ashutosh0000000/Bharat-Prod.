
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
router = APIRouter()  # <-- Add this 

REDIS_URL = os.getenv("REDIS_URL")

if not REDIS_URL:
    print("❌ ERROR: REDIS_URL is not set in environment variables!")
    redis_client = None
else:
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)


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

@router.get("/products/mode/{mode_name}", response_model=PaginatedProductResponse)
def get_products_by_mode_endpoint(
    mode_name: str,
    skip: int = 0,
    limit: int = 100,
    session: Session = Depends(get_session)
):
    return product_crud.get_products_by_mode(session, mode_name, skip=skip, limit=limit)


@router.get("/products/trending", response_model=List[ProductRead])
def get_trending_products(response: Response, session: Session = Depends(get_session)):
    cache_key = "trending_products"

    # Use safe redis getter
    cached_data = None
    try:
        cached_data = safe_redis_get(cache_key)
    except Exception:
        cached_data = None

    if cached_data:
        try:
            products = json.loads(cached_data)
            response.headers["X-Cache"] = "HIT"
            return products
        except json.JSONDecodeError:
            # corrupted cache -> fall through to DB
            logger.warning("Trending cache corrupted, fetching DB results.")

    # Fallback: read from DB
    try:
        products = product_crud.get_top_products_by_purchase_count(session, limit=10)
        products_json = [p.dict() for p in products]
    except Exception as e:
        logger.error(f"Error fetching trending products from DB: {e}")
        # Return empty list instead of raising 500
        return []

    # Try caching but ignore errors
    try:
        safe_redis_setex(cache_key, 300, json.dumps(products_json, default=default_json_serializer))
    except Exception:
        pass

    response.headers["X-Cache"] = "MISS"
    return products_json

@router.get("/products/ai-search", response_model=List[ProductRead])
def ai_search(
    description: str = Query(..., description="Describe your need/problem"),
    session: Session = Depends(get_session)
):
    description = description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="Description cannot be empty")

    try:
        result = product_crud.search_by_problem_description(session, description)

        # Normalize output to list of dicts that match ProductRead
        if not result:
            return []

        # If product objects (SQLModel), convert to dicts
        if isinstance(result, list) and result and hasattr(result[0], "dict"):
            return [r.dict() for r in result]

        if isinstance(result, list):
            return result

        if isinstance(result, dict):
            return result.get("results", [])

        return []
    except Exception as e:
        logger.exception(f"AI search error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

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
