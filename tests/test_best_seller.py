"""Test fitur produk terlaris: cache-aside, invalidation setelah order dibayar, dan rate limit."""
from app.application.cache_keys import BEST_SELLERS_KEY
from app.infrastructure.repositories import SqlAlchemyOrderRepository
from tests.conftest import auth, order


def paid_order(client, *items):
    order_id = client.post("/orders", json=order(*items)).json()["id"]
    client.post(f"/orders/{order_id}/pay")
    return order_id


def test_hanya_order_dibayar_yang_dihitung(client):
    client.post("/products", json={"name": "Monitor", "price": 2_000_000, "stock": 10},
                headers=auth("admin@toko.com"))
    paid_order(client, (1, 1), (3, 2))
    paid_order(client, (3, 1))
    client.post("/orders", json=order((1, 3)))                 # pending, tidak dihitung

    rows = client.get("/products/best-sellers").json()
    assert rows == [{"product_id": 3, "name": "Monitor", "sold": 3},
                    {"product_id": 1, "name": "Keyboard", "sold": 1}]


def test_cache_hit_tidak_query_database(client, monkeypatch):
    queries = []
    original = SqlAlchemyOrderRepository.best_sellers
    monkeypatch.setattr(SqlAlchemyOrderRepository, "best_sellers",
                        lambda self, limit: queries.append(limit) or original(self, limit))

    first = client.get("/products/best-sellers")
    second = client.get("/products/best-sellers?limit=1")
    assert (first.headers["x-cache"], second.headers["x-cache"]) == ("MISS", "HIT")
    assert queries == [10]                      # selalu top 10, limit dipotong dari cache


def test_order_dibayar_menghapus_cache(client, fake_redis):
    assert client.get("/products/best-sellers").json() == []
    assert fake_redis.exists(BEST_SELLERS_KEY)

    paid_order(client, (1, 2))
    assert not fake_redis.exists(BEST_SELLERS_KEY)
    response = client.get("/products/best-sellers")
    assert response.headers["x-cache"] == "MISS"
    assert response.json() == [{"product_id": 1, "name": "Keyboard", "sold": 2}]


def test_order_baru_tidak_menghapus_cache(client, fake_redis):
    client.get("/products/best-sellers")
    client.post("/orders", json=order((1, 1)))               # status pending
    assert fake_redis.exists(BEST_SELLERS_KEY)


def test_limit_divalidasi(client):
    assert client.get("/products/best-sellers?limit=0").status_code == 422
    assert client.get("/products/best-sellers?limit=11").status_code == 422


def test_best_sellers_dibatasi_rate_limit(client):
    assert all(client.get("/products/best-sellers").status_code == 200 for _ in range(20))
    blocked = client.get("/products/best-sellers")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
