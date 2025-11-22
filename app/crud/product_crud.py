import sys
from dotenv import load_dotenv
load_dotenv()
import os
import logging
import redis
import json
import datetime
from sqlmodel import Session, select
from fastapi import HTTPException
from sqlalchemy import func, or_
from app.models.product import Product, ProductCreate
from typing import List, Optional
from urllib.parse import urlparse
from app.db import engine

from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

logger = logging.getLogger("product_crud")
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

logger.setLevel(logging.INFO)

parsed_url = urlparse(redis_url)
REDIS_HOST = parsed_url.hostname
REDIS_PORT = parsed_url.port or 6379
REDIS_DB = int(parsed_url.path.lstrip("/")) if parsed_url.path else 0
REDIS_PASSWORD = parsed_url.password

try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True
    )
    redis_client.ping()
except Exception as e:
    logger.warning(f"Could not connect to Redis: {e}")
    redis_client = None


CACHE_EXPIRE = 300

def default_json_serializer(obj):
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

def cache_set(key: str, value: dict, expire_seconds: int = CACHE_EXPIRE):
    if not redis_client:
        return
    try:
        redis_client.set(key, json.dumps(value, default=default_json_serializer), ex=expire_seconds)
    except Exception as e:
        logger.warning(f"Redis cache set error for key {key}: {e}")

def cache_get(key: str):
    if not redis_client:
        return None
    try:
        data = redis_client.get(key)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning(f"Redis cache get error for key {key}: {e}")
    return None

def cache_delete(pattern: str):
    if not redis_client:
        return
    try:
        for key in redis_client.scan_iter(pattern):
            redis_client.delete(key)
    except Exception as e:
        logger.warning(f"Redis cache delete error for pattern {pattern}: {e}")

def create_product(product_create: ProductCreate, db: Session) -> Product:
    try:
        product_data = {
            key: value for key, value in product_create.dict().items()
            if hasattr(Product, key) and value is not None
        }
        product = Product(**product_data)
        db.add(product)
        db.commit()
        db.refresh(product)

        cache_delete("products_list*")
        cache_delete("trending_products")

        return product
    except Exception as e:
        logger.error(f"Error creating product: {e}")
        raise

def get_product(session: Session, product_id: int) -> Optional[Product]:
    try:
        return session.get(Product, product_id)
    except Exception as e:
        logger.error(f"Error fetching product {product_id}: {e}")
        return None

def get_products(
    session: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    category: Optional[str] = None,
    region: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort_by: Optional[str] = None,
    order: Optional[str] = "asc"
) -> dict:
    try:
        cache_key = f"products_list:{skip}:{limit}:{search}:{category}:{region}:{min_price}:{max_price}:{sort_by}:{order}"
        cached = cache_get(cache_key)
        if cached:
            return cached

        filters = []
        if search:
            term = f"%{search.lower()}%"
            filters.append(or_(
                func.lower(Product.name).like(term),
                func.lower(Product.brand).like(term),
                func.lower(Product.description).like(term),
                func.lower(Product.tags).like(term),
            ))
        if category:
            filters.append(Product.category == category)
        if region:
            filters.append(Product.region == region)
        if min_price is not None:
            filters.append(Product.price >= min_price)
        if max_price is not None:
            filters.append(Product.price <= max_price)

        statement = select(Product).where(*filters)

        total = session.exec(
            statement.with_only_columns(func.count()).order_by(None)
        ).first() or 0

        if sort_by in ["price", "created_at", "name"]:
            sort_col = getattr(Product, sort_by)
            statement = statement.order_by(sort_col.desc() if order == "desc" else sort_col.asc())
        else:
            statement = statement.order_by(Product.id.asc())

        statement = statement.offset(skip).limit(limit)

        products = session.exec(statement).all()

        result = {
            "total": total,
            "items": [product.dict() for product in products]
        }

        cache_set(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"Error fetching products: {e}")
        return {"total": 0, "items": []}

def update_product(session: Session, product_id: int, product_data: dict) -> Optional[Product]:
    try:
        product = session.get(Product, product_id)
        if not product:
            return None

        for key, value in product_data.items():
            if hasattr(Product, key):
                setattr(product, key, value)

        session.add(product)
        session.commit()
        session.refresh(product)

        cache_delete("products_list*")
        cache_delete("trending_products")

        return product
    except Exception as e:
        logger.error(f"Error updating product {product_id}: {e}")
        return None

