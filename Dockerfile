# Order API - image production (multi-stage)
# Satu image dipakai untuk API, worker Celery, dan consumer notifikasi.
# Yang berbeda hanya perintah yang dijalankan (lihat docker-compose.yml dan k8s/).

# Stage 1: install dependency ke virtualenv
FROM python:3.12-slim AS builder

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Stage 2: image akhir, tanpa pip cache dan tanpa dependency development
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY app ./app
COPY create_user.py seed.py ./

# uid tetap supaya bisa dicek Kubernetes (runAsNonRoot)
RUN useradd --create-home --uid 10001 appuser
USER 10001

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
