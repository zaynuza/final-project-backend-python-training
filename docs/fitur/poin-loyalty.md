# Fitur: Poin Loyalty dari Event Order

Setiap order yang dibayar (`order.paid`) memberi **1 poin per Rp10.000** dari nilai `total` order (setelah diskon dan voucher).
Poin ditambah oleh consumer RabbitMQ terpisah, jadi pembayaran tidak ikut melambat. Event yang datang dua kali tidak menambah poin dua kali.

## Aturan bisnis

- Poin hanya dihitung saat order dibayar (`order.paid`) sebesar `total // 10_000`
- Event selain `order.paid` diabaikan dan langsung di-ack
- Event dengan `event_id` yang sama hanya menambah poin satu kali walaupun dikirim ulang oleh broker (idempotent)
- Pesan rusak (bukan JSON atau field tidak valid) langsung dipindah ke `points.dlq` (`nack(requeue=False)`)
- Customer hanya bisa melihat saldo poin miliknya sendiri; admin (`orders:all`) bisa melihat saldo poin semua customer

## Endpoint & Consumer

| Komponen | Path / Queue | Scope | Keterangan |
|---|---|---|---|
| GET | `/customers/{customer}/points` | `orders:write` (milik sendiri) / `orders:all` (admin) | Lihat saldo poin loyalty customer |
| Consumer | Queue `points` (binding `order.paid`) | - | `python -m app.consumers.points_consumer` |

## Error

| Code | HTTP | Kapan |
|---|---|---|
| `invalid_token` | 401 | Belum login atau token tidak valid |
| `forbidden` | 403 | Customer mencoba melihat saldo poin customer lain |

## File yang ditambah atau diubah

| Layer | File | Perubahan |
|---|---|---|
| application | `points_service.py`, `ports.py` | `PointsService` (`handle()`, `balance()` dengan cek akses), port `PointsLedger` |
| infrastructure | `models.py`, `points_ledger.py`, `rabbitmq.py`, `metrics.py` | Tabel `customer_points` & `point_events`, penambahan poin idempotent dalam satu transaksi, topologi queue `points` & `points.dlq`, metric `points_events_processed_total` |
| consumers | `points_consumer.py` | Consumer RabbitMQ dengan manual ack/nack, propagasi trace OpenTelemetry, dan log JSON |
| api | `routers/customers.py`, `schemas.py`, `dependencies.py` | Endpoint `GET /customers/{customer}/points` dengan cek akses RBAC |

## Keputusan teknis

Pencatatan `event_id` (primary key di `point_events`) dan penambahan saldo (`customer_points`) dilakukan dalam satu transaksi database, dengan `INSERT ... ON CONFLICT DO NOTHING` dan `UPDATE points = points + n` yang atomic, sehingga aman walau beberapa event customer yang sama diproses bersamaan. Lihat [ADR 0005](../adr/0005-poin-loyalty-idempotent-consumer.md).
Event bisa hilang jika RabbitMQ gagal setelah commit order, dipantau lewat alert `EventPublishFailed` ([ADR 0008](../adr/0008-event-dikirim-setelah-commit.md)).

## Test

```bash
pytest tests/test_points.py -q
# event bersamaan di PostgreSQL asli (butuh TEST_POSTGRES_URL, lihat tests/test_concurrency.py)
```

Yang dites: perhitungan poin, pengiriman event ganda (idempotency), pengabaian event selain `order.paid`, pemindahan pesan rusak ke DLQ, pembacaan saldo lewat API, dan cek akses antar customer.
