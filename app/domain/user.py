"""Domain: user dan hak aksesnya (RBAC).

Setiap role punya daftar scope. Scope = izin untuk satu jenis aksi.
    customer : membuat dan mengelola order miliknya sendiri
    admin    : + mengelola order semua customer, mengubah produk, melihat report
customer_type (regular/member/vip) disimpan di data user, bukan dikirim client,
supaya customer tidak bisa memilih diskonnya sendiri.
"""
from dataclasses import dataclass

ROLE_SCOPES = {
    "customer": {"orders:write"},
    "admin": {"orders:write", "orders:all", "products:write", "reports:read"},
}


@dataclass
class User:
    email: str
    password_hash: str
    role: str = "customer"
    customer_type: str = "regular"
    id: int | None = None

    def __post_init__(self):
        if self.role not in ROLE_SCOPES:
            raise ValueError(f"Role {self.role} tidak dikenal")

    @property
    def scopes(self) -> set[str]:
        return ROLE_SCOPES[self.role]
