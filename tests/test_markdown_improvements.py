import re
from ollux.markdown import _normalize_whitespace, normalize_markdown, _protect_code, _restore_code

def test_html_protection():
    src = "Press <kbd>Ctrl</kbd> + <kbd>C</kbd>."
    out = normalize_markdown(src, math_mode="unicode")
    assert out.strip() == "Press <kbd>Ctrl</kbd> + <kbd>C</kbd>."

def test_blockquote_normalization():
    src = "> Line 1\n>\n> Line 2\n"
    out = normalize_markdown(src, math_mode="unicode")
    assert out.strip() == "> Line 1\n>\n> Line 2"

def test_list_normalization():
    src = "- Item 1\n  - Subitem 1\n  - Subitem 2\n- Item 2\n"
    out = normalize_markdown(src, math_mode="unicode")
    assert out.strip() == "- Item 1\n  - Subitem 1\n  - Subitem 2\n- Item 2"

def test_table_protection():
    src = "| A | B |\n|---|---|\n| 1 | 2 |\n"
    out = normalize_markdown(src, math_mode="unicode")
    assert out.strip() == "| A | B |\n|---|---|\n| 1 | 2 |"

if __name__ == "__main__":
    import pytest
    pytest.main(["test_markdown_improvements.py"])
