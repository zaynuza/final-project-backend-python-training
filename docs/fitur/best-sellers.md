# Fitur: Produk Terlaris (Best Sellers)

Menampilkan daftar produk paling laris berdasarkan jumlah unit terjual dari order yang sudah dibayar (`paid`).
Endpoint memakai **cache-aside** di Redis, invalidation otomatis setelah commit, dan **sliding window rate limiting**.

## Aturan bisnis

- Hanya order berstatus `paid` yang dihitung (`pending` dan `cancelled` diabaikan)
- Diurutkan dari jumlah terjual (`sold`) terbanyak, lalu `product_id`
- Parameter `limit` antara 1 sampai 10 (default 5, di luar itu ditolak `422`)
- Hasil disimpan di satu cache key `v1:products:best-sellers` (top 10) lalu dipotong sesuai `limit`
- Cache dihapus setelah commit setiap ada status order yang berubah (misalnya saat order dibayar)
- Order baru (`pending`) tidak menghapus cache
- Response menyertakan header `X-Cache: HIT` atau `MISS`
- Saat cache kosong dan banyak request datang bersamaan (*cache stampede*), hanya satu request yang query database (lock `SET lock:<key> NX EX 5`), yang lain menunggu lalu membaca cache

## Endpoint

| Method | Path | Scope | Keterangan |
|---|---|---|---|
| GET | `/products/best-sellers?limit=5` | Publik (dibatasi rate limit) | Daftar produk terlaris (`product_id`, `name`, `sold`) |

## Error

| Code | HTTP | Kapan |
|---|---|---|
| `validation_error` | 422 | `limit` kurang dari 1 atau lebih dari 10 |
| `rate_limited` | 429 | Melewati batas request per window |

## File yang ditambah atau diubah

| Layer | File | Perubahan |
|---|---|---|
| application | `cache_keys.py`, `ports.py`, `product_service.py` | `BEST_SELLERS_KEY`, port `OrderRepository.best_sellers()`, cache-aside di `ProductService.best_sellers()` |
| infrastructure | `repositories.py`, `unit_of_work.py` | Query agregasi `GROUP BY` di SQL, flag `status_changed`, hapus cache setelah commit |
| api | `routers/products.py`, `schemas.py` | Route `GET /products/best-sellers` dengan `Depends(rate_limit)` dan header `X-Cache` |

## Keputusan teknis

Query agregasi dijalankan langsung di database (`SUM(qty) ... GROUP BY`) dan hasilnya di-cache sebagai top 10 dalam satu key Redis dengan TTL + jitter. Invalidation dilakukan oleh Unit of Work tepat setelah `session.commit()`. Pengisian ulang cache dilindungi lock anti-stampede (`ProductService._cache_aside`, `RedisCache.acquire_lock`); lock hanya optimasi, bukan penjaga kebenaran data.

## Test

```bash
pytest tests/test_best_seller.py -q
```

Yang dites: hanya order `paid` yang dihitung, cache hit tidak menyentuh database, order dibayar menghapus cache, order `pending` tidak menghapus cache, validasi `limit`, rate limit `429`, dan lock stampede (satu query untuk banyak request bersamaan, tests/test_cache.py).
