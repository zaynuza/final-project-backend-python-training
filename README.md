# Order API - Final Project

API toko online siap produksi: produk, katalog produk terlaris (*best-sellers*), order dengan diskon per tipe customer dan voucher kuota, pembayaran, poin loyalty otomatis berbasis event, report penjualan di background, serta notifikasi ke customer.

## Fitur

- **Produk & Stok:** CRUD produk dengan cache-aside di Redis dan invalidation otomatis setelah commit
- **Order & Diskon:** aggregate `Order` dengan `DiscountPolicy` (regular/member/vip), keyset pagination, tanpa N+1 query (`selectinload`)
- **[Voucher Diskon](docs/fitur/voucher.md):** potongan harga dengan kuota yang terikat dalam satu transaksi Unit of Work bersama stok produk
- **[Produk Terlaris](docs/fitur/best-sellers.md):** `GET /products/best-sellers` dengan query agregasi SQL, cache-aside (`X-Cache: HIT/MISS`), invalidation saat order dibayar, dan rate limiting
- **[Poin Loyalty](docs/fitur/poin-loyalty.md):** consumer RabbitMQ pada event `order.paid` yang menambah 1 poin per Rp10.000 secara idempotent, dilengkapi endpoint `GET /customers/{customer}/points`
- **Background Report:** pembuatan laporan penjualan asynchronous lewat worker Celery (`POST /reports/sales`)
- **Concurrency:** stok, kuota voucher, dan status order dikunci dengan `SELECT ... FOR UPDATE` (urutan kunci tetap, anti-deadlock), poin loyalty ditambah atomic. Dibuktikan di PostgreSQL asli lewat `tests/test_concurrency.py`
- **Cache:** cache-aside dengan TTL + jitter, invalidation setelah commit, dan lock anti-stampede (`SET NX EX`)
- **Observability:** log JSON dengan `request_id` & `trace_id`, Prometheus `/metrics` untuk API dan kedua consumer, alert SLO (`prometheus/alerts.yml`), readiness/liveness check, distributed tracing OpenTelemetry + Jaeger
- **[Security](docs/fitur/login-limit.md):** OAuth2 password flow + JWT, hash Argon2, RBAC per scope, cek pemilik data (order orang lain = 404), batas login gagal per email (429 + `Retry-After`), schema ketat, secret dari environment

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

Setiap pull request menjalankan lint (`ruff`), unit & integration test (`pytest`), build multi-stage Docker image, scan kerentanan Trivy, deploy ke cluster Kubernetes (`k8s/`), dan menjalankan `smoke_test.py`.
