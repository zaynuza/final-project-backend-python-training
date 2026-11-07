"""Domain: error business logic. Setiap error punya code yang stabil untuk dibaca client."""


class DomainError(Exception):
    code = "domain_error"


class OrderCannotBeChanged(DomainError):
    code = "order_cannot_be_changed"


class UnknownCustomerType(DomainError):
    code = "unknown_customer_type"


class OutOfStock(DomainError):
    code = "out_of_stock"


class VoucherExhausted(DomainError):
    code = "voucher_exhausted"


class VoucherAlreadyExists(DomainError):
    code = "voucher_already_exists"
