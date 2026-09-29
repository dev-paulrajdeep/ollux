"""Tests for LaTeX → Unicode math conversion and delimited math."""

from ollux.math import convert_math
from ollux.markdown import normalize_markdown


def test_simple_greek():
    assert convert_math(r"\alpha + \beta = \gamma") == "α + β = γ"


def test_operators():
    assert convert_math(r"a \leq b \geq c \neq d") == "a ≤ b ≥ c ≠ d"
    assert convert_math(r"x \rightarrow y \times z") == "x → y × z"
    assert convert_math(r"\partial \nabla \infty \pm") == "∂ ∇ ∞ ±"
    assert convert_math(r"a \parallel b") == "a ∥ b"
    assert convert_math(r"a \perp b") == "a ⟂ b"


def test_sum_int():
    assert convert_math(r"\sum \int") == "Σ ∫"


def test_sqrt_simple():
    assert convert_math(r"\sqrt{x}") == "√x"
    assert convert_math(r"\sqrt{a+b}") == "√(a+b)"


def test_frac_simple():
    assert convert_math(r"\frac{a}{b}") == "a/b"
    assert convert_math(r"\frac{1}{2}") == "1/2"


def test_tfrac_and_imath():
    assert convert_math(r"$\tfrac{1}{2}AC$") == "1/2 × AC"
    assert "ı" in convert_math(r"$\imath$")
    assert "✓" in convert_math(r"$\checkmark$")


def test_frac_juxtaposition():
    assert convert_math(r"\frac{1}{2}AC") == "1/2 × AC"
    assert convert_math(r"\frac{a}{b}x") == "(a/b) × x"


def test_overrightarrow_and_boxed():
    out = convert_math(r"\overrightarrow{PQ} = \boxed{a + b}")
    assert "PQ" in out and "⃗" in out
    assert "a + b" in out
    assert "\\boxed" not in out


def test_frac_with_greek_becomes_unicode_ratio():
    assert convert_math(r"\frac{\alpha}{b}") == "α/b"


def test_frac_nested_not_aggressively_flattened():
    src = r"\frac{\frac{a}{b}}{c}"
    out = convert_math(src)
    assert out != "a/b/c"


def test_latex_mode_noop():
    src = r"$ABCD$ $\alpha$ \frac{a}{b}"
    assert convert_math(src, mode="latex") == src
    assert "$ABCD$" in normalize_markdown(src, math_mode="latex")


def test_varepsilon_before_epsilon():
    assert convert_math(r"\varepsilon") == "ε"
    assert convert_math(r"\epsilon") == "ε"


def test_delimited_inline_dollar():
    assert convert_math("$x^2$") == "x²"
    assert convert_math("$x_i$") == "xᵢ"
    assert convert_math(r"$\alpha + \beta$") == "α + β"
    assert convert_math(r"$\sqrt{x}$") == "√x"
    assert convert_math(r"$\frac{a}{b}$") == "a/b"
    assert convert_math(r"$a \parallel b$") == "a ∥ b"


def test_delimited_parens_and_brackets():
    assert convert_math(r"\(x+y\)") == "x+y"
    assert convert_math(r"\[x+y\]") == "x+y"
    assert convert_math("$$x+y$$") == "x+y"


def test_display_superscripts():
    assert convert_math("$$x^2 + y^2 = z^2$$") == "x² + y² = z²"


def test_subscript_braced():
    assert convert_math("$x_{n+1}$") == "xₙ₊₁"
    assert convert_math("$a_i$") == "aᵢ"


def test_currency_not_math():
    assert convert_math("It costs $20 today.") == "It costs $20 today."
    assert "20" in normalize_markdown("Price is $20\n", math_mode="unicode")
    assert "$20" in normalize_markdown("Price is $20\n", math_mode="unicode")


def test_strip_spacing_commands():
    out = convert_math(r"$a \quad b \, c \qquad d$")
    assert "\\quad" not in out
    assert "\\," not in out
    assert "a" in out and "b" in out


def test_text_command():
    assert convert_math(r"$\text{where } x > 0$") == "where x > 0"


def test_prose_adjacent():
    src = (
        "Consider quadrilateral $ABCD$ with midpoints $P,Q,R,S$.\n"
    )
    out = normalize_markdown(src, math_mode="unicode")
    assert "quadrilateral ABCD with midpoints P,Q,R,S" in out
    assert "$" not in out


def test_varignon_regression():
    src = (
        "Why it works: Consider quadrilateral $ABCD$ with midpoints "
        "$P, Q, R, S$ of sides $AB$, $BC$, $CD$, and $DA$ respectively.\n"
        "\n"
        r"$PQ \parallel AC$" "\n"
        r"$PQ = \frac{1}{2}AC$" "\n"
        r"$SR = \frac{1}{2}AC$" "\n"
    )
    out = normalize_markdown(src, math_mode="unicode")

    for needle in (
        "ABCD",
        "P, Q, R, S",
        "AB",
        "BC",
        "CD",
        "DA",
        "PQ ∥ AC",
        "PQ = 1/2 × AC",
        "SR = 1/2 × AC",
    ):
        assert needle in out, f"missing {needle!r} in:\n{out}"

    for banned in ("$", r"\frac", r"\parallel", r"\quad", r"\text{"):
        assert banned not in out, f"unexpected {banned!r} in:\n{out}"


def test_inline_code_preserved():
    src = "Use `$\\alpha$` in code and $\\alpha$ outside.\n"
    out = normalize_markdown(src, math_mode="unicode")
    assert "`$\\alpha$`" in out or "`$\\\\alpha$`" in out or r"`$\alpha$`" in out
    # Outside math converted
    assert "outside" in out
    # The prose alpha should be unicode; the code span kept literally
    assert "α outside" in out or out.endswith("α outside.\n") or "α outside." in out
