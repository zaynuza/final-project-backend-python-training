"""Data contoh untuk demo: 3 produk. Dijalankan sekali setelah user admin dibuat (idempotent: tidak menambah dua kali).

Jalankan (API harus sudah hidup):
    BASE_URL=http://localhost:8000 SMOKE_EMAIL=admin@toko.com SMOKE_PASSWORD=... python demo_data.py
Voucher sengaja tidak dibuat di sini: membuat voucher adalah bagian dari demo fitur.
"""
import os

import httpx

PRODUCTS = [
    {"name": "Keyboard", "price": 500_000, "stock": 10},
    {"name": "Mouse", "price": 100_000, "stock": 20},
    {"name": "Monitor", "price": 2_000_000, "stock": 5},
]


def main() -> None:
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    email, password = os.environ["SMOKE_EMAIL"], os.environ["SMOKE_PASSWORD"]
    with httpx.Client(base_url=base_url, timeout=10) as client:
        login = client.post("/auth/token", data={"username": email, "password": password})
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        if client.get("/products").json():
            print("Produk sudah ada, tidak ditambah lagi.")
            return
        for product in PRODUCTS:
            created = client.post("/products", json=product, headers=headers)
            created.raise_for_status()
            print(f"Produk #{created.json()['id']}: {product['name']}, Rp{product['price']:,}, stok {product['stock']}")


if __name__ == "__main__":
    main()
