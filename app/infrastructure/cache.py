"""Infrastructure: adapter Redis untuk port Cache.

Nilai disimpan sebagai JSON. TTL ditambah jitter (acak sampai 10%),
supaya key yang dibuat bersamaan tidak kedaluwarsa di detik yang sama (mengurangi cache stampede).

Lock (SET NX EX) mencegah stampede di key yang sama: saat cache kosong, hanya satu request yang query database,
yang lain menunggu. Lock hanya optimasi, bukan penjaga kebenaran data: kalau lock habis waktu atau bocor,
dampak terburuknya satu query database tambahan.
"""
import json
import random

from redis import Redis


class RedisCache:
    def __init__(self, redis: Redis, ttl: int):
        self.redis = redis
        self.ttl = ttl

    def get(self, key: str):
        value = self.redis.get(key)
        return None if value is None else json.loads(value)

    def set(self, key: str, value) -> None:
        jitter = random.randint(0, max(1, self.ttl // 10))
        self.redis.set(key, json.dumps(value), ex=self.ttl + jitter)

    def delete(self, *keys: str) -> None:
        if keys:
            self.redis.delete(*keys)

    def acquire_lock(self, key: str, ttl: int = 5) -> bool:
        """SET lock:<key> NX EX <ttl>: berhasil hanya untuk satu pemanggil. Lock hilang sendiri setelah ttl detik."""
        return bool(self.redis.set(f"lock:{key}", "1", nx=True, ex=ttl))

    def release_lock(self, key: str) -> None:
        self.redis.delete(f"lock:{key}")
