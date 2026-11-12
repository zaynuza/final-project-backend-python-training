# ADR 0006: Row lock (SELECT ... FOR UPDATE) untuk stok, kuota voucher, dan status order

Tanggal: 2026-11-06
Status: Diterima

## Konteks

Unit of Work (ADR 0004) membuat langkah-langkah satu order **atomic**: semuanya tersimpan atau semuanya dibatalkan.
Tetapi atomic belum berarti aman dari **request bersamaan**. Di PostgreSQL (isolation default READ COMMITTED),
use case lama bekerja dengan pola baca -> ubah di Python -> tulis. Dua request yang berjalan bersamaan sama-sama
membaca nilai lama, lalu tulisan yang satu menimpa yang lain (*lost update*):

- Voucher kuota 1, dua order bersamaan: keduanya membaca kuota 1, keduanya berhasil, kuota akhir 0 padahal terpakai dua kali
- Stok 5, delapan order bersamaan: banyak yang berhasil, stok akhir lebih besar dari seharusnya (barang terjual melebihi stok)
- `pay` dan `cancel` bersamaan pada order yang sama: keduanya membaca `pending`, keduanya berhasil,
  stok dikembalikan padahal order sudah dibayar

Bug ini tidak terlihat di test biasa karena SQLite mengunci seluruh database saat menulis, sehingga request tidak
pernah benar-benar bersamaan. Bug ini direproduksi di PostgreSQL asli (lihat `tests/test_concurrency.py`).

## Keputusan

Repository punya method `get_for_update()` (SQLAlchemy: `session.get(..., with_for_update=True)`, SQL:
`SELECT ... FOR UPDATE`). Baris dikunci sampai transaksi selesai, jadi request kedua menunggu lalu membaca nilai
yang sudah terbaru. Dipakai oleh `place_order`, `pay_order`, dan `cancel_order`.

Urutan kunci selalu sama: **order -> produk (urut id) -> voucher**. Urutan yang sama di semua use case mencegah
*deadlock* (dua transaksi saling menunggu kunci yang dipegang yang lain).

## Konsekuensi

- Order yang memakai produk atau voucher yang sama diproses bergantian. Throughput di baris yang sangat ramai
  (misalnya satu produk flash sale) dibatasi kecepatan satu transaksi. Transaksi dijaga tetap pendek, event dikirim setelah commit
- `get_for_update` ada di port, jadi use case tetap tidak tahu SQL. Fake repository di unit test cukup memakai `get`
- SQLite mengabaikan `FOR UPDATE`, jadi hanya `tests/test_concurrency.py` (PostgreSQL, dijalankan di CI)
  yang membuktikan kunci bekerja. Test biasa tidak bisa
- Pengujian: `tests/test_concurrency.py` gagal pada kode lama (4 dari 5 test) dan lulus setelah perbaikan

## Alternatif yang dipertimbangkan

- `UPDATE vouchers SET quota = quota - 1 WHERE code = :c AND quota > 0` (atomic di satu statement): cepat dan tanpa
  kunci eksplisit, tetapi aturan bisnis pindah dari domain (`Voucher.redeem`) ke SQL
- Optimistic locking (kolom `version`, ulangi jika bentrok): cocok untuk bentrokan jarang, tetapi butuh retry di use case
- Isolation SERIALIZABLE: paling sederhana dipakai, tetapi PostgreSQL menggagalkan transaksi yang bentrok dan semua
  use case harus siap mengulang
- Lock terdistribusi di Redis: menambah satu titik gagal dan tidak ikut dalam transaksi database
