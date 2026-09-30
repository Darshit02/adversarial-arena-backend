"""Celery application configuration for background benchmark execution."""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "adversarial_arena",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_acks_late=settings.CELERY_TASK_ACKS_LATE,
    worker_prefetch_multiplier=settings.CELERY_WORKER_PREFETCH_MULTIPLIER,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=1500,
    result_expires=86400,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery_app.autodiscover_tasks(["app.workers.tasks"])
