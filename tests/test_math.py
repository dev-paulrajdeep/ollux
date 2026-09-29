"""Tests for conservative LaTeX → Unicode math conversion."""

from ollux.math import convert_math


def test_simple_greek():
    assert convert_math(r"\alpha + \beta = \gamma") == "α + β = γ"


def test_operators():
    assert convert_math(r"a \leq b \geq c \neq d") == "a ≤ b ≥ c ≠ d"
    assert convert_math(r"x \rightarrow y \times z") == "x → y × z"
    assert convert_math(r"\partial \nabla \infty \pm") == "∂ ∇ ∞ ±"


def test_sum_int():
    assert convert_math(r"\sum \int") == "Σ ∫"


def test_sqrt_simple():
    assert convert_math(r"\sqrt{x}") == "√x"
    assert convert_math(r"\sqrt{a+b}") == "√a+b"


def test_frac_simple():
    assert convert_math(r"\frac{a}{b}") == "a/b"
    assert convert_math(r"\frac{1}{2}") == "1/2"


def test_frac_with_greek_becomes_unicode_ratio():
    # Commands run before frac, so this is a safe simple conversion.
    assert convert_math(r"\frac{\alpha}{b}") == "α/b"


def test_frac_nested_not_aggressively_flattened():
    src = r"\frac{\frac{a}{b}}{c}"
    out = convert_math(src)
    # Inner simple frac may convert; do not flatten to a/b/c
    assert out != "a/b/c"
    assert "\\frac" in out or out == src


def test_latex_mode_noop():
    src = r"\alpha \frac{a}{b}"
    assert convert_math(src, mode="latex") == src


def test_varepsilon_before_epsilon():
    assert convert_math(r"\varepsilon") == "ε"
    assert convert_math(r"\epsilon") == "ε"


def test_unwrap_simple_delimiters():
    assert convert_math(r"\(\alpha\)") == "α"
    assert "β" in convert_math(r"\[\beta\]")
