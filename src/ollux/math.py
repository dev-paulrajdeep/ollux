"""Conservative LaTeX → Unicode math conversions."""

from __future__ import annotations

import re

# Safe, common command → Unicode mappings (no ambiguous multi-arg forms).
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
    r"\rightarrow": "→",
    r"\to": "→",
    r"\leftarrow": "←",
    r"\Rightarrow": "⇒",
    r"\Leftarrow": "⇐",
    r"\leftrightarrow": "↔",
    r"\leq": "≤",
    r"\geq": "≥",
    r"\neq": "≠",
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
}

# Longest keys first so \varepsilon beats \epsilon, etc.
_SORTED_CMDS = sorted(_SIMPLE_CMDS.keys(), key=len, reverse=True)
_CMD_RE = re.compile(
    "|".join(re.escape(k) for k in _SORTED_CMDS)
)

# Simple \sqrt{x} where x has no nested braces
_SQRT_RE = re.compile(r"\\sqrt\{([^{}]+)\}")

# Simple \frac{a}{b} where a,b have no nested braces — conservative a/b
_FRAC_RE = re.compile(r"\\frac\{([^{}]+)\}\{([^{}]+)\}")

# Strip outer \( \) \[ \] $ $ when they wrap already-converted short math
_INLINE_WRAP_RE = re.compile(r"\\\((.+?)\\\)")
_DISPLAY_WRAP_RE = re.compile(r"\\\[(.+?)\\\]")


def convert_math(text: str, mode: str = "unicode") -> str:
    """
    Convert safe common LaTeX to Unicode when mode is 'unicode'.
    Leaves text unchanged for 'latex'. Never touches fenced code
    (caller must protect fences before calling).
    """
    if mode != "unicode" or not text:
        return text
    return _convert_unicode(text)


def _convert_unicode(text: str) -> str:
    # Simple sqrt before frac / commands so nested forms stay conservative
    text = _SQRT_RE.sub(lambda m: "√" + m.group(1), text)

    def frac_sub(m: re.Match[str]) -> str:
        a, b = m.group(1).strip(), m.group(2).strip()
        # Skip if either side still looks like complex TeX
        if "\\" in a or "\\" in b or " " in a or " " in b:
            if "\\" in a or "\\" in b:
                return m.group(0)  # uncertain — leave alone
        return f"{a}/{b}"

    text = _FRAC_RE.sub(frac_sub, text)
    text = _CMD_RE.sub(lambda m: _SIMPLE_CMDS[m.group(0)], text)

    # Unwrap simple \(...\) / \[...\] after conversion (content already unicode)
    text = _INLINE_WRAP_RE.sub(r"\1", text)
    text = _DISPLAY_WRAP_RE.sub(r"\1", text)
    return text
