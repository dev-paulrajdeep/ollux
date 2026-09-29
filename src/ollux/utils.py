"""Shared helpers: stdin, safe writes, ANSI stripping, errors."""

from __future__ import annotations

import re
import sys
from pathlib import Path

# CSI / OSC-style ANSI escapes and common control sequences
_ANSI_RE = re.compile(
    r"(?:\x1B[@-Z\\-_]"  # Fe escape
    r"|\x1B\[[0-?]*[ -/]*[@-~]"  # CSI
    r"|\x1B\][^\x07\x1B]*(?:\x07|\x1B\\)"  # OSC
    r"|\x1B[PX^_][^\x1B]*\x1B\\"  # DCS/PM/APC
    r"|\x9B[0-?]*[ -/]*[@-~])"  # 8-bit CSI
)


class OlluxError(Exception):
    """User-facing error with optional exit code."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def eprint(*args: object, **kwargs: object) -> None:
    print(*args, file=sys.stderr, **kwargs)  # type: ignore[call-arg]


def read_stdin_if_piped() -> str | None:
    """Return stdin text when not a TTY; otherwise None."""
    if sys.stdin.isatty():
        return None
    data = sys.stdin.read()
    if not data:
        return None
    return data.rstrip("\n")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences so saved files stay pure Markdown."""
    return _ANSI_RE.sub("", text)


def write_markdown_file(path: Path, content: str, *, force: bool = False) -> Path:
    """Write pure Markdown (no ANSI). Refuse overwrite unless force."""
    path = path.expanduser()
    if path.exists() and not force:
        raise OlluxError(
            f"refusing to overwrite existing file: {path} (use --force)"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = strip_ansi(content)
    if not clean.endswith("\n"):
        clean += "\n"
    path.write_text(clean, encoding="utf-8")
    return path


def looks_like_model_name(token: str) -> bool:
    """
    Heuristic: model tags are typically short, no spaces, often contain ':' or '/'.
    Used to avoid an API round-trip for ordinary prompts.
    """
    if not token or " " in token or "\n" in token:
        return False
    if len(token) > 128:
        return False
    # Prompts often start with capitals and punctuation; model names are
    # lowercase-ish identifiers with optional :tag or /namespace.
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*(:[A-Za-z0-9._-]+)?", token):
        return True
    return False
