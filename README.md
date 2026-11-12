# Order API - Final Project

API toko online: produk, produk terlaris, order dengan diskon per tipe customer dan voucher berkuota, pembayaran, poin loyalty dari event, report penjualan di background, dan notifikasi ke customer.

## Fitur

- Produk dan stok. Data produk di-cache di Redis (cache-aside) dan cache-nya dihapus setelah commit
- Order dengan diskon per tipe customer (regular, member, vip) lewat `DiscountPolicy`. Riwayat order memakai keyset pagination dan `selectinload`, jadi tidak ada N+1 query
- [Voucher](docs/fitur/voucher.md) berkuota. Kuota dikurangi dalam transaksi yang sama dengan stok produk
- [Produk terlaris](docs/fitur/best-sellers.md) di `GET /products/best-sellers`: dihitung dengan `GROUP BY` di database, di-cache (`X-Cache: HIT/MISS`), cache dihapus saat ada order dibayar, dan dibatasi rate limit
- [Poin loyalty](docs/fitur/poin-loyalty.md): consumer RabbitMQ untuk event `order.paid`, 1 poin per Rp10.000, idempotent. Saldo bisa dilihat di `GET /customers/{customer}/points`
- Report penjualan dibuat worker Celery di background (`POST /reports/sales`)
- Stok, kuota voucher, dan status order dikunci dengan `SELECT ... FOR UPDATE` dengan urutan kunci tetap supaya tidak deadlock. Diuji di PostgreSQL lewat `tests/test_concurrency.py`
- Cache dengan TTL + jitter dan lock anti-stampede (`SET NX EX`)
- Observability: log JSON dengan `request_id` dan `trace_id`, `/metrics` Prometheus untuk API dan kedua consumer, alert SLO (`prometheus/alerts.yml`), readiness/liveness check, dan tracing OpenTelemetry + Jaeger
- Keamanan: login OAuth2 password flow + JWT, hash Argon2, RBAC per scope, order milik orang lain dijawab 404, [batas login gagal per email](docs/fitur/login-limit.md) (429 + `Retry-After`), schema ketat, dan secret dari environment

## Arsitektur & Keputusan Teknis

Lihat [docs/architecture.md](docs/architecture.md) untuk diagram komponen dan alur request.
Keputusan teknis dicatat di [docs/adr/](docs/adr/):
- [ADR 0001 - Clean Architecture](docs/adr/0001-clean-architecture.md)
- [ADR 0002 - PostgreSQL & Keyset Pagination](docs/adr/0002-postgresql-keyset-pagination.md)
- [ADR 0003 - RabbitMQ untuk Notifikasi](docs/adr/0003-rabbitmq-untuk-notifikasi.md)
- [ADR 0004 - Kuota Voucher dalam Transaksi Order](docs/adr/0004-kuota-voucher-dalam-transaksi-order.md)
- [ADR 0005 - Consumer Poin Loyalty Idempotent](docs/adr/0005-poin-loyalty-idempotent-consumer.md)
- [ADR 0006 - Row Lock untuk Stok, Voucher, dan Status Order](docs/adr/0006-row-lock-untuk-stok-voucher-dan-status-order.md)
- [ADR 0007 - Batas Login Gagal per Email](docs/adr/0007-batas-login-gagal-per-email.md)
- [ADR 0008 - Event Dikirim Setelah Commit (risiko dan outbox)](docs/adr/0008-event-dikirim-setelah-commit.md)

Sebelum rilis, cek [docs/deployment-checklist.md](docs/deployment-checklist.md).

## Menjalankan

Butuh Docker. Semua service (API, worker Celery, consumer notifikasi, consumer poin, PostgreSQL, Redis, RabbitMQ, Jaeger, Prometheus) berjalan di container.

```bash
cp .env.example .env                 # isi JWT_SECRET (minimal 32 karakter), contoh: python -c "import secrets; print(secrets.token_hex(32))"
docker compose up -d --build
docker compose exec api python create_user.py admin@toko.com --role admin
docker compose exec api python create_user.py budi@mail.com --type vip
```

| URL | Isi |
|---|---|
| http://localhost:8000/docs | Dokumentasi API (Swagger), hanya saat `ENV=development` |
| http://localhost:8000/health/ready | Readiness check (PostgreSQL, Redis, RabbitMQ) |
| http://localhost:8000/metrics | Metrics Prometheus |
| http://localhost:15672 | Dashboard RabbitMQ (`guest` / `guest`) |
| http://localhost:16686 | Distributed trace di Jaeger |
| http://localhost:9090 | Prometheus: grafik, targets, dan alert (`/alerts`) |

## Konfigurasi

| Variabel | Wajib | Default | Keterangan |
|---|---|---|---|
| `JWT_SECRET` | ya | - | Kunci tanda tangan JWT, minimal 32 karakter |
| `DATABASE_URL` | tidak | PostgreSQL lokal | Koneksi database (`DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=10`) |
| `REDIS_URL` | tidak | `redis://localhost:6379/2` | Cache produk/best-sellers dan sliding window rate limiter |
| `RABBITMQ_URL` | tidak | `amqp://guest:guest@localhost:5672/` | Broker event `order.*` untuk consumer notifikasi dan poin |
| `CACHE_TTL` | tidak | `60` | TTL cache Redis dalam detik (+ jitter 10%) |
| `RATE_LIMIT` | tidak | `20` | Batas request per `RATE_LIMIT_WINDOW` detik per IP |
| `LOGIN_MAX_ATTEMPTS` | tidak | `5` | Login gagal per email sebelum diblokir sementara |
| `LOGIN_BLOCK_SECONDS` | tidak | `900` | Lama blokir login (detik, dihitung dari gagal pertama) |
| `CONSUMER_METRICS_PORT` / `POINTS_METRICS_PORT` | tidak | `8001` / `8002` | Port `/metrics` consumer notifikasi / poin |
| `ENV` | tidak | `development` | `production` mematikan `/docs` |

## Test

```bash
pip install -r requirements-dev.txt
ruff check .
pytest -q                            # test tanpa Docker: SQLite di memory + fakeredis (test_concurrency dilewati)
# race condition butuh PostgreSQL asli (nama database harus berakhiran _test):
docker compose up -d postgres && docker compose exec postgres createdb -U app orders_test
TEST_POSTGRES_URL=postgresql+psycopg://app:app@localhost:5433/orders_test pytest tests/test_concurrency.py -v   # PostgreSQL compose: localhost:5433
python demo_concurrency.py           # demo: 8 order bersamaan memakai voucher kuota 1 (API harus hidup)
python demo_rate_limit.py            # demo: kirim request sampai 429 + Retry-After (API harus hidup)
python demo_login_limit.py           # demo: 5 password salah, login ke-6 ditolak 429 (butuh DEMO_PASSWORD)
BASE_URL=http://localhost:8000 SMOKE_EMAIL=smoke@toko.com SMOKE_PASSWORD=... python smoke_test.py
```

## Deploy

Pipeline ada di `.github/workflows/ci.yml`. Setiap pull request menjalankan lint (`ruff`), test (`pytest`), build image Docker multi-stage, dan scan kerentanan Trivy. Push ke `main` juga men-deploy manifest `k8s/` ke cluster kind di runner GitHub, menjalankan `smoke_test.py`, lalu mem-publish image ke ghcr.io.
