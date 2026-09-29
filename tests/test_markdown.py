"""Tests for Markdown normalization and fenced-code preservation."""

from ollux.markdown import normalize_markdown


def test_collapse_blank_lines():
    src = "Hello\n\n\n\nWorld\n"
    out = normalize_markdown(src, math_mode="latex")
    assert out == "Hello\n\nWorld\n"


def test_strip_trailing_whitespace():
    src = "line  \nnext\n"
    out = normalize_markdown(src, math_mode="latex")
    assert "  \n" not in out
    assert "line\nnext\n" == out


def test_strip_think_blocks():
    src = "Intro\n<think>\nsecret chain\n</think>\n## Answer\nDone\n"
    out = normalize_markdown(src, math_mode="latex")
    assert "secret" not in out
    assert "## Answer" in out
    assert "Done" in out


def test_code_fence_preserved_exactly():
    code = "```python\n\\alpha = 1\n  spaced  \n\n\n\nmore\n```"
    src = f"Before\n\n{code}\n\nAfter \\alpha\n"
    out = normalize_markdown(src, math_mode="unicode")
    assert "```python\n\\alpha = 1\n  spaced  \n\n\n\nmore\n```" in out
    assert "After α" in out


def test_tilde_fence_preserved():
    src = "~~~\n\\beta = 2\n~~~\n\n\\beta outside\n"
    out = normalize_markdown(src, math_mode="unicode")
    assert "\\beta = 2" in out
    assert "β outside" in out


def test_math_outside_code():
    src = "The value is \\lambda.\n"
    out = normalize_markdown(src, math_mode="unicode")
    assert "λ" in out


def test_no_paraphrase():
    src = "Eigenvalues are roots of det(A - \\lambda I) = 0.\n"
    out = normalize_markdown(src, math_mode="unicode")
    assert "Eigenvalues are roots of det(A - λ I) = 0." in out


def test_empty():
    assert normalize_markdown("") == ""
