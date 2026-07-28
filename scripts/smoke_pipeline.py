"""Run the whole pipeline on the fixture data with the real local models.

Mocks stand in for Scopus and the LLMs (no API keys needed), but SPECTER2
and the cross-encoder are the real thing, so this is the check that the
retrieval stack actually behaves on this machine.

    make smoke
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("USE_MOCK_PROVIDERS", "true")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ["EMBEDDING_FAKE"] = "false"
os.environ["RERANKER_FAKE"] = "false"

FIXTURES = ROOT / "tests" / "fixtures"
BAR_WIDTH = 24


def bar(percentage: float) -> str:
    filled = round(percentage / 100 * BAR_WIDTH)
    return "█" * filled + "·" * (BAR_WIDTH - filled)


async def main() -> int:
    import httpx

    from app.core.device import get_device
    from app.main import app

    print(f"device: {get_device()}")
    print("loading models (first run downloads a few hundred MB)...\n")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://smoke", timeout=600) as c:
        project = (
            await c.post(
                "/api/v1/projects",
                json={"name": "Smoke test", "field_of_study": "Computer Science"},
            )
        ).json()
        project_id = project["id"]

        await c.post(
            f"/api/v1/projects/{project_id}/drafts/upload",
            files={"file": ("sample_draft.docx", (FIXTURES / "sample_draft.docx").read_bytes())},
        )
        imported = (
            await c.post(
                f"/api/v1/projects/{project_id}/references/import",
                files={
                    "file": (
                        "sample_dataset.xlsx",
                        (FIXTURES / "sample_dataset.xlsx").read_bytes(),
                    )
                },
            )
        ).json()
        print(f"imported {imported['imported']} references")

        run = await c.post(f"/api/v1/projects/{project_id}/analysis/run", json={})
        if run.status_code != 202:
            print(f"analysis failed to start: {run.status_code} {run.text}")
            return 1

        status = (await c.get(f"/api/v1/projects/{project_id}/analysis/status")).json()
        print(
            f"run {status['status']}  references: {status['references']['enriched']} enriched, "
            f"{status['references']['embedded']} embedded, "
            f"{status['references']['incomplete']} incomplete"
        )
        if status["status"] != "COMPLETED":
            print(f"error: {status['error']}")
            return 1

        draft_id = status["draft_id"]
        claims = (
            await c.get(f"/api/v1/drafts/{draft_id}/claims?needs_citation=true")
        ).json()
        print(f"claims needing citation: {len(claims)}\n")

        for claim in claims:
            section = claim["section_title"] or "-"
            print(f"[{section}] {claim['sentence_text']}")
            recs = (await c.get(f"/api/v1/claims/{claim['id']}/recommendations")).json()
            if not recs:
                print("    (no candidates)\n")
                continue
            for rec in recs:
                reference = rec["reference"]
                year = reference["year"] or "n.d."
                print(
                    f"    {rec['score_percentage']:5.1f}% {bar(rec['score_percentage'])} "
                    f"{rec['verdict']:<34} {reference['title'][:52]} ({year})"
                )
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
