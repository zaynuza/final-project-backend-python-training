"""API: dependency rate limit per client (IP address).

Dipasang di router yang mahal diproses (orders, reports).
Setiap response diberi header X-RateLimit-Limit dan X-RateLimit-Remaining.
Lewat batas = 429 dengan header Retry-After (lihat api/errors.py).
"""
from fastapi import Depends, Request, Response

from app.api.dependencies import get_rate_limiter
from app.api.errors import RateLimited
from app.infrastructure.rate_limiter import SlidingWindowRateLimiter


def rate_limit(request: Request, response: Response,
               limiter: SlidingWindowRateLimiter = Depends(get_rate_limiter)) -> None:
    result = limiter.hit(request.client.host)
    if not result.allowed:
        raise RateLimited(result.limit, result.retry_after)
    response.headers["X-RateLimit-Limit"] = str(result.limit)
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)
