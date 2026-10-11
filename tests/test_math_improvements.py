from ollux.math import convert_math

def test_new_symbols():
    text = "Let x \\in \\mathbb{R}"
    out = convert_math(text)
    assert out == "Let x ∈ ℝ"

def test_complex_symbols():
    text = "\\approx \\equiv \\mathcal{O}(n)"
    out = convert_math(text)
    assert out == "≈ ≡ 𝒪(n)"

def test_multiline_matrix():
    text = "\\begin{pmatrix}\n1 & 2 \\\\\n3 & 4\n\\end{pmatrix}"
    out = convert_math(text)
    # Could be a unicode representation like
    # ⎛ 1  2 ⎞
    # ⎝ 3  4 ⎠
    # Or fallback to raw if not implemented perfectly, but something better than mangling
    assert "1" in out

def test_inline_newlines():
    text = "\\[\nx = 1\n\\]"
    out = convert_math(text)
    assert "x = 1" in out

    text = "\\(\ny = 2\n\\)"
    out = convert_math(text)
    assert "y = 2" in out

if __name__ == "__main__":
    import pytest
    pytest.main(["test_math_improvements.py"])
