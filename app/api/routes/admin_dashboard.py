from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import SessionDep, require_any_admin
from app.core.config import get_settings
from app.db.models import AnalysisRun, User
from app.db.models.enums import RunStatus, UserRole
from app.schemas.admin_dashboard import AdminOverview, AppStatus, UserCounts
from app.services.progress import reference_counts

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_any_admin)])


@router.get("/overview", response_model=AdminOverview)
async def admin_overview(session: SessionDep) -> AdminOverview:
    """Dashboard numbers: user counts, library enrichment state, and app
    status (environment, in-flight/last analysis run)."""
    settings = get_settings()

    total_users = (await session.scalar(select(func.count()).select_from(User))) or 0
    active_users = (
        await session.scalar(
            select(func.count()).select_from(User).where(User.is_active.is_(True))
        )
    ) or 0
    admin_users = (
        await session.scalar(
            select(func.count()).select_from(User).where(User.role == UserRole.ADMIN)
        )
    ) or 0

    active_analyses = (
        await session.scalar(
            select(func.count())
            .select_from(AnalysisRun)
            .where(AnalysisRun.status.in_([RunStatus.PENDING, RunStatus.RUNNING]))
        )
    ) or 0

    last_run = (
        await session.execute(
            select(AnalysisRun).order_by(AnalysisRun.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()

    return AdminOverview(
        users=UserCounts(total=total_users, active=active_users, admins=admin_users),
        library=await reference_counts(session),
        app=AppStatus(
            environment=settings.environment,
            active_analyses=active_analyses,
            last_run_status=last_run.status if last_run else None,
            last_run_stage=last_run.stage if last_run else None,
            last_run_started_at=last_run.started_at if last_run else None,
            last_run_finished_at=last_run.finished_at if last_run else None,
            last_run_error=last_run.error if last_run else None,
        ),
    )
