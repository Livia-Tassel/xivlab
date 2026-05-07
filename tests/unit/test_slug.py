"""Tests for the slugify helper.

Pure-function tests; no DB / no async. Covers ASCII alphanumerics,
CJK preservation (Chinese ideographs in the BMP), separator collapse,
length cap, and the all-stripped-out fallback.
"""

from app.services.slug import slugify


def test_slugify_lowercases_and_separates_words() -> None:
    assert slugify("Hello World!") == "hello-world"


def test_slugify_collapses_runs_of_separators() -> None:
    assert slugify("a    b---c__d") == "a-b-c-d"


def test_slugify_strips_leading_and_trailing_separators() -> None:
    assert slugify("  -hello-  ") == "hello"


def test_slugify_preserves_cjk_characters() -> None:
    """Chinese ideographs in the BMP must survive (a-z0-9 ASCII alone isn't enough)."""
    out = slugify("论文写作 prompt")
    # Exact form: ideographs joined with prompt via "-"
    assert "论文写作" in out
    assert "prompt" in out
    assert "-" in out


def test_slugify_truncates_to_max_len() -> None:
    long = "a" * 200
    out = slugify(long, max_len=80)
    assert len(out) == 80


def test_slugify_falls_back_to_default_when_input_empties() -> None:
    """All-punctuation input would slug to the empty string; we return 'prompt' instead."""
    assert slugify("!!!") == "prompt"
    assert slugify("") == "prompt"
    assert slugify("   ") == "prompt"


def test_slugify_default_max_len_is_80() -> None:
    long = "a" * 200
    assert len(slugify(long)) == 80
