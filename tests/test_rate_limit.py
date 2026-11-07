"""Test rate limit sliding window (Redis diganti fakeredis)."""
from app.infrastructure.rate_limiter import SlidingWindowRateLimiter
from tests.conftest import order


def test_tidak_ada_celah_di_pergantian_menit(fake_redis):
    limiter = SlidingWindowRateLimiter(fake_redis, limit=10, window=60)
    allowed = [limiter.hit("budi", now=59.0).allowed for _ in range(10)]
    allowed += [limiter.hit("budi", now=60.5).allowed for _ in range(10)]
    assert allowed.count(True) == 10
    assert limiter.hit("budi", now=119.5).allowed       # request detik ke-59 sudah lewat 60 detik


def test_retry_after_dan_limit_per_client(fake_redis):
    limiter = SlidingWindowRateLimiter(fake_redis, limit=2, window=60)
    limiter.hit("budi", now=0)
    limiter.hit("budi", now=10)
    blocked = limiter.hit("budi", now=20)
    assert not blocked.allowed
    assert blocked.retry_after == 40                    # request detik ke-0 lewat di detik ke-60
    assert limiter.hit("ani", now=20).allowed           # client lain punya limit sendiri


def test_api_mengembalikan_429_setelah_limit(client):
    created = client.post("/orders", json=order((1, 1)))         # request ke-1 dari 20
    assert created.headers["x-ratelimit-remaining"] == "19"

    order_id = created.json()["id"]
    assert all(client.get(f"/orders/{order_id}").status_code == 200 for _ in range(19))

    blocked = client.get(f"/orders/{order_id}")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["retry-after"]) > 0


def test_produk_tidak_dibatasi(client):
    assert all(client.get("/products").status_code == 200 for _ in range(30))
