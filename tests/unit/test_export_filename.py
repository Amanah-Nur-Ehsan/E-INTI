import pytest

from app.services.export import _display_filename


@pytest.mark.parametrize(
    "original_filename,extension,expected",
    [
        ("Fraud Detection Paper.docx", "docx", "[INTI] Fraud Detection Paper.docx"),
        # Extension comes from the generated export, not the source draft --
        # a .md draft can still be exported as .docx.
        ("notes.md", "docx", "[INTI] notes.docx"),
        (None, "docx", "[INTI] paper.docx"),
        ("", "docx", "[INTI] paper.docx"),
        # Path.stem already discards any directory components (forward
        # slashes), so a POSIX-style traversal attempt collapses to just
        # its basename before sanitisation ever runs.
        ("../../etc/passwd", "docx", "[INTI] passwd.docx"),
        # Backslashes aren't a path separator to Path.stem on POSIX, so
        # they survive to reach the sanitiser, which is what strips them.
        ("weird\\name", "docx", "[INTI] weird_name.docx"),
        ("weird\x00name.docx", "docx", "[INTI] weird_name.docx"),
    ],
)
def test_display_filename(original_filename, extension, expected):
    assert _display_filename(original_filename, extension) == expected
