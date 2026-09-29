"""Local LaTeX → Unicode math normalization for terminal readability."""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Symbol tables
# ---------------------------------------------------------------------------

_SIMPLE_CMDS: dict[str, str] = {
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\delta": "δ",
    r"\epsilon": "ε",
    r"\varepsilon": "ε",
    r"\zeta": "ζ",
    r"\eta": "η",
    r"\theta": "θ",
    r"\iota": "ι",
    r"\kappa": "κ",
    r"\lambda": "λ",
    r"\mu": "μ",
    r"\nu": "ν",
    r"\xi": "ξ",
    r"\pi": "π",
    r"\rho": "ρ",
    r"\sigma": "σ",
    r"\tau": "τ",
    r"\phi": "φ",
    r"\varphi": "φ",
    r"\chi": "χ",
    r"\psi": "ψ",
    r"\omega": "ω",
    r"\Gamma": "Γ",
    r"\Delta": "Δ",
    r"\Theta": "Θ",
    r"\Lambda": "Λ",
    r"\Xi": "Ξ",
    r"\Pi": "Π",
    r"\Sigma": "Σ",
    r"\Phi": "Φ",
    r"\Psi": "Ψ",
    r"\Omega": "Ω",
    r"\infty": "∞",
    r"\partial": "∂",
    r"\nabla": "∇",
    r"\cdot": "×",
    r"\times": "×",
    r"\parallel": "∥",
    r"\perp": "⟂",
    r"\rightarrow": "→",
    r"\to": "→",
    r"\leftarrow": "←",
    r"\Rightarrow": "⇒",
    r"\Leftarrow": "⇐",
    r"\leftrightarrow": "↔",
    r"\leq": "≤",
    r"\geq": "≥",
    r"\neq": "≠",
    r"\ne": "≠",
    r"\approx": "≈",
    r"\equiv": "≡",
    r"\pm": "±",
    r"\mp": "∓",
    r"\sum": "Σ",
    r"\prod": "Π",
    r"\int": "∫",
    r"\cdotp": "·",
    r"\ldots": "…",
    r"\cdots": "⋯",
    r"\dots": "…",
    r"\imath": "ı",
    r"\jmath": "ȷ",
    r"\checkmark": "✓",
    r"\blacksquare": "■",
}

_SORTED_CMDS = sorted(_SIMPLE_CMDS.keys(), key=len, reverse=True)
_CMD_RE = re.compile("|".join(re.escape(k) for k in _SORTED_CMDS))

_SUP: dict[str, str] = {
    "0": "⁰",
    "1": "¹",
    "2": "²",
    "3": "³",
    "4": "⁴",
    "5": "⁵",
    "6": "⁶",
    "7": "⁷",
    "8": "⁸",
    "9": "⁹",
    "+": "⁺",
    "-": "⁻",
    "=": "⁼",
    "(": "⁽",
    ")": "⁾",
    "n": "ⁿ",
    "i": "ⁱ",
    "a": "ᵃ",
    "b": "ᵇ",
    "c": "ᶜ",
    "d": "ᵈ",
    "e": "ᵉ",
    "f": "ᶠ",
    "g": "ᵍ",
    "h": "ʰ",
    "k": "ᵏ",
    "l": "ˡ",
    "m": "ᵐ",
    "o": "ᵒ",
    "p": "ᵖ",
    "r": "ʳ",
    "s": "ˢ",
    "t": "ᵗ",
    "u": "ᵘ",
    "v": "ᵛ",
    "w": "ʷ",
    "x": "ˣ",
    "y": "ʸ",
    "z": "ᶻ",
}

_SUB: dict[str, str] = {
    "0": "₀",
    "1": "₁",
    "2": "₂",
    "3": "₃",
    "4": "₄",
    "5": "₅",
    "6": "₆",
    "7": "₇",
    "8": "₈",
    "9": "₉",
    "+": "₊",
    "-": "₋",
    "=": "₌",
    "(": "₍",
    ")": "₎",
    "a": "ₐ",
    "e": "ₑ",
    "h": "ₕ",
    "i": "ᵢ",
    "j": "ⱼ",
    "k": "ₖ",
    "l": "ₗ",
    "m": "ₘ",
    "n": "ₙ",
    "o": "ₒ",
    "p": "ₚ",
    "r": "ᵣ",
    "s": "ₛ",
    "t": "ₜ",
    "u": "ᵤ",
    "v": "ᵥ",
    "x": "ₓ",
}

# Harmless spacing / sizing commands to drop (leave a space to avoid word-join)
_STRIP_CMDS_RE = re.compile(
    r"\\(?:left|right|big|Big|bigg|Bigg|quad|qquad)\b|\\[,\!;:]|\\[ ]"
)

