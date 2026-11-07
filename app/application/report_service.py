"""Application: use case report penjualan.

Dijalankan oleh worker Celery, bukan oleh request API.
Hitungannya dilakukan repository di database (satu query), bukan dengan memuat semua order ke Python.
"""
from app.application.ports import UnitOfWork


class ReportService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    def sales_summary(self) -> dict:
        with self.uow:
            return self.uow.orders.sales_summary()
