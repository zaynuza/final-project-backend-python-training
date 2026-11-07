"""API: middleware yang membungkus semua request.

Untuk setiap request:
1. request_id diambil dari header X-Request-ID, atau dibuat baru, lalu disimpan di contextvars
2. Waktu response diukur dan dicatat ke metrics Prometheus (route = pola path, bukan path asli)
3. Satu access log JSON: method, route, status, duration_ms (request_id ditempel otomatis oleh filter log)
4. Response membawa header X-Request-ID dan X-Process-Time
"""
import logging
import time
import uuid

from fastapi import Request

from app.infrastructure.logs import request_id_var
from app.infrastructure.metrics import HTTP_LATENCY, HTTP_REQUESTS

logger = logging.getLogger("app.access")


async def observe_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request_id_var.set(request_id)
    start = time.perf_counter()
    status = 500                                         # jika terjadi error yang tidak tertangani
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{(time.perf_counter() - start) * 1000:.1f}ms"
        return response
    finally:
        seconds = time.perf_counter() - start
        route = request.scope.get("route")
        path = route.path if route else "unknown"         # "/orders/{order_id}", bukan "/orders/7"
        HTTP_REQUESTS.labels(request.method, path, status).inc()
        HTTP_LATENCY.labels(request.method, path).observe(seconds)
        if path not in ("/metrics", "/health/live", "/health/ready"):
            logger.info("request selesai", extra={
                "method": request.method, "route": path, "status": status,
                "duration_ms": round(seconds * 1000, 1)})
