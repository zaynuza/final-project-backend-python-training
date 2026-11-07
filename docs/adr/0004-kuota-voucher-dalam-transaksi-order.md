# ADR 0004: Pengurangan kuota voucher dalam transaksi Unit of Work order

Tanggal: 2026-11-05
Status: Diterima

## Konteks

Saat customer membuat order dengan kode voucher (`voucher_code`), sistem harus mengurangi stok setiap produk, mengurangi kuota voucher sebesar 1, dan menyimpan order. Jika kuota voucher dikurangi di transaksi terpisah sebelum stok dicek, kegagalan karena stok habis (`OutOfStock`) akan membuat kuota voucher berkurang padahal order batal dibuat.

## Keputusan

Repository `vouchers` dimasukkan ke dalam `UnitOfWork` yang sama dengan `products` dan `orders`. Pemakaian kuota (`voucher.redeem()`) saat `place_order` serta pengembalian kuota (`voucher.restore()`) saat `cancel_order` dijalankan dalam satu blok `with self.uow:` dan di-commit bersamaan.

## Konsekuensi

- Jika salah satu produk kehabisan stok atau terjadi error lain sebelum `uow.commit()`, seluruh perubahan termasuk kuota voucher otomatis di-rollback
- Pembatalan order mengembalikan stok produk sekaligus kuota voucher secara konsisten
- Tabel `vouchers` berada di database yang sama dengan `orders` dan `products`

## Pembaruan 2026-11-06

Transaksi yang atomic belum melindungi dari dua request bersamaan: kuota 1 bisa terpakai dua kali.
Baris voucher, produk, dan order sekarang dikunci dengan `SELECT ... FOR UPDATE`. Lihat [ADR 0006](0006-row-lock-untuk-stok-voucher-dan-status-order.md).

## Alternatif yang dipertimbangkan

- Layanan voucher terpisah (microservice) dengan Saga/kompensasi: terlalu kompleks untuk kebutuhan saat ini dan membuka celah inkonsistensi sementara
