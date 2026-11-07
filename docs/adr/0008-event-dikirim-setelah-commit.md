# ADR 0008: Event dikirim setelah commit, risiko event hilang diterima dan dipantau

Tanggal: 2026-11-06
Status: Diterima (dengan risiko yang diketahui)

## Konteks

Order tersimpan di PostgreSQL, lalu event `order.*` dikirim ke RabbitMQ. Dua penyimpanan berbeda tidak bisa
di-commit bersamaan (*dual write*). Pilihan urutannya:

- Kirim event SEBELUM commit: bisa terkirim event untuk order yang akhirnya rollback (notifikasi untuk order yang tidak ada)
- Kirim event SETELAH commit: kalau RabbitMQ gagal tepat setelah commit, order ada tetapi event hilang

## Keputusan

Event dikirim setelah commit (`OrderService`). Kegagalan kirim ke RabbitMQ tidak menggagalkan request (order sudah
tersimpan), tetapi dicatat di log (`error_type: dependency`) dan metric `events_published_total{result="failed"}`.
Alert `EventPublishFailed` di Prometheus menyala begitu ada satu kegagalan. Log kegagalan hanya berisi `event_id` dan `event_type`, bukan isi event,
jadi pemulihan manual berarti mencocokkan waktunya dengan data order lalu menerbitkan ulang event-nya (belum ada skrip untuk ini).

## Konsekuensi

- Customer bisa tidak menerima notifikasi atau poin untuk order tersebut. Menerbitkan ulang event `order.paid`
  aman dilakukan karena kedua consumer idempotent
- Risiko ini sengaja diterima untuk saat ini, bukan tidak diketahui

## Langkah berikutnya

*Transactional outbox*: event ditulis ke tabel `outbox` dalam transaksi yang sama dengan order, lalu proses terpisah
(*relay*) membaca tabel itu dan mengirim ke RabbitMQ sampai berhasil. Event tidak pernah hilang, tetapi bisa terkirim
lebih dari sekali, yang sudah ditangani consumer idempotent (ADR 0003 dan 0005).

## Alternatif yang dipertimbangkan

- Two-phase commit antara PostgreSQL dan RabbitMQ: tidak didukung RabbitMQ dan sangat lambat
- Change Data Capture (misalnya Debezium): kuat, tetapi menambah komponen infrastruktur yang berat untuk skala ini
