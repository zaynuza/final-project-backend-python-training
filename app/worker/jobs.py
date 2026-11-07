"""Worker: memulai job report dan membaca statusnya dari result backend."""
from celery.result import AsyncResult

from app.worker.celery_app import celery_app
from app.worker.tasks import generate_sales_report

STATUS = {"PENDING": "pending", "STARTED": "running", "RETRY": "retrying",
          "SUCCESS": "done", "FAILURE": "failed"}


def start_sales_report() -> str:
    return generate_sales_report.delay().id


def get_job_status(task_id: str) -> dict:
    result = AsyncResult(task_id, app=celery_app)
    return {
        "task_id": task_id,
        "status": STATUS.get(result.state, result.state.lower()),
        "result": result.result if result.successful() else None,
        "error": str(result.result) if result.failed() else None,
    }
