"""Rewrites a claim's paragraph to weave in a chosen citation.

The citation itself is never left to the model to format -- the in-text
string and bibliography entry are deterministic output from
citation_formatting_service, computed before this call ever runs. The
model's only job is inserting that exact string at the natural point in
the paragraph without changing what it says.
"""

from pydantic import BaseModel

from app.services.llm_client import Tier, get_llm_client

REWRITE_SYSTEM = (
    "You edit one paragraph from an academic paper so it cites a specific "
    "source. You are given the paragraph, the sentence within it that makes "
    "the claim needing a citation, and the exact citation string to insert "
    "(already correctly formatted -- do not reformat, translate, or invent "
    "a different one). Insert that exact citation string at the natural "
    "point in the sentence, usually right after the claim, rewording only "
    "as much as grammar requires to fit it in smoothly. Do not change what "
    "the paragraph says, add new claims, or remove any other sentence. "
    "Return JSON only."
)

REWRITE_USER_TEMPLATE = """PARAGRAPH: {paragraph}
SENTENCE: {sentence}
CITATION: {citation}

Respond with: {{"paragraph": "<the full paragraph, with the citation inserted>"}}"""


class ParagraphRewrite(BaseModel):
    paragraph: str


def rewrite_paragraph(paragraph: str, sentence: str, citation: str) -> str:
    """`paragraph` is expected to be claim.local_context, `sentence` is
    claim.sentence_text, and `citation` is the pre-formatted in-text string
    for the chosen reference (e.g. "(Smith & Doe, 2023)" or "[1]").
    """
    client = get_llm_client()
    user = REWRITE_USER_TEMPLATE.format(paragraph=paragraph, sentence=sentence, citation=citation)
    result = client.complete_structured(
        tier=Tier.CLASSIFY, system=REWRITE_SYSTEM, user=user, schema=ParagraphRewrite
    )
    return result.paragraph
