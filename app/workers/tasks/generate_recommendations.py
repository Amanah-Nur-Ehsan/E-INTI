from app.db.models.enums import RunStage
from app.workers.celery_app import celery_app
from app.workers.tasks.base import PipelineTask, RunContext


class GenerateRecommendationsTask(PipelineTask):
    name = "pipeline.generate_recommendations"
    stage = RunStage.RECOMMENDING

    def run_stage(self, ctx: RunContext) -> dict:
        from app.services.recommendation_pipeline import recommend_for_draft

        return recommend_for_draft(ctx.session, ctx.draft_id)


generate_recommendations = celery_app.register_task(GenerateRecommendationsTask())
