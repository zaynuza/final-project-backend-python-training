# ADR 0003: Notifikasi lewat event RabbitMQ, bukan task Celery

Tanggal: 2026-10-23
Status: Diterima

## Konteks

Sebelumnya `OrderService` memanggil task Celery `send_notification` setelah
order dibuat. Fitur baru (poin loyalty, analytics) juga ingin bereaksi saat
order dibuat atau dibayar. Jika semua dipanggil dari `OrderService`, service
itu harus diubah setiap ada fitur baru.

## Keputusan

`OrderService` hanya mengirim event (`order.placed`, `order.paid`,
`order.cancelled`) ke exchange topic `orders` di RabbitMQ setelah commit.
Notifikasi dikirim oleh consumer terpisah. Celery tetap dipakai untuk report,
karena report adalah job yang diminta user.

## Konsekuensi

- Fitur baru cukup membuat queue dan consumer baru, `OrderService` tidak
  diubah
- Butuh RabbitMQ sebagai service tambahan yang harus dijalankan dan dipantau
- Consumer harus idempotent, karena RabbitMQ menjamin pesan sampai minimal
  sekali
- Jika RabbitMQ mati tepat setelah commit, event hilang. Solusi lengkapnya
  (outbox pattern) belum dibuat

## Alternatif yang dipertimbangkan

- Tetap memakai Celery: lebih sederhana, tetapi setiap fitur baru mengubah
  `OrderService`
- Kafka: event bisa dibaca ulang, tetapi retry dan DLQ harus dibuat sendiri
  dan operasionalnya lebih berat
