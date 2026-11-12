"""Demo race condition untuk presentasi: banyak request memakai voucher berkuota 1 DI WAKTU YANG SAMA.

Yang terjadi dengan kode yang benar (row lock, ADR 0006):
    tepat 1 order berhasil (201), sisanya ditolak 409 voucher_exhausted, sisa kuota 0 (bukan negatif),
    dan stok produk hanya berkurang 1 (order yang ditolak di-rollback, stok tidak ikut berkurang).
Tanpa row lock, beberapa request bisa sama-sama membaca kuota 1, jadi lebih dari satu order lolos.

Jalankan (API harus sudah hidup, user admin sudah dibuat):
    BASE_URL=http://localhost:8000 SMOKE_EMAIL=admin@toko.com SMOKE_PASSWORD=... python demo_concurrency.py
REQUESTS=8 (default) = jumlah request bersamaan. Semua request order berasal dari satu IP, jadi dihitung rate limit
(default 20 per menit): jalankan demo ini sebelum demo rate limit, atau tunggu semenit.
Exit code 1 kalau hasilnya salah.
"""
import os
import sys
import threading
import uuid
from collections import Counter

import httpx


def main() -> None:
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    email, password = os.environ["SMOKE_EMAIL"], os.environ["SMOKE_PASSWORD"]
    requests = int(os.getenv("REQUESTS", "8"))

    with httpx.Client(base_url=base_url, timeout=30) as client:
        token = client.post("/auth/token", data={"username": email, "password": password}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        suffix = uuid.uuid4().hex[:6].upper()
        code = f"RACE-{suffix}"
        product = client.post("/products", json={"name": f"Produk race {suffix}", "price": 100_000, "stock": 100},
                              headers=headers).json()
        client.post("/vouchers", json={"code": code, "amount": 10_000, "quota": 1}, headers=headers)
        print(f"Voucher {code} kuota 1, produk #{product['id']} stok 100. Kirim {requests} order bersamaan...")

        start = threading.Barrier(requests)             # semua thread menunggu, lalu berangkat bersamaan
        statuses: list[int] = []

        def place_order() -> None:
            with httpx.Client(base_url=base_url, timeout=30, headers=headers) as own:
                start.wait()
                response = own.post("/orders", json={"items": [{"product_id": product["id"], "qty": 1}],
                                                     "voucher_code": code})
                statuses.append(response.status_code)

        threads = [threading.Thread(target=place_order) for _ in range(requests)]
        [t.start() for t in threads]
        [t.join() for t in threads]

        quota = client.get(f"/vouchers/{code}", headers=headers).json()["quota"]
        stock = client.get(f"/products/{product['id']}").json()["stock"]

    counts = Counter(statuses)
    print(f"Hasil status       : {dict(sorted(counts.items()))}   (201 = order jadi, 409 = voucher habis)")
    print(f"Sisa kuota voucher : {quota}   (harus 0)")
    print(f"Sisa stok produk   : {stock}   (harus 99: hanya order yang berhasil mengurangi stok)")
    ok = counts.get(201) == 1 and quota == 0 and stock == 99
    print("LULUS: kuota tidak bocor" if ok else "GAGAL: ada order berlebih, cek row lock (get_for_update)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