_TEXT_RE = re.compile(r"\\text\{([^{}]*)\}")
_MATHRM_RE = re.compile(r"\\(?:mathrm|mathbf|mathit|mathsf|textbf|textit)\{([^{}]*)\}")
_VEC_RE = re.compile(r"\\(?:vec|overrightarrow|overleftarrow)\{([^{}]+)\}")
_HAT_RE = re.compile(r"\\hat\{([^{}]+)\}")
# \vec F / \hat i without braces (single token)
_VEC_BARE_RE = re.compile(r"\\vec\s*([A-Za-z])")
_HAT_BARE_RE = re.compile(r"\\hat\s*([A-Za-z])")
_BOXED_RE = re.compile(r"\\boxed\{([^{}]+)\}")  # simple; nested handled below

_FUNC_RE = re.compile(
    r"\\(sin|cos|tan|cot|sec|csc|log|ln|exp|det|max|min|lim|inf|sup|arg|"
    r"deg|dim|ker|hom|gcd|arcsin|arccos|arctan)\b"
)

_SQRT_RE = re.compile(r"\\sqrt\{([^{}]+)\}")
# Capture optional juxtaposed identifier after \frac{a}{b}
_FRAC_RE = re.compile(
    r"\\(?:frac|tfrac|dfrac|cfrac)\{([^{}]+)\}\{([^{}]+)\}(\s*)([A-Za-z][A-Za-z0-9]*)?"
)

# Single-token or braced super/subscripts
_SUP_RE = re.compile(r"\^(\{([^{}]*)\}|([A-Za-z0-9+\-]))")
_SUB_RE = re.compile(r"_(\{([^{}]*)\}|([A-Za-z0-9+\-]))")

_OPS_IN_SQRT = re.compile(r"[+\-*/=]")


def convert_math(text: str, mode: str = "unicode") -> str:
    """
    Convert common LaTeX (delimited and bare) to terminal-readable Unicode.
    `--math latex` bypasses entirely. Caller must protect code first.
    """
    if mode != "unicode" or not text:
        return text
    text = _replace_delimited_math(text)
    # Convert any remaining bare LaTeX outside former delimiters
    text = _convert_expression(text)
    return text


def _replace_delimited_math(text: str) -> str:
    """Find $$ $$ / \\[ \\] / \\( \\) / $ $ and replace with converted bodies."""
    out: list[str] = []
    i = 0
    n = len(text)

    while i < n:
        # Display $$...$$
        if text.startswith("$$", i):
            end = text.find("$$", i + 2)
            if end != -1:
                body = text[i + 2 : end]
                out.append(_convert_expression(body))
                i = end + 2
                continue
            out.append(text[i])
            i += 1
            continue

        # \[...\]
        if text.startswith("\\[", i):
            end = text.find("\\]", i + 2)
            if end != -1:
                out.append(_convert_expression(text[i + 2 : end]))
                i = end + 2
                continue

        # \(...\)
        if text.startswith("\\(", i):
            end = text.find("\\)", i + 2)
            if end != -1:
                out.append(_convert_expression(text[i + 2 : end]))
                i = end + 2
                continue

        # Inline $...$ (not currency, not $$)
        if text[i] == "$" and not text.startswith("$$", i):
            # Escaped \$?
            if i > 0 and text[i - 1] == "\\":
                out.append("$")
                i += 1
                continue
            close = _find_closing_dollar(text, i + 1)
            if close is not None:
                body = text[i + 1 : close]
                out.append(_convert_expression(body))
                i = close + 1
                continue
            # No valid closer — leave the dollar (e.g. $20)
            out.append("$")
            i += 1
            continue

        out.append(text[i])
        i += 1

    return "".join(out)


def _find_closing_dollar(text: str, start: int) -> int | None:
    """
    Find closing $ for inline math. Reject empty bodies and bare currency
    patterns that never close. Requires a later unescaped $.
    """
    i = start
    n = len(text)
    while i < n:
        if text[i] == "$":
            if i > 0 and text[i - 1] == "\\":
                i += 1
                continue
            # Disallow empty $$
            if i == start:
                return None
            return i
        # Stop at newline for inline $ — display uses $$
        if text[i] == "\n":
            return None
        i += 1
    return None


