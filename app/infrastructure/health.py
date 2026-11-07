"""Infrastructure: pengecekan dependency untuk readiness check.

Setiap check memanggil dependency dengan cara paling ringan, lalu raise jika gagal.
Timeout dibuat pendek, supaya readiness check tidak ikut lambat saat dependency mati.
"""
import pika
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker


def check_database(session_factory: sessionmaker) -> None:
    with session_factory() as session:
        session.execute(text("SELECT 1"))


def check_redis(url: str) -> None:
    redis = Redis.from_url(url, socket_connect_timeout=2, retry=None)
    try:
        redis.ping()
    finally:
        redis.close()


def check_rabbitmq(url: str) -> None:
    params = pika.URLParameters(url)
    params.socket_timeout = 2
    params.connection_attempts = 1
    pika.BlockingConnection(params).close()
