"""Infrastructure: log terstruktur (JSON) dengan request_id dan trace_id.

Satu log = satu baris JSON. Field tambahan dikirim lewat extra={...}:
    logger.info("order dibuat", extra={"order_id": order.id})
request_id diisi middleware API (contextvars, terpisah per request).
trace_id diambil dari span OpenTelemetry yang sedang aktif, jadi log bisa dicocokkan dengan trace di Jaeger.
"""
import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone

from opentelemetry import trace

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# atribut bawaan setiap LogRecord, selain ini berarti dari extra={...}
STANDARD = set(vars(logging.makeLogRecord({}))) | {"message"}


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        span = trace.get_current_span().get_span_context()
        record.trace_id = f"{span.trace_id:032x}" if span.is_valid else None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        time = datetime.fromtimestamp(record.created, timezone.utc)
        log = {
            "time": time.isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in STANDARD and value is not None:
                log[key] = value                         # request_id, trace_id, field dari extra
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        return json.dumps(log, default=str)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestContextFilter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
    for noisy in ("pika", "httpx", "uvicorn.access"):           # log library yang terlalu ramai
        logging.getLogger(noisy).setLevel(logging.WARNING)
