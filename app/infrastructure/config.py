"""Infrastructure: config dari environment (Singleton lewat @lru_cache)."""
import os
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    database_url: str
    notification_channel: str
    notification_fail_rate: float     # simulasi server email gangguan, 0.5 = setengah percobaan gagal
    broker_url: str
    result_backend: str
    task_always_eager: bool           # True = task langsung dijalankan tanpa worker (dipakai di test)
    redis_url: str                    # Redis untuk cache dan rate limiter
    cache_ttl: int                    # detik
    rate_limit: int                   # jumlah request per window, per client
    rate_limit_window: int            # detik
    db_pool_size: int                 # koneksi database yang disimpan di pool, per proses
    db_max_overflow: int              # koneksi tambahan saat sibuk
    rabbitmq_url: str                 # broker untuk event order
    notification_max_retries: int     # batas retry sebelum pesan dipindah ke DLQ
    notification_retry_delay_ms: int  # jeda retry pertama, berikutnya 2x lipat
    log_level: str                    # DEBUG, INFO, WARNING, ERROR
    tracing_enabled: bool             # kirim trace ke Jaeger lewat OTLP
    otlp_endpoint: str                # alamat penerima trace (OTLP HTTP)
    consumer_metrics_port: int        # port /metrics milik consumer notifikasi
    points_metrics_port: int          # port /metrics milik consumer poin
    login_max_attempts: int           # login gagal yang boleh terjadi sebelum email diblokir sementara
    login_block_seconds: int          # lama blokir, dihitung dari login gagal pertama
    env: str                          # development / production
    jwt_secret: str = field(repr=False)   # kunci tanda tangan JWT, min. 32 karakter, tidak ikut tercetak
    access_token_minutes: int         # masa berlaku access token
    cors_origins: list[str]           # domain frontend yang boleh memanggil API dari browser


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/orders"),
        notification_channel=os.getenv("NOTIFICATION_CHANNEL", "email"),
        notification_fail_rate=float(os.getenv("NOTIFICATION_FAIL_RATE", "0")),
        broker_url=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        result_backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
        task_always_eager=os.getenv("CELERY_TASK_ALWAYS_EAGER", "0") == "1",
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/2"),
        cache_ttl=int(os.getenv("CACHE_TTL", "60")),
        rate_limit=int(os.getenv("RATE_LIMIT", "20")),
        rate_limit_window=int(os.getenv("RATE_LIMIT_WINDOW", "60")),
        db_pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        db_max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
        rabbitmq_url=os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"),
        notification_max_retries=int(os.getenv("NOTIFICATION_MAX_RETRIES", "3")),
        notification_retry_delay_ms=int(os.getenv("NOTIFICATION_RETRY_DELAY_MS", "1000")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        tracing_enabled=os.getenv("TRACING_ENABLED", "1") == "1",
        otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"),
        consumer_metrics_port=int(os.getenv("CONSUMER_METRICS_PORT", "8001")),
        points_metrics_port=int(os.getenv("POINTS_METRICS_PORT", "8002")),
        login_max_attempts=int(os.getenv("LOGIN_MAX_ATTEMPTS", "5")),
        login_block_seconds=int(os.getenv("LOGIN_BLOCK_SECONDS", "900")),
        env=os.getenv("ENV", "development"),
        jwt_secret=os.getenv("JWT_SECRET", ""),           # sengaja tanpa default yang bisa dipakai
        access_token_minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "30")),
        cors_origins=[o for o in os.getenv("CORS_ORIGINS", "").split(",") if o],
    )


def check_api_settings(settings: Settings) -> None:
    """Dipanggil saat API start. Setting yang tidak aman = API gagal start, bukan jalan diam-diam."""
    if len(settings.jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET belum di-set atau kurang dari 32 karakter. "
                           "Buat dengan: python -c \"import secrets; print(secrets.token_hex(32))\"")
