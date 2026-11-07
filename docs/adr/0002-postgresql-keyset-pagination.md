# ADR 0002: Riwayat order memakai keyset pagination

Tanggal: 2026-10-23
Status: Diterima

## Konteks

Riwayat order customer memakai `OFFSET`. Dengan 200.000 order, halaman yang
jauh makin lambat, karena database tetap membaca semua baris yang dilewati.

## Keputusan

`GET /orders` memakai keyset pagination: client mengirim `after` (id order
terakhir), lalu query memakai `WHERE id < :after ORDER BY id DESC LIMIT
:limit` dengan index `(customer, id)`.

## Konsekuensi

- Waktu query sama cepatnya di halaman mana pun
- Client tidak bisa lompat langsung ke halaman tertentu, hanya "halaman
  berikutnya"
- Urutan hanya berdasarkan id. Urutan lain butuh index dan cursor sendiri
