# ADR 0005: Consumer poin loyalty idempotent dengan transaksi tabel point_events

Tanggal: 2026-11-05
Status: Diterima

## Konteks

RabbitMQ menjamin pengiriman pesan *at-least-once*: event `order.paid` yang sama bisa diterima lebih dari sekali jika koneksi putus sebelum ack atau saat terjadi redelivery. Jika consumer langsung menambah saldo poin tanpa mencatat `event_id`, customer bisa mendapat poin ganda untuk satu pembayaran.

## Keputusan

`PointsService` dipanggil oleh consumer terpisah pada queue `points` (di-bind ke exchange `orders` dengan routing key `order.paid`). Adapter `SqlAlchemyPointsLedger.add()` menyimpan `event_id` sebagai primary key di tabel `point_events` dan memperbarui saldo di tabel `customer_points` dalam **satu transaksi database**:

1. `INSERT INTO point_events ... ON CONFLICT DO NOTHING ... RETURNING event_id`. Tidak ada baris kembali berarti `event_id` sudah pernah diproses: `add()` mengembalikan `False` dan consumer tetap mengirim `ack`
2. `INSERT INTO customer_points ... ON CONFLICT DO NOTHING` (poin 0) membuat baris saldo untuk customer baru
3. `UPDATE customer_points SET points = points + :n`: penambahan dilakukan database, bukan dibaca ke Python lalu ditulis ulang

## Konsekuensi

- Event `order.paid` yang dikirim berulang kali dijamin hanya menambah poin tepat satu kali
- `OrderService` sama sekali tidak berubah ketika fitur poin loyalty ditambahkan
- Pesan yang rusak (bukan JSON atau field tidak valid) langsung dikirim ke `points.dlq` lewat `basic_nack(requeue=False)` agar tidak menyumbat antrean

## Pembaruan 2026-11-06: dua consumer bersamaan

Versi pertama menangkap `IntegrityError` dari seluruh blok dan menulis `record.points += points` di Python.
Pengujian di PostgreSQL asli menemukan dua masalah saat beberapa event customer yang sama diproses bersamaan:

- Customer baru: dua event pertama sama-sama mencoba membuat baris `customer_points`. Yang kalah mendapat `IntegrityError`
  dari tabel SALDO, tetapi `except IntegrityError` mengira itu "event sudah diproses", sehingga poinnya hilang diam-diam
  dan event di-ack
- Customer lama: dua consumer membaca saldo yang sama lalu menulis, tambahan yang satu menimpa yang lain (*lost update*)

Perbaikan: `ON CONFLICT DO NOTHING` untuk kedua tabel dan penambahan atomic di SQL (di atas). Tidak ada lagi `try/except IntegrityError`,
jadi error lain tidak salah dianggap "event duplikat". Dites di `tests/test_concurrency.py`.

## Risiko yang diketahui

Event `order.paid` dikirim setelah commit order, sehingga bisa hilang jika RabbitMQ gagal tepat saat itu
(poin tidak bertambah). Lihat [ADR 0008](0008-event-dikirim-setelah-commit.md).

## Alternatif yang dipertimbangkan

- Menyimpan `event_id` di Redis (TTL): jika key kedaluwarsa atau Redis kehilangan data sebelum penambahan poin di-commit ke PostgreSQL, pengecekan idempotency dan saldo poin tidak berada dalam satu transaksi atomik
