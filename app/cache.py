# app/cache.py

import redis
import os
import json

REDIS_HOST = os.getenv("REDIS_HOST", "redis")  # "redis" is the Docker service name
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

redis_client = redis.Redis(
    host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True
)

def cache_set(key: str, value: dict, expire_seconds: int = 300):
    redis_client.set(key, json.dumps(value), ex=expire_seconds)

def cache_get(key: str):
    data = redis_client.get(key)
    if data:
        return json.loads(data)
    return None
