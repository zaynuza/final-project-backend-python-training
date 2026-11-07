"""Infrastructure: distributed tracing dengan OpenTelemetry.

setup_tracing() dipanggil sekali saat proses mulai (API dan consumer).
- Span dikirim ke Jaeger lewat OTLP HTTP (port 4318), dilihat di http://localhost:16686
- FastAPIInstrumentor   : satu span untuk setiap request HTTP, otomatis
- SQLAlchemyInstrumentor: satu span untuk setiap query ke database, otomatis
Span RabbitMQ (publish dan consume) dibuat manual di rabbitmq.py dan notification_consumer.py.
TRACING_ENABLED=0 mematikan pengiriman trace (dipakai di test).
"""
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.infrastructure.config import get_settings
from app.infrastructure.database import get_session_factory


def setup_tracing(service_name: str, app=None) -> None:
    settings = get_settings()
    if not settings.tracing_enabled:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter(endpoint=f"{settings.otlp_endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)
    # engine aplikasi (satu per proses). skip_dep_check: library instrumentation belum
    # mencantumkan SQLAlchemy 2.1 sebagai versi yang didukung, padahal sudah berjalan normal
    engine = get_session_factory().kw["bind"]
    SQLAlchemyInstrumentor().instrument(engine=engine, skip_dep_check=True)
    if app is not None:
        FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
