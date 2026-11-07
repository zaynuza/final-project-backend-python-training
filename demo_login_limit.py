"""Demo batas login gagal untuk presentasi: 5 kali password salah, lalu login ke-6 ditolak 429
walaupun password-nya benar (ADR 0007).

Jalankan (API harus sudah hidup, user ani@mail.com sudah dibuat):
    BASE_URL=http://localhost:8000 DEMO_EMAIL=ani@mail.com DEMO_PASSWORD=... python demo_login_limit.py
Setelah demo, buka kunci supaya user bisa login lagi (jika tidak, tunggu 15 menit):
    docker compose exec redis redis-cli -n 2 DEL login-fail:ani@mail.com
Exit code 1 kalau hasilnya tidak sesuai.
"""
import os
import sys

import httpx


def login(client: httpx.Client, email: str, password: str) -> httpx.Response:
    return client.post("/auth/token", data={"username": email, "password": password})


def main() -> None:
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    email = os.getenv("DEMO_EMAIL", "ani@mail.com")
    password = os.environ["DEMO_PASSWORD"]
    statuses = []
    with httpx.Client(base_url=base_url, timeout=10) as client:
        for number in range(1, 6):
            status = login(client, email, "password-salah").status_code
            statuses.append(status)
            print(f"password salah ke-{number} -> {status}")
        blocked = login(client, email, password)
    print(f"password BENAR     -> {blocked.status_code}  Retry-After: {blocked.headers.get('retry-after')}")
    if blocked.status_code == 429:
        print(f"Pesan              : {blocked.json()['error']['message']}")
    ok = statuses == [401] * 5 and blocked.status_code == 429
    print("LULUS: akun dikunci sementara walau password benar" if ok else "GAGAL: batas login tidak bekerja")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
