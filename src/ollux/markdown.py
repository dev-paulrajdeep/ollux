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

# Inline code: one or more backticks, matching closer
_INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)((?:(?!\1).)+)\1(?!`)")

# Obvious think wrappers (common in some local models)
_THINK_RE = re.compile(
    r"<think>\s*.*?\s*</think\s*>",
    re.IGNORECASE | re.DOTALL,
)
_THINK_ALT_RE = re.compile(
    r"<thinking>\s*.*?\s*</thinking\s*>",
    re.IGNORECASE | re.DOTALL,
)

_CODE_PLACEHOLDER = "\x00OLLUXCODE«{i}»\x00"


def normalize_markdown(text: str, *, math_mode: str = "unicode") -> str:
    """
    Deterministic local cleanup. Does not paraphrase, summarize,
    reorder, or alter code fence / inline-code contents.

    Pipeline:
      protect code → strip think → math (unicode) → whitespace → unescape → restore
    """
    if not text:
        return ""

    protected, chunks = _protect_code(text)
    protected = _strip_think_blocks(protected)
    # Math before general whitespace so delimiter scanning sees original lines
    protected = convert_math(protected, mode=math_mode)
    protected = _normalize_whitespace(protected)
    protected = _unescape_common(protected)
    restored = _restore_code(protected, chunks)
    return restored.strip() + ("\n" if restored.strip() else "")


def _protect_code(text: str) -> tuple[str, list[str]]:
    """Protect fenced blocks first, then inline code. Restore exactly later."""
    chunks: list[str] = []

    def keep(block: str) -> str:
        idx = len(chunks)
        chunks.append(block)
        return _CODE_PLACEHOLDER.format(i=idx)

    def fence_repl(m: re.Match[str]) -> str:
        return f"{m.group(1)}{keep(m.group(2))}"

    text = _FENCE_RE.sub(fence_repl, text)

    def inline_repl(m: re.Match[str]) -> str:
        return keep(m.group(0))

    text = _INLINE_CODE_RE.sub(inline_repl, text)
    return text, chunks


def _restore_code(text: str, chunks: list[str]) -> str:
    for i, block in enumerate(chunks):
        text = text.replace(_CODE_PLACEHOLDER.format(i=i), block)
    return text


def _strip_think_blocks(text: str) -> str:
    text = _THINK_RE.sub("", text)
    text = _THINK_ALT_RE.sub("", text)
    return text


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.lstrip("\n")
    return text


def _unescape_common(text: str) -> str:
    r"""
    Undo a few accidental Markdown escapes outside code.
    Conservative: only clear \ before punctuation that models over-escape.
    """
    return re.sub(r"\\([#*_`\[\]()>+\-.!])", r"\1", text)
