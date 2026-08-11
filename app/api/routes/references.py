"""Reference library routes, split across two routers by who may call them.

`router` is public: `GET /library/status` is polled by the unauthenticated
main page (it leaks only aggregate counts), so it must NOT sit behind
`require_admin`. Everything else here is an admin action (importing the
dataset, triggering enrichment, listing/browsing raw rows, downloading the
missing-abstracts template) and lives on `admin_router`, which carries
`dependencies=[Depends(require_admin)]` at the router level rather than
per-route -- a per-route decorator is one forgotten annotation away from
an open admin endpoint; a router-level dependency can't be forgotten on a
route added later.
"""

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import case, func, select

from app.api.deps import SessionDep
from app.core.security import require_admin
from app.core.uploads import read_upload_capped
from app.db.models import ReferencePaper
from app.schemas.analysis import ReferenceCounts
from app.schemas.reference import ImportResult, MissingAbstractsByYear, ReferenceRead
from app.services.dataset_import_service import DatasetSchemaError, import_dataset
from app.services.progress import reference_counts

router = APIRouter(prefix="/library", tags=["library"])
admin_router = APIRouter(
    prefix="/library", tags=["library"], dependencies=[Depends(require_admin)]
)


@router.get("/status", response_model=ReferenceCounts)
async def references_status(session: SessionDep) -> ReferenceCounts:
    return await reference_counts(session)


@admin_router.post("/import", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
async def import_references(session: SessionDep, file: UploadFile = File(...)) -> ImportResult:
    content = await read_upload_capped(file)

    # The importer is sync (shared with worker code); run it on the sync engine.
    from app.db.session import get_sync_session_factory

    try:
        with get_sync_session_factory()() as sync_session:
            summary = import_dataset(sync_session, content, file.filename or "upload.xlsx")
    except DatasetSchemaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    return ImportResult(**summary.__dict__)


@admin_router.post("/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_library() -> dict:
    """Kick off enrichment-then-embedding for every pending library row.

    Not tied to an AnalysisRun -- the library is maintained on its own
    schedule, separate from any particular draft's analysis.
    """
    from app.workers.tasks.refresh_library import refresh_library as refresh_task

    async_result = refresh_task.delay()
    return {"task_id": async_result.id}


@admin_router.get("/missing-abstracts-by-year", response_model=list[MissingAbstractsByYear])
async def missing_abstracts_by_year(session: SessionDep) -> list[MissingAbstractsByYear]:
    """Where to focus manual abstract collection: which publication years
    have the most references still missing an abstract, so a user filling
    them in by hand (or re-exporting from Scopus) knows where to start.
    """
    missing_expr = func.sum(case((ReferencePaper.abstract.is_(None), 1), else_=0))
    stmt = (
        select(
            ReferencePaper.year,
            missing_expr.label("missing"),
            func.count().label("total"),
        )
        .group_by(ReferencePaper.year)
        .having(missing_expr > 0)
        .order_by(missing_expr.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        MissingAbstractsByYear(year=year, missing=missing, total=total)
        for year, missing, total in rows
    ]


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@admin_router.get("/missing-abstracts-template")
async def missing_abstracts_template(
    session: SessionDep, year: int | None = Query(default=None)
) -> Response:
    """xlsx of every reference missing an abstract for `year` (omit the
    query param for the "unknown year" bucket) -- the header row matches
    what /library/import already recognizes, so filling in ABSTRACT and
    re-uploading the same file backfills just that field via the normal
    duplicate-match path, no separate mechanism needed.

    This is a plain `<a href download>` navigation on the frontend, not a
    fetch() call -- it cannot carry a custom header, so it relies on the
    admin session cookie (SameSite=Lax still attaches on a top-level GET
    navigation) rather than any header-based auth scheme.
    """
    from app.services.missing_abstract_template import build_missing_abstract_template

    stmt = select(ReferencePaper).where(ReferencePaper.abstract.is_(None))
    stmt = (
        stmt.where(ReferencePaper.year == year)
        if year is not None
        else stmt.where(ReferencePaper.year.is_(None))
    )
    stmt = stmt.order_by(ReferencePaper.original_row_number)
    references = list((await session.execute(stmt)).scalars())

    content = build_missing_abstract_template(references)
    label = str(year) if year is not None else "unknown-year"
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="missing-abstracts-{label}.xlsx"'},
    )


@admin_router.get("", response_model=list[ReferenceRead])
async def list_references(
    session: SessionDep,
    enrichment_status: str | None = Query(default=None),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[ReferencePaper]:
    stmt = select(ReferencePaper)
    if enrichment_status:
        stmt = stmt.where(ReferencePaper.enrichment_status == enrichment_status)
    stmt = stmt.order_by(ReferencePaper.original_row_number).limit(limit).offset(offset)
    return list((await session.execute(stmt)).scalars())
