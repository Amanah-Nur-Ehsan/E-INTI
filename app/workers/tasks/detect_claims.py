from app.db.models.enums import RunStage
from app.workers.celery_app import celery_app
from app.workers.tasks.base import PipelineTask, RunContext


class DetectClaimsTask(PipelineTask):
    name = "pipeline.detect_claims"
    stage = RunStage.DETECTING

    def run_stage(self, ctx: RunContext) -> dict:
        from app.services.claim_detection_service import detect_and_store_claims

        return detect_and_store_claims(ctx.session, ctx.draft_id)


detect_claims = celery_app.register_task(DetectClaimsTask())
