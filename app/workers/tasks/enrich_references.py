from app.db.models.enums import RunStage
from app.workers.celery_app import celery_app
from app.workers.tasks.base import PipelineTask, RunContext


class EnrichReferencesTask(PipelineTask):
    name = "pipeline.enrich_references"
    stage = RunStage.ENRICHING

    def run_stage(self, ctx: RunContext) -> dict:
        from app.services.enrichment import enrich_project_references

        return enrich_project_references(ctx.session, ctx.project_id)


enrich_references = celery_app.register_task(EnrichReferencesTask())
