"""Local, deterministic Markdown normalization."""

from __future__ import annotations

import re

from ollux.math import convert_math

# Fenced code blocks (``` or ~~~), keeping exact original text for restore
_FENCE_RE = re.compile(
    r"(^|\n)(```[^\n]*\n.*?^\s*```[ \t]*"
    r"|~~~[^\n]*\n.*?^\s*~~~[ \t]*)",
    re.MULTILINE | re.DOTALL,
)

# Obvious think wrappers (common in some local models)
_THINK_RE = re.compile(
    r"<think>\s*.*?\s*</think\s*>",
    re.IGNORECASE | re.DOTALL,
)
_THINK_ALT_RE = re.compile(
    r"<thinking>\s*.*?\s*</thinking\s*>",
    re.IGNORECASE | re.DOTALL,
)

_PLACEHOLDER = "\x00OLLUX_CODE_{i}\x00"


def normalize_markdown(text: str, *, math_mode: str = "unicode") -> str:
    """
    Deterministic local cleanup. Does not paraphrase, summarize,
    reorder, or alter code fence contents.
    """
    if not text:
        return ""

    protected, fences = _protect_fences(text)
    protected = _strip_think_blocks(protected)
    protected = _normalize_whitespace(protected)
    protected = _unescape_common(protected)
    protected = convert_math(protected, mode=math_mode)
    restored = _restore_fences(protected, fences)
    return restored.strip() + ("\n" if restored.strip() else "")


def _protect_fences(text: str) -> tuple[str, list[str]]:
    fences: list[str] = []

    def repl(m: re.Match[str]) -> str:
        prefix = m.group(1)
        block = m.group(2)
        idx = len(fences)
        fences.append(block)
        return f"{prefix}{_PLACEHOLDER.format(i=idx)}"

    return _FENCE_RE.sub(repl, text), fences


def _restore_fences(text: str, fences: list[str]) -> str:
    for i, block in enumerate(fences):
        text = text.replace(_PLACEHOLDER.format(i=i), block)
    return text


def _strip_think_blocks(text: str) -> str:
    text = _THINK_RE.sub("", text)
    text = _THINK_ALT_RE.sub("", text)
    return text


def _normalize_whitespace(text: str) -> str:
    # Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Strip trailing spaces/tabs per line
    text = re.sub(r"[ \t]+\n", "\n", text)
    # Collapse 3+ blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Trim leading blank lines
    text = text.lstrip("\n")
    return text


def _unescape_common(text: str) -> str:
    """
    Undo a few accidental Markdown escapes outside code.
    Conservative: only clear \ before punctuation that models over-escape.
    """
    return re.sub(r"\\([#*_`\[\]()>+\-.!])", r"\1", text)
