"""Shared plumbing for pipeline stage tasks.

Every stage task is a thin wrapper: `PipelineTask` handles run-status
bookkeeping so the task body contains only business logic. All stages
are idempotent (skip-what's-done), which makes a run resumable by
simply starting a new one.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from celery import Task
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import AnalysisRun, Draft, Project
from app.db.models.enums import RunStage, RunStatus
from app.db.session import get_sync_session_factory

log = get_logger(__name__)


@contextmanager
def worker_session() -> Iterator[Session]:
    with get_sync_session_factory()() as session:
        yield session


class RunContext:
    """Convenience handle passed to stage bodies."""

    def __init__(self, session: Session, run: AnalysisRun):
        self.session = session
        self.run = run
        self.run_id = run.id
        self.project_id = run.project_id
        self.draft_id = run.draft_id

    @property
    def project(self) -> Project:
        return self.session.get(Project, self.project_id)

    @property
    def draft(self) -> Draft:
        return self.session.get(Draft, self.draft_id)


class PipelineTask(Task):
    """Base task that records stage/status transitions on analysis_runs."""

    #: Set by each subclass module.
    stage: RunStage | None = None

    def run_stage(self, ctx: RunContext) -> dict:  # pragma: no cover - overridden
        raise NotImplementedError

    def run(self, run_id: str) -> str:
        rid = uuid.UUID(run_id)
        with worker_session() as session:
            run = session.get(AnalysisRun, rid)
            if run is None:
                raise ValueError(f"AnalysisRun {run_id} not found")
            if run.status == RunStatus.FAILED:
                # An earlier stage in this chain already failed; do nothing.
                return run_id

            run.status = RunStatus.RUNNING
            run.stage = self.stage
            if run.started_at is None:
                run.started_at = datetime.now(UTC)
            session.commit()

            ctx = RunContext(session, run)
            try:
                summary = self.run_stage(ctx)
            except Exception as exc:
                session.rollback()
                run = session.get(AnalysisRun, rid)
                run.status = RunStatus.FAILED
                run.error = f"{self.stage}: {type(exc).__name__}: {exc}"
                run.finished_at = datetime.now(UTC)
                session.commit()
                log.error("stage_failed", stage=str(self.stage), run_id=run_id, error=str(exc))
                raise

            log.info("stage_done", stage=str(self.stage), run_id=run_id, **summary)

            if self.stage == RunStage.RECOMMENDING:
                run = session.get(AnalysisRun, rid)
                run.status = RunStatus.COMPLETED
                run.finished_at = datetime.now(UTC)
                session.commit()

        return run_id
