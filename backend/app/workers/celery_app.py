"""Celery application.

Scheduler (Beat) reference in IST: the daily eligibility scan recomputes
ages from DOB and diffs results for new notifications; the deadline job
reminds eligible users 7/3/1 days ahead. Every queued message is drained
by ``send_notification`` individually with retry/backoff.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "schemeping",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "daily-eligibility-scan": {
            # 07:30 IST, before quiet-hr window really matters; the scan diffs
            # newly eligible people and queues their notifications.
            "task": "app.workers.tasks.daily_eligibility_scan",
            "schedule": crontab(hour=7, minute=30),
        },
        "deadline-reminders": {
            "task": "app.workers.tasks.deadline_reminders",
            "schedule": crontab(hour=10, minute=0),
        },
        "purge-chat-history": {
            # Chat transcripts are kept briefly (default 14 days).
            "task": "app.workers.tasks.purge_chat_history",
            "schedule": crontab(hour=3, minute=15),
        },
    },
)
