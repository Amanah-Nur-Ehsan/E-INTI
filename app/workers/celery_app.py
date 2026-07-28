from celery import Celery

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()

celery_app = Celery(
    "citationinti",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.tasks.enrich_references",
        "app.workers.tasks.generate_embeddings",
        "app.workers.tasks.parse_draft",
        "app.workers.tasks.detect_claims",
        "app.workers.tasks.generate_recommendations",
    ],
)

celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_max_tasks_per_child=200,
    broker_connection_retry_on_startup=True,
)

configure_logging()
