"""Worker: task Celery.

Task adalah pintu masuk seperti route di api/: menerima job, memanggil use case atau adapter, selesai.
- generate_sales_report : dihitung di database, tetap dibatasi time limit
Notifikasi tidak lagi lewat Celery. Sekarang dikirim oleh consumer RabbitMQ (app/consumers/).
AlertingTask memastikan retry dan kegagalan permanen selalu tercatat di log worker.
"""
from celery import Task
from celery.utils.log import get_task_logger

from app.application.report_service import ReportService
from app.infrastructure.database import get_session_factory
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.worker.celery_app import celery_app

logger = get_task_logger(__name__)


class AlertingTask(Task):
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning("%s retry ke-%s: %s", self.name, self.request.retries + 1, exc)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        # di aplikasi nyata: kirim alert ke Slack/Sentry atau simpan ke tabel failed_jobs
        logger.error("[ALERT] %s gagal permanen (task_id=%s, args=%s): %s", self.name, task_id, args, exc)


@celery_app.task(base=AlertingTask, soft_time_limit=120, time_limit=150)
def generate_sales_report() -> dict:
    return ReportService(SqlAlchemyUnitOfWork(get_session_factory())).sales_summary()
