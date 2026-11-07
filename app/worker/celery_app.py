"""Worker: konfigurasi Celery.

Broker (queue job) dan result backend (status & hasil job) memakai Redis.

Jalankan worker dari folder starter/:
    celery -A app.worker.celery_app worker --loglevel=info --pool=solo
"""
from celery import Celery

from app.infrastructure.config import get_settings

settings = get_settings()

celery_app = Celery("order_api", broker=settings.broker_url, backend=settings.result_backend,
                    include=["app.worker.tasks"])
celery_app.conf.update(
    task_track_started=True,          # status "running" saat worker mulai mengerjakan
    task_acks_late=True,              # job dihapus dari queue setelah selesai, bukan saat diambil
    worker_prefetch_multiplier=1,     # worker mengambil satu job setiap kali
    result_expires=24 * 3600,         # status & hasil disimpan 1 hari
    task_always_eager=settings.task_always_eager,
    task_store_eager_result=True,     # mode eager tetap mencatat status, supaya bisa dicek lewat API
)
