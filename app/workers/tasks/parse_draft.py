from app.db.models.enums import RunStage
from app.workers.celery_app import celery_app
from app.workers.tasks.base import PipelineTask, RunContext


class ParseDraftTask(PipelineTask):
    name = "pipeline.parse_draft"
    stage = RunStage.PARSING

    def run_stage(self, ctx: RunContext) -> dict:
        from app.services.draft_parser_service import parse_and_store_draft

        return parse_and_store_draft(ctx.session, ctx.draft_id)


parse_draft = celery_app.register_task(ParseDraftTask())
