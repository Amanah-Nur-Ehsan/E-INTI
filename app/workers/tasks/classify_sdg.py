from app.db.models.enums import RunStage
from app.workers.celery_app import celery_app
from app.workers.tasks.base import PipelineTask, RunContext


class ClassifySDGTask(PipelineTask):
    name = "pipeline.classify_sdg"
    stage = RunStage.CLASSIFYING_SDG

    def run_stage(self, ctx: RunContext) -> dict:
        from app.services.sdg_classification_service import classify_draft

        return classify_draft(ctx.session, ctx.draft)


classify_sdg = celery_app.register_task(ClassifySDGTask())
