"""Infrastructure: koneksi database SQLAlchemy.

get_session_factory() dipakai bersama oleh API, worker Celery, dan consumer RabbitMQ.
Satu engine = satu connection pool per proses. Koneksi dipakai ulang, tidak dibuka setiap request.
"""
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def create_session_factory(database_url: str, pool_size: int = 5, max_overflow: int = 10) -> sessionmaker:
    from app.infrastructure import models  # noqa: F401  (daftarkan tabel ke Base)

    options = {}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    if database_url == "sqlite://":          # database di memory, dipakai di test
        options["poolclass"] = StaticPool
    if not database_url.startswith("sqlite"):
        options["connect_args"] = {"connect_timeout": 3}   # detik, database mati = cepat gagal
        options.update(pool_size=pool_size, max_overflow=max_overflow,
                       pool_pre_ping=True,    # cek koneksi masih hidup, misalnya setelah database restart
                       pool_recycle=1800)     # ganti koneksi yang sudah terbuka 30 menit

    engine = create_engine(database_url, **options)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


@lru_cache
def get_session_factory() -> sessionmaker:
    from app.infrastructure.config import get_settings

    settings = get_settings()
    return create_session_factory(settings.database_url, settings.db_pool_size, settings.db_max_overflow)
