import sys
from dotenv import load_dotenv
load_dotenv()
import os
import logging
import redis
import json
import datetime
from sqlmodel import Session, select
from sqlalchemy import func, or_
from app.models.product import Product, ProductCreate
from typing import List, Optional
from urllib.parse import urlparse
from app.db import engine

from openai import OpenAI
client = OpenAI()

logger = logging.getLogger("product_crud")
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")


logger.setLevel(logging.INFO)
redis_client = redis.Redis.from_url(redis_url)

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
def search_by_problem_description(session: Session, description: str, limit: int = 5):
    """
    AI-powered semantic search using OpenAI embeddings.
    Users can describe their need in natural language.
    Understand discription and give the most equivalent product.
    Returns products most relevant to the description.
    Optimized for small datasets without heavy local models.
    """
    try:
        import numpy as np
        from openai import OpenAI
        from sklearn.metrics.pairwise import cosine_similarity

        # STEP 1 — Load OpenAI client (ensure OPENAI_API_KEY is in .env)
        client = OpenAI()

        # STEP 2 — Check Redis cache
        cache_key = f"ai_search:{description.lower()}"
        cached = cache_get(cache_key)
        if cached:
            return {"query": description, "results": cached}

        # STEP 3 — Load products
        products = session.exec(select(Product)).all()
        if not products:
            return {"query": description, "results": []}

        # STEP 4 — Create embeddings for products
        product_texts = [f"{p.name}. {p.description}. {p.tags}" for p in products]
        product_embeddings = []
        for text in product_texts:
            emb_resp = client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            product_embeddings.append(np.array(emb_resp.data[0].embedding, dtype=np.float32))
        product_embeddings = np.vstack(product_embeddings)

        # STEP 5 — Encode user query
        query_resp = client.embeddings.create(
            model="text-embedding-3-small",
            input=description
        )
        query_embedding = np.array(query_resp.data[0].embedding, dtype=np.float32).reshape(1, -1)

        # STEP 6 — Compute cosine similarity in-memory
        similarities = cosine_similarity(query_embedding, product_embeddings)[0]
        top_indices = similarities.argsort()[::-1][:limit]

        # STEP 7 — Return top-k products
        results = [products[i].dict() for i in top_indices]

        # STEP 8 — Cache results
        cache_set(cache_key, results, expire_seconds=300)

        return {"query": description, "results": results}

    except Exception as e:
        logger.error(f"AI search error: {e}")
        return {"query": description, "results": []}
