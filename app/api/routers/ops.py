"""API: endpoint operasional, dipanggil Kubernetes, load balancer, dan Prometheus.

GET /health/live   : proses berjalan. Tidak mengecek dependency (gagal = container di-restart)
GET /health/ready  : database, Redis, dan RabbitMQ bisa dihubungi (503 = berhenti dikirimi traffic)
GET /metrics       : metrics format Prometheus
"""
from collections.abc import Callable

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.dependencies import get_health_checks
from app.api.schemas import ReadinessOut

router = APIRouter(tags=["ops"])


@router.get("/health/live", summary="Liveness check")
def live():
    return {"status": "ok"}


@router.get("/health/ready", response_model=ReadinessOut, summary="Readiness check",
            responses={503: {"model": ReadinessOut, "description": "Ada dependency yang tidak bisa dihubungi"}})
def ready(checks: dict[str, Callable[[], None]] = Depends(get_health_checks)):
    results = {}
    for name, check in checks.items():
        try:
            check()
            results[name] = "ok"
        except Exception as exc:
            results[name] = f"down: {type(exc).__name__}"
    healthy = all(result == "ok" for result in results.values())
    return JSONResponse(status_code=200 if healthy else 503,
                        content={"status": "ready" if healthy else "not_ready", "checks": results})


@router.get("/metrics", summary="Metrics Prometheus", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
