import pytest

from app.services.draft_parser_service import (
    normalize_paragraph,
    parse_file,
    segment,
)
from tests.conftest import FIXTURES


@pytest.fixture(scope="module")
def parsed_docx():
    return parse_file(FIXTURES / "sample_draft.docx")


def test_normalize_collapses_whitespace_and_nbsp():
    assert normalize_paragraph("  a b\tc  \r\n") == "a b c"


@pytest.mark.parametrize("filename", ["sample_draft.docx", "sample_draft.md", "sample_draft.txt"])
def test_block_offsets_slice_back_to_block_text(filename):
    """The invariant every downstream char offset depends on."""
    parsed = parse_file(FIXTURES / filename)
    assert parsed.blocks
    for block in parsed.blocks:
        assert parsed.raw_text[block.char_start : block.char_end] == block.text


@pytest.mark.parametrize("filename", ["sample_draft.docx", "sample_draft.md", "sample_draft.txt"])
def test_sentence_offsets_slice_back_to_sentence_text(filename):
    parsed = parse_file(FIXTURES / filename)
    assert parsed.sentences
    for sentence in parsed.sentences:
        assert parsed.raw_text[sentence.char_start : sentence.char_end] == sentence.text


def test_headings_become_section_titles(parsed_docx):
    body = [b for b in parsed_docx.blocks if not b.is_heading]
    sections = {b.section_title for b in body}
    assert {"Introduction", "Related Work", "Methodology", "Results"} <= sections


def test_headings_are_not_segmented_into_sentences(parsed_docx):
    assert "Introduction" not in {s.text for s in parsed_docx.sentences}


def test_et_al_does_not_split_a_sentence(parsed_docx):
    joined = [s.text for s in parsed_docx.sentences]
    target = [s for s in joined if "Smith et al. (2024)" in s]
    assert len(target) == 1
    assert target[0].startswith("According to Smith et al. (2024)")
    assert target[0].endswith("unseen fraud schemes.")


def test_eg_abbreviation_does_not_split(parsed_docx):
    target = [s.text for s in parsed_docx.sentences if "e.g." in s.text]
    assert len(target) == 1
    assert "retraining cycles fall behind" in target[0]


def test_decimal_numbers_do_not_split():
    from app.services.draft_parser_service import ParsedDraft, _assemble

    parsed = _assemble([("Adaptive retraining raised recall by 8.4 percent overall.", False, None)])
    sentences = segment(parsed)
    assert len(sentences) == 1
    assert isinstance(parsed, ParsedDraft)


def test_sentences_carry_paragraph_and_section(parsed_docx):
    first = parsed_docx.sentences[0]
    assert first.section_title == "Introduction"
    assert first.sentence_index == 0
    assert first.text.startswith("Machine learning techniques have improved")


def test_local_context_window(parsed_docx):
    from app.services.draft_parser_service import local_context

    context = local_context(parsed_docx.sentences, 1)
    assert parsed_docx.sentences[0].text in context
    assert parsed_docx.sentences[1].text in context
    assert parsed_docx.sentences[2].text in context


def test_unsupported_format_rejected(tmp_path):
    bad = tmp_path / "draft.pdf"
    bad.write_bytes(b"%PDF-1.4")
    with pytest.raises(ValueError, match="Unsupported draft format"):
        parse_file(bad)
