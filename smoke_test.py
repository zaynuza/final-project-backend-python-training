"""Smoke test Order API: dijalankan ke aplikasi yang baru di-deploy, setelah deploy selesai.

Yang dicek adalah hasil deploy (config, koneksi ke dependency, login), dengan request sungguhan.
Butuh user khusus smoke test (role admin) yang dibuat sekali di setiap environment:
    python create_user.py smoke@toko.com --role admin

Jalankan:
    BASE_URL=http://localhost:8000 SMOKE_EMAIL=smoke@toko.com SMOKE_PASSWORD=... python smoke_test.py
Exit code 1 jika ada langkah yang gagal, supaya pipeline CD berhenti.
"""
import os
import sys

import httpx


def check(name: str, response: httpx.Response, expected: int) -> bool:
    passed = response.status_code == expected
    print(f"{'OK   ' if passed else 'GAGAL'} {name:<26} {response.request.method} "
          f"{response.request.url.path} -> {response.status_code}")
    return passed


def run(client: httpx.Client, email: str, password: str) -> bool:
    results = [
        check("proses berjalan", client.get("/health/live"), 200),
        check("semua dependency siap", client.get("/health/ready"), 200),
        check("tanpa token ditolak", client.get("/auth/me"), 401),
    ]
    login = client.post("/auth/token", data={"username": email, "password": password})
    results.append(check("login", login, 200))
    if login.status_code == 200:
        auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
        results.append(check("token terbaca", client.get("/auth/me", headers=auth), 200))
        results.append(check("produk dari database", client.get("/products"), 200))
        results.append(check("produk terlaris (cache)", client.get("/products/best-sellers"), 200))
        results.append(check("saldo poin loyalty", client.get(f"/customers/{email}/points", headers=auth), 200))
        # voucher: hanya membaca (tidak membuat data di production). Kode yang tidak ada harus 404, bukan 500
        results.append(check("voucher (kode tidak ada)", client.get("/vouchers/SMOKE-TIDAK-ADA", headers=auth), 404))
        report = client.post("/reports/sales", headers=auth)
        results.append(check("worker menerima report", report, 202))
    return all(results)


def main() -> None:
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    email, password = os.environ["SMOKE_EMAIL"], os.environ["SMOKE_PASSWORD"]
    print(f"Smoke test ke {base_url}")
    with httpx.Client(base_url=base_url, timeout=10) as client:
        passed = run(client, email, password)
    print("Smoke test lulus" if passed else "Smoke test GAGAL")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
