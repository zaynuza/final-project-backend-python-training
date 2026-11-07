# Fitur: Voucher Diskon

Customer bisa memakai kode voucher saat membuat order untuk mendapat potongan harga tetap.
Setiap voucher punya kuota. Kuota berkurang saat dipakai dan kembali saat order dibatalkan.

## Aturan bisnis

- Satu order hanya bisa memakai satu voucher
- Voucher dengan kuota 0 tidak bisa dipakai (`voucher_exhausted`)
- Potongan voucher ditambahkan ke diskon tipe customer, dan tidak pernah membuat total order negatif
- Order dibatalkan = kuota voucher dikembalikan bersama stok produk
- Stok kurang = order gagal, kuota voucher tidak terpakai (satu transaksi Unit of Work dengan stok)
- Dua order bersamaan tidak bisa memakai kuota yang sama: baris voucher dikunci (`SELECT ... FOR UPDATE`), request kedua menunggu lalu membaca kuota terbaru

## Endpoint

| Method | Path | Scope | Keterangan |
|---|---|---|---|
| POST | `/vouchers` | `products:write` (admin) | Buat voucher: `code`, `amount`, `quota` |
| GET | `/vouchers/{code}` | `products:write` (admin) | Detail dan sisa kuota |
| POST | `/orders` | `orders:write` | Field baru `voucher_code` (opsional) |

## Error

| Code | HTTP | Kapan |
|---|---|---|
| `voucher_not_found` | 404 | Kode voucher tidak ada |
| `voucher_exhausted` | 409 | Kuota sudah habis |
| `voucher_already_exists` | 409 | Membuat voucher dengan kode yang sudah ada |

## File yang ditambah atau diubah

| Layer | File | Perubahan |
|---|---|---|
| domain | `voucher.py`, `order.py`, `errors.py` | Entity `Voucher` (`redeem()`, `restore()`), `Order.apply_voucher()`, error domain |
| application | `voucher_service.py`, `order_service.py`, `ports.py`, `errors.py` | Use case buat/lihat voucher, pakai & kembalikan kuota di dalam Unit of Work |
| infrastructure | `models.py`, `repositories.py`, `unit_of_work.py` | Tabel `vouchers`, kolom `orders.voucher_code`, `SqlAlchemyVoucherRepository` |
| api | `routers/vouchers.py`, `routers/orders.py`, `schemas.py`, `errors.py`, `dependencies.py` | Endpoint, proteksi RBAC `products:write`, schema ketat, pemetaan error |

## Keputusan teknis

Kuota dikurangi di transaksi yang sama dengan stok produk dan penyimpanan order, supaya order yang gagal tidak menghabiskan kuota.
Lihat [ADR 0004](../adr/0004-kuota-voucher-dalam-transaksi-order.md).
Perlindungan dari request bersamaan memakai row lock, lihat [ADR 0006](../adr/0006-row-lock-untuk-stok-voucher-dan-status-order.md).

## Test

```bash
pytest tests/test_voucher.py -q
python demo_concurrency.py     # 8 order bersamaan, voucher kuota 1: tepat 1 yang berhasil (API harus hidup)
```

Yang dites: kuota berkurang sampai habis, potongan tidak membuat total negatif, kuota kembali saat order dibatalkan, kuota tidak terpakai saat stok kurang (rollback transaksi), format error, dan proteksi RBAC admin.
