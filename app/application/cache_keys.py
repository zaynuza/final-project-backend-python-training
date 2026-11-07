"""Application: nama cache key di satu tempat.

Dipakai oleh ProductService (mengisi cache) dan Unit of Work (menghapus cache setelah commit).
Naikkan versi (v1 -> v2) kalau bentuk data yang di-cache berubah.
"""
PRODUCT_LIST_KEY = "v1:products:list"
BEST_SELLERS_KEY = "v1:products:best-sellers"   # selalu top 10, dipotong sesuai limit


def product_key(product_id: int) -> str:
    return f"v1:product:{product_id}"
