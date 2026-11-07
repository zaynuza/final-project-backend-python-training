"""Setting test: tanpa Redis, RabbitMQ, worker, maupun database sungguhan.

- Celery mode eager, database SQLite di memory
- Redis diganti fakeredis (Redis palsu di memory, perintahnya sama)
- Publisher RabbitMQ diganti FakeEventPublisher, event yang diumumkan bisa dicek di test
- Trace tidak dikirim ke Jaeger (TRACING_ENABLED=0)
- Tiga user dibuat di setiap test: admin, budi (customer vip), ani (customer regular).
  Token dibuat langsung lewat JwtTokenService, jadi test tidak perlu login dulu.
Environment di-set sebelum app di-import, karena config dibaca saat import.
"""
import os

os.environ.update(
    DATABASE_URL="sqlite://",
    CELERY_TASK_ALWAYS_EAGER="1",
    CELERY_BROKER_URL="memory://",
    CELERY_RESULT_BACKEND="cache+memory://",
    NOTIFICATION_FAIL_RATE="0",
    RATE_LIMIT="20",
    TRACING_ENABLED="0",
    JWT_SECRET="test-secret-yang-panjangnya-minimal-32-karakter",
    ENV="development",
)

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.dependencies import get_event_publisher  # noqa: E402
from app.domain.user import User  # noqa: E402
from app.infrastructure import redis_client  # noqa: E402
from app.infrastructure.database import get_session_factory  # noqa: E402
from app.infrastructure.security import Argon2PasswordHasher, JwtTokenService  # noqa: E402
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork  # noqa: E402
from app.main import app  # noqa: E402
from tests.fakes import FakeEventPublisher  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database():
    get_session_factory.cache_clear()          # setiap test dapat database baru
    yield
    get_session_factory.cache_clear()


PASSWORD = "rahasia123"
PASSWORD_HASH = Argon2PasswordHasher().hash(PASSWORD)     # dihitung sekali, Argon2 sengaja lambat
USERS = {"admin@toko.com": ("admin", "regular"),
         "budi@mail.com": ("customer", "vip"),
         "ani@mail.com": ("customer", "regular")}


@pytest.fixture(autouse=True)
def users(fresh_database):
    with SqlAlchemyUnitOfWork(get_session_factory()) as uow:
        for email, (role, customer_type) in USERS.items():
            uow.users.add(User(email, PASSWORD_HASH, role, customer_type))
        uow.commit()


def auth(email: str, minutes: int = 30) -> dict:
    """Header Authorization untuk user di USERS."""
    token = JwtTokenService(os.environ["JWT_SECRET"], minutes).issue(User(email, "", *USERS[email]))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client.Redis, "from_url", lambda *args, **kwargs: fake)
    redis_client.get_redis.cache_clear()       # setiap test dapat Redis baru yang kosong
    yield fake
    redis_client.get_redis.cache_clear()


@pytest.fixture(autouse=True)
def events():
    fake = FakeEventPublisher()
    app.dependency_overrides[get_event_publisher] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    client = TestClient(app)
    admin = auth("admin@toko.com")
    client.post("/products", json={"name": "Keyboard", "price": 500_000, "stock": 5}, headers=admin)
    client.post("/products", json={"name": "Mouse", "price": 100_000, "stock": 1}, headers=admin)
    client.headers.update(auth("budi@mail.com"))          # default: login sebagai budi (customer vip)
    return client


def order(*items):
    return {"items": [{"product_id": p, "qty": q} for p, q in items]}
