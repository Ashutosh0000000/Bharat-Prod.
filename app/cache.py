# app/cache.py

import redis
import os
import json
import logging

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")  # Docker service name
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

redis_client = None

try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True
    )
except Exception as e:
    logger.error(f"Failed to connect Redis: {e}")

CACHE_EXPIRE = 300


# ------------------------------------------------------------------
# SAFE REDIS HELPERS (No 500 Errors Even If Redis Fails)
# ------------------------------------------------------------------

def safe_redis_get(key: str):
    """Return None on any redis problem instead of crashing."""
    if not redis_client:
        return None

    try:
        data = redis_client.get(key)
        if data:
            return json.loads(data)
        return None

    except redis.exceptions.RedisError as e:
        logger.warning(f"Redis GET error for key={key}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected Redis GET error: {e}")
        return None


def safe_redis_set(key: str, value: dict, ex: int = CACHE_EXPIRE):
    """Return False instead of crashing."""
    if not redis_client:
        return False

    try:
        redis_client.set(key, json.dumps(value), ex=ex)
        return True
    except redis.exceptions.RedisError as e:
        logger.warning(f"Redis SET error for key={key}: {e}")
        return False
    except Exception as e:
        logger.warning(f"Unexpected Redis SET error: {e}")
        return False


def safe_redis_setex(key: str, ttl: int, value: dict):
    """Use setex but safe."""
    if not redis_client:
        return False

    try:
        redis_client.setex(key, ttl, json.dumps(value))
        return True
    except Exception as e:
        logger.warning(f"Redis SETEX error for key={key}: {e}")
        return False


# ------------------------------------------------------------------
# Backwards compatible functions
# ------------------------------------------------------------------

def cache_set(key: str, value: dict, expire_seconds: int = 300):
    return safe_redis_set(key, value, expire_seconds)

def cache_get(key: str):
    return safe_redis_get(key)
