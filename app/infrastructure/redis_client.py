"""Infrastructure: koneksi Redis untuk cache dan rate limiter (satu client untuk seluruh aplikasi)."""
from functools import lru_cache

from redis import Redis

from app.infrastructure.config import get_settings


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)
