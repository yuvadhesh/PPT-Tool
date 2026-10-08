import socket
from urllib.parse import urlparse
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "accessppt",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.analysis_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600 * 24,  # 24 hours
    broker_connection_retry_on_startup=False,
    broker_connection_max_retries=1,
    broker_connection_timeout=0.5,
    task_routes={
        "app.tasks.analysis_tasks.analyze_presentation": {"queue": "analysis"},
        "app.tasks.analysis_tasks.apply_safe_fixes": {"queue": "remediation"},
        "app.tasks.analysis_tasks.generate_report": {"queue": "reports"},
    },
)


def is_celery_available() -> bool:
    """Quickly check if the Celery Redis broker is responding."""
    try:
        parsed = urlparse(settings.CELERY_BROKER_URL)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False
