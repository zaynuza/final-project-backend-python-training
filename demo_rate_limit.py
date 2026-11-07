"""Demo rate limit untuk presentasi: kirim request ke endpoint publik sampai server menjawab 429.

Jalankan (API harus sudah hidup):
    BASE_URL=http://localhost:8000 python demo_rate_limit.py
Batasnya 20 request per 60 detik per IP (RATE_LIMIT, RATE_LIMIT_WINDOW) dan dihitung bersama untuk /orders,
/reports, dan /products/best-sellers. Request ke-N yang ditolak bergantung pada berapa request yang sudah
dikirim dalam semenit terakhir. Untuk hasil bersih (ke-21), kosongkan Redis dulu:
    docker compose exec redis redis-cli -n 2 FLUSHDB
Exit code 1 kalau sampai 30 request server tidak pernah menjawab 429.
"""
import os
import sys

import httpx


def main() -> None:
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    with httpx.Client(base_url=base_url, timeout=10) as client:
        for number in range(1, 31):
            response = client.get("/products/best-sellers")
            if response.status_code == 429:
                print(f"request ke-{number} -> 429 Too Many Requests")
                print(f"Retry-After          : {response.headers['retry-after']} detik")
                print(f"X-RateLimit-Limit    : {response.headers['x-ratelimit-limit']}")
                print(f"X-RateLimit-Remaining: {response.headers['x-ratelimit-remaining']}")
                print(f"Pesan                : {response.json()['error']['message']}")
                print("LULUS: kelebihan request ditolak, bukan dilayani")
                return
        print("GAGAL: 30 request tidak pernah ditolak, cek RATE_LIMIT")
        sys.exit(1)


if __name__ == "__main__":
    main()
