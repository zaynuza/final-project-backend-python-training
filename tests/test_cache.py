"""Test cache produk: cache-aside di ProductService, invalidation setelah commit, dan lock anti-stampede."""
import threading
import time

import pytest

from app.application.cache_keys import BEST_SELLERS_KEY, PRODUCT_LIST_KEY, product_key
from app.application.errors import ProductNotFound
from app.application.product_service import ProductService
from app.domain.money import Money
from app.domain.product import Product
from app.infrastructure.cache import RedisCache
from tests.conftest import order
from tests.fakes import FakeCache, FakeUnitOfWork


def test_cache_hit_tidak_query_database():
    uow = FakeUnitOfWork([Product("Keyboard", Money(500_000), 5)])
    queries = []
    query = uow.products.get
    uow.products.get = lambda product_id: queries.append(product_id) or query(product_id)

    service = ProductService(uow, FakeCache())
    for _ in range(3):
        assert service.get_product(1).stock == 5
    assert queries == [1]                      # cuma request pertama yang ke database


def test_produk_disimpan_di_redis_dengan_ttl(client, fake_redis):
    client.get("/products/1")
    assert fake_redis.exists(product_key(1))
    assert 0 < fake_redis.ttl(product_key(1)) <= 66      # TTL 60 + jitter maksimal 6


def test_order_menghapus_cache_produk(client, fake_redis):
    assert client.get("/products/1").json()["stock"] == 5
    assert client.get("/products").json()[0]["stock"] == 5

    client.post("/orders", json=order((1, 2)))
    assert not fake_redis.exists(product_key(1), PRODUCT_LIST_KEY)
    assert client.get("/products/1").json()["stock"] == 3
    assert client.get("/products").json()[0]["stock"] == 3


def test_order_gagal_tidak_mengubah_cache(client, fake_redis):
    client.get("/products/1")
    assert client.post("/orders", json=order((1, 2), (2, 3))).status_code == 409   # rollback
    assert fake_redis.exists(product_key(1))
    assert client.get("/products/1").json()["stock"] == 5


# ---------- cache stampede: lock SET NX ----------
class NoLockCache(FakeCache):
    """Cache dengan lock yang selalu 'berhasil': meniru kode lama tanpa lock, untuk pembanding."""

    def acquire_lock(self, key: str, ttl: int = 5) -> bool:
        return True


def slow_product_queries(uow: FakeUnitOfWork, delay: float = 0.2) -> list[int]:
    queries: list[int] = []
    query = uow.products.get

    def slow(product_id: int):
        queries.append(product_id)
        time.sleep(delay)                               # database lambat: semua request punya waktu untuk menyerbu
        return query(product_id)

    uow.products.get = slow
    return queries


def read_together(service: ProductService, threads: int = 10) -> list:
    start = threading.Barrier(threads)
    stocks: list = []

    def request():
        start.wait()
        stocks.append(service.get_product(1).stock)

    workers = [threading.Thread(target=request) for _ in range(threads)]
    [w.start() for w in workers]
    [w.join(timeout=10) for w in workers]
    return stocks


def test_stampede_dengan_lock_hanya_satu_query_ke_database():
    uow = FakeUnitOfWork([Product("Keyboard", Money(500_000), 5)])
    queries = slow_product_queries(uow)
    stocks = read_together(ProductService(uow, FakeCache()))
    assert stocks == [5] * 10                           # semua request dapat jawaban yang benar
    assert queries == [1]                               # tapi database hanya ditanya sekali


def test_stampede_tanpa_lock_semua_request_query_database():
    uow = FakeUnitOfWork([Product("Keyboard", Money(500_000), 5)])
    queries = slow_product_queries(uow)
    read_together(ProductService(uow, NoLockCache()))
    assert len(queries) > 1                             # inilah yang dicegah oleh lock


def test_lock_dilepas_walau_produk_tidak_ada():
    cache = FakeCache()
    service = ProductService(FakeUnitOfWork([Product("Keyboard", Money(500_000), 5)]), cache)
    with pytest.raises(ProductNotFound):
        service.get_product(99)
    assert cache.acquire_lock(product_key(99))          # tidak macet: lock sudah dilepas


def test_redis_lock_hanya_untuk_satu_pemanggil_dan_punya_ttl(fake_redis):
    cache = RedisCache(fake_redis, ttl=60)
    assert cache.acquire_lock("v1:product:1") is True
    assert cache.acquire_lock("v1:product:1") is False  # SET NX: yang kedua ditolak
    assert 0 < fake_redis.ttl("lock:v1:product:1") <= 5  # lock hilang sendiri kalau pemegangnya mati
    cache.release_lock("v1:product:1")
    assert cache.acquire_lock("v1:product:1") is True


def test_best_sellers_dan_daftar_produk_tetap_memakai_cache(client, fake_redis):
    client.get("/products")
    client.get("/products/best-sellers")
    assert fake_redis.exists(PRODUCT_LIST_KEY, BEST_SELLERS_KEY) == 2
    assert not fake_redis.keys("lock:*")                # tidak ada lock yang tertinggal
