from celery import Celery

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()

celery_app = Celery(
    "citationinti",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.tasks.refresh_library",
        "app.workers.tasks.parse_draft",
        "app.workers.tasks.classify_sdg",
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
    # worker_max_tasks_per_child is prefork-only and is silently ignored
    # under --pool=threads (the worker command in docker-compose.yml) --
    # left here as documentation of a real gap (no leak-driven recycling
    # under threads), not because it does anything. Restart the worker
    # periodically instead if that ever becomes a problem in practice.
    worker_max_tasks_per_child=200,
    broker_connection_retry_on_startup=True,
    # One task claimed per worker slot rather than prefetched ahead --
    # with --concurrency=2 threads, prefetching would let one slow
    # analysis hoard a second task's slot before the first is anywhere
    # near actually running it.
    worker_prefetch_multiplier=1,
)

configure_logging()
