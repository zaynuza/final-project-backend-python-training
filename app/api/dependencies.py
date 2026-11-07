"""API: dependency graph.

get_session_factory -> get_uow -> get_order_service / get_product_service / get_voucher_service -> route
get_session_factory ada di infrastructure, karena dipakai juga oleh worker Celery.
Cache dan rate limiter memakai Redis yang sama (get_redis).
OrderService mengumumkan event lewat RabbitMQPublisher. Notifikasi dikirim oleh consumer, bukan oleh API.
get_health_checks berisi daftar dependency yang dicek readiness check. Di test, diganti dengan check palsu.
get_auth_service menyiapkan AuthService dengan hasher Argon2, token JWT (secret dari environment),
dan pembatas login gagal (get_login_limiter, Redis).
"""
from collections.abc import Callable

from fastapi import Depends
from sqlalchemy.orm import sessionmaker

from app.application.auth_service import AuthService
from app.application.order_service import OrderService
from app.application.points_service import PointsService
from app.application.ports import Cache, EventPublisher, LoginAttemptLimiter, UnitOfWork
from app.application.product_service import ProductService
from app.application.voucher_service import VoucherService
from app.infrastructure.cache import RedisCache
from app.infrastructure.config import get_settings
from app.infrastructure.database import get_session_factory
from app.infrastructure.health import check_database, check_rabbitmq, check_redis
from app.infrastructure.login_limiter import RedisLoginAttemptLimiter
from app.infrastructure.points_ledger import SqlAlchemyPointsLedger
from app.infrastructure.rabbitmq import RabbitMQPublisher
from app.infrastructure.rate_limiter import SlidingWindowRateLimiter
from app.infrastructure.redis_client import get_redis
from app.infrastructure.security import Argon2PasswordHasher, JwtTokenService
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


def get_cache() -> Cache:
    return RedisCache(get_redis(), get_settings().cache_ttl)


def get_uow(session_factory: sessionmaker = Depends(get_session_factory),
            cache: Cache = Depends(get_cache)) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session_factory, cache)


def get_event_publisher() -> EventPublisher:
    return RabbitMQPublisher(get_settings().rabbitmq_url)


def get_order_service(uow: UnitOfWork = Depends(get_uow),
                      events: EventPublisher = Depends(get_event_publisher)) -> OrderService:
    return OrderService(uow, events)


def get_product_service(uow: UnitOfWork = Depends(get_uow),
                        cache: Cache = Depends(get_cache)) -> ProductService:
    return ProductService(uow, cache)


def get_voucher_service(uow: UnitOfWork = Depends(get_uow)) -> VoucherService:
    return VoucherService(uow)


def get_rate_limiter() -> SlidingWindowRateLimiter:
    settings = get_settings()
    return SlidingWindowRateLimiter(get_redis(), settings.rate_limit, settings.rate_limit_window)


def get_health_checks() -> dict[str, Callable[[], None]]:
    settings = get_settings()
    return {
        "database": lambda: check_database(get_session_factory()),
        "redis": lambda: check_redis(settings.redis_url),
        "rabbitmq": lambda: check_rabbitmq(settings.rabbitmq_url),
    }


def get_login_limiter() -> LoginAttemptLimiter:
    settings = get_settings()
    return RedisLoginAttemptLimiter(get_redis(), settings.login_max_attempts, settings.login_block_seconds)


def get_auth_service(uow: UnitOfWork = Depends(get_uow),
                     limiter: LoginAttemptLimiter = Depends(get_login_limiter)) -> AuthService:
    settings = get_settings()
    return AuthService(uow, Argon2PasswordHasher(),
                       JwtTokenService(settings.jwt_secret, settings.access_token_minutes), limiter)


def get_points_service(session_factory: sessionmaker = Depends(get_session_factory)) -> PointsService:
    return PointsService(SqlAlchemyPointsLedger(session_factory))