def delete_product(session: Session, product_id: int) -> bool:
    try:
        product = session.get(Product, product_id)
        if not product:
            return False

        session.delete(product)
        session.commit()

        cache_delete("products_list*")
        cache_delete("trending_products")

        return True
    except Exception as e:
        logger.error(f"Error deleting product {product_id}: {e}")
        return False

def get_top_products_by_purchase_count(session: Session, limit: int = 10) -> List[Product]:
    try:
        statement = select(Product).order_by(Product.purchase_count.desc()).limit(limit)
        return session.exec(statement).all()
    except Exception as e:
        logger.error(f"Error fetching top products by purchase count: {e}")
        return []

def suggest_products(
    session: Session,
    product_id: int,
    price_range: float = 500,
    limit: int = 5
) -> List[Product]:
    try:
        product = session.get(Product, product_id)
        if not product or product.category is None or product.price is None:
            return []

        min_price = max(0, product.price - price_range)
        max_price = product.price + price_range

        statement = (
            select(Product)
            .where(Product.category == product.category)
            .where(Product.id != product_id)
            .where(Product.price.between(min_price, max_price))
            .order_by(Product.rating.desc())
            .limit(limit)
        )

        return session.exec(statement).all()
    except Exception as e:
        logger.error(f"Error in suggest_products: {e}")
        return []

def search_by_problem_description(session, problem: str):
    import re
    from sqlalchemy import or_

    problem = problem.lower().strip()
    if not problem:
        return []

    # -----------------------------
    # Redis cache
    # -----------------------------
    cache_key = f"smart_search:{problem}"
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    # -----------------------------
    # Extract words
    # -----------------------------
    words = re.findall(r"\w+", problem)
    words = [w for w in words if len(w) > 2]

    # -----------------------------
    # Synonyms expansion
    # -----------------------------
    synonyms = {
        "earbuds": ["earphones", "tws", "headphones", "audio", "bluetooth"],
        "earphones": ["earbuds", "tws"],
        "headphones": ["earbuds", "audio"],

        "dirty": ["clean", "wash", "dust", "stain"],
        "clean": ["wash", "wipe", "sanitize"],

        "battery": ["charge", "power", "backup"],
        "charging": ["battery", "power"],

        "phone": ["mobile", "smartphone", "android"],
        "mobile": ["phone", "device"],

        "mosquito": ["insect", "repellent", "pest"],
        "insect": ["mosquito", "bug"],

        "mixie": ["mixer", "grinder"],
        "mixer": ["blender", "grinder"],

        "shoes": ["footwear", "sneakers"],
        "shirt": ["tshirt", "clothes", "top"],

        "trimmer": ["shaver", "grooming"],
    }

    expanded = set(words)
    for w in words:
        if w in synonyms:
            expanded.update(synonyms[w])

    expanded = list(expanded)

    # -----------------------------
    # Build SQL OR search
    # -----------------------------
    clauses = []
    for w in expanded:
        clauses.append(
            or_(
                Product.name.ilike(f"%{w}%"),
                Product.description.ilike(f"%{w}%"),
                Product.category.ilike(f"%{w}%"),
                Product.tags.ilike(f"%{w}%")
            )
        )

    query = select(Product).where(or_(*clauses))
    products = session.exec(query).all()

    # -----------------------------
    # Scoring
    # -----------------------------
    ranked = []
    for p in products:
        score = 0
        full_text = f"{p.name} {p.description} {p.tags}".lower()

        matched = [w for w in expanded if w in full_text]
        score += len(matched) * 2

        if getattr(p, "rating", 0):
            score += float(p.rating)

        if getattr(p, "stock", 0) > 0:
            score += 1

        ranked.append({
            "product": p,
            "score": score,
            "matched": matched
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)

    # -----------------------------
    # Format output
    # -----------------------------
    result = [
        {
            "id": p["product"].id,
            "name": p["product"].name,
            "price": p["product"].price,
            "rating": p["product"].rating,
            "stock": p["product"].stock,
            "image_url": p["product"].image_url,
            "description": p["product"].description,
            "reason": f"Matched: {', '.join(p['matched'])}, Score: {p['score']}"
        }
        for p in ranked
    ]

    # Cache
    redis_client.set(cache_key, json.dumps(result), ex=300)
    return result
