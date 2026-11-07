"""Infrastructure: rate limiter sliding window dengan Redis sorted set.

Setiap request dicatat waktunya (score = waktu). Yang dihitung adalah request dalam
`window` detik terakhir, jadi tidak ada celah di pergantian menit seperti fixed window.

Catatan: cek lalu catat dilakukan dalam dua langkah. Untuk traffic sangat tinggi,
gabungkan jadi satu Lua script supaya atomic.
"""
import math
import time
from dataclasses import dataclass
from uuid import uuid4

from redis import Redis


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int                  # detik sampai boleh mencoba lagi, 0 kalau allowed


class SlidingWindowRateLimiter:
    def __init__(self, redis: Redis, limit: int, window: int):
        self.redis = redis
        self.limit = limit
        self.window = window

    def hit(self, client_id: str, now: float | None = None) -> RateLimitResult:
        now = time.time() if now is None else now
        key = f"ratelimit:{client_id}"

        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, now - self.window)     # buang request yang sudah lewat window
        pipe.zcard(key)
        _, count = pipe.execute()

        if count >= self.limit:
            oldest = self.redis.zrange(key, 0, 0, withscores=True)[0][1]
            return RateLimitResult(False, self.limit, 0, max(1, math.ceil(oldest + self.window - now)))

        pipe = self.redis.pipeline()
        pipe.zadd(key, {uuid4().hex: now})
        pipe.expire(key, self.window)
        pipe.execute()
        return RateLimitResult(True, self.limit, self.limit - count - 1, 0)
