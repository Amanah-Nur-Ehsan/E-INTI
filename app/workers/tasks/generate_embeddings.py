from app.db.models.enums import RunStage
from app.workers.celery_app import celery_app
from app.workers.tasks.base import PipelineTask, RunContext


class GenerateEmbeddingsTask(PipelineTask):
    name = "pipeline.generate_embeddings"
    stage = RunStage.EMBEDDING

    def run_stage(self, ctx: RunContext) -> dict:
        from app.services.embedding_service import embed_project_references

        return embed_project_references(ctx.session, ctx.project_id)


generate_embeddings = celery_app.register_task(GenerateEmbeddingsTask())