def _convert_expression(expr: str) -> str:
    """Convert LaTeX inside one math expression (no outer delimiters)."""
    if not expr:
        return expr

    text = expr
    # \text{...} / \mathrm{...} / \boxed{...} (brace-aware for nesting)
    text = _replace_brace_cmd(text, ("text",), lambda inner: inner)
    text = _replace_brace_cmd(
        text,
        ("mathrm", "mathbf", "mathit", "mathsf", "textbf", "textit"),
        lambda inner: inner,
    )
    text = _replace_brace_cmd(text, ("boxed",), lambda inner: inner)
    # \vec{x} / \overrightarrow{x} → x⃗ , \hat{i} → î / î
    text = _replace_brace_cmd(
        text,
        ("vec", "overrightarrow", "overleftarrow"),
        lambda inner: inner + "\u20d7",
    )
    text = _replace_brace_cmd(text, ("hat",), _hat_inner)
    text = _VEC_BARE_RE.sub(lambda m: m.group(1) + "\u20d7", text)
    text = _HAT_BARE_RE.sub(lambda m: _hat_inner(m.group(1)), text)
    # \sin → sin (pad with spaces so ab\sinθ → ab sin θ)
    text = _FUNC_RE.sub(r" \1 ", text)
    # Drop spacing / \left \right etc. (replace with space)
    text = _STRIP_CMDS_RE.sub(" ", text)

    # Named commands before frac/sqrt so \frac{\alpha}{2} works
    text = _CMD_RE.sub(lambda m: _SIMPLE_CMDS[m.group(0)], text)

    text = _SQRT_RE.sub(_sqrt_repl, text)
    # Frac may nest; apply repeatedly for simple non-nested residues
    for _ in range(4):
        nxt = _FRAC_RE.sub(_frac_repl, text)
        if nxt == text:
            break
        text = nxt

    # Super/sub after symbols exist
    text = _SUP_RE.sub(_sup_repl, text)
    text = _SUB_RE.sub(_sub_repl, text)

    # Collapse leftover multi-spaces introduced by stripping
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip() if expr.strip() != expr else text


def _replace_brace_cmd(
    text: str, names: tuple[str, ...], repl
) -> str:
    """Replace \\name{...} with brace matching (allows nested braces)."""
    changed = True
    while changed:
        changed = False
        for name in names:
            needle = "\\" + name + "{"
            idx = text.find(needle)
            if idx < 0:
                continue
            start = idx + len(needle)
            depth = 1
            j = start
            while j < len(text) and depth:
                ch = text[j]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                j += 1
            if depth != 0:
                continue
            inner = text[start : j - 1]
            text = text[:idx] + repl(inner) + text[j:]
            changed = True
            break
    return text


def _hat_inner(inner: str) -> str:
    special = {"i": "î", "j": "ĵ", "a": "â", "e": "ê", "o": "ô", "u": "û"}
    if inner in special:
        return special[inner]
    if len(inner) == 1:
        return inner + "\u0302"  # combining circumflex
    return inner


def _hat_repl(m: re.Match[str]) -> str:
    return _hat_inner(m.group(1))


def _sqrt_repl(m: re.Match[str]) -> str:
    inner = m.group(1).strip()
    if _OPS_IN_SQRT.search(inner) or " " in inner:
        return f"√({inner})"
    return f"√{inner}"


def _frac_repl(m: re.Match[str]) -> str:
    a = m.group(1).strip()
    b = m.group(2).strip()
    # Uncertain nested / cascading TeX left alone
    if "\\" in a or "\\" in b or "/" in a or "/" in b:
        return m.group(0)
    if len(a) > 32 or len(b) > 32:
        return m.group(0)

    juxta = m.group(4) or ""
    digits = a.isdigit() and b.isdigit()
    ratio = f"{a}/{b}"

    if juxta:
        if digits:
            return f"{ratio} × {juxta}"
        return f"({ratio}) × {juxta}"
    return ratio


def _map_script(body: str, table: dict[str, str]) -> str | None:
    mapped: list[str] = []
    for ch in body:
        if ch == " ":
            continue
        if ch not in table:
            return None
        mapped.append(table[ch])
    return "".join(mapped) if mapped else None


def _sup_repl(m: re.Match[str]) -> str:
    body = m.group(2) if m.group(2) is not None else m.group(3)
    body = body or ""
    converted = _map_script(body, _SUP)
    if converted is not None:
        return converted
    return f"^({body})" if len(body) > 1 or m.group(2) is not None else f"^{body}"


def _sub_repl(m: re.Match[str]) -> str:
    body = m.group(2) if m.group(2) is not None else m.group(3)
    body = body or ""
    converted = _map_script(body, _SUB)
    if converted is not None:
        return converted
    return f"_({body})" if len(body) > 1 or m.group(2) is not None else f"_{body}"
