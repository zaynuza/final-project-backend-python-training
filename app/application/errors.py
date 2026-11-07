"""Application: error dari use case."""


class NotFound(Exception):
    code = "not_found"


class OrderNotFound(NotFound):
    code = "order_not_found"


class ProductNotFound(NotFound):
    code = "product_not_found"


class VoucherNotFound(NotFound):
    code = "voucher_not_found"


class InvalidEvent(Exception):
    """Isi event tidak sesuai format. Dicoba ulang pun tetap gagal."""


class InvalidCredentials(Exception):
    """Email atau password salah. Pesannya sengaja sama untuk keduanya."""
    code = "invalid_credentials"


class TooManyLoginAttempts(Exception):
    """Login gagal terlalu sering untuk email ini. Login ditolak (walau password benar) sampai blokir selesai."""
    code = "too_many_login_attempts"

    def __init__(self, retry_after: int):
        super().__init__(f"Terlalu banyak login gagal, coba lagi dalam {retry_after} detik")
        self.retry_after = retry_after


class InvalidToken(Exception):
    """Token tidak ada, salah tanda tangan, atau kedaluwarsa."""
    code = "invalid_token"


class AccessDenied(Exception):
    """User sudah login, tetapi tidak punya scope untuk aksi ini."""
    code = "forbidden"


class UserAlreadyExists(Exception):
    code = "user_already_exists"

