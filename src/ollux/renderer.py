"""Terminal Markdown rendering via glow (piped) or plain fallback."""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import TextIO

from ollux.utils import eprint


def glow_available() -> bool:
    return shutil.which("glow") is not None


def render_markdown(
    text: str,
    *,
    use_glow: bool = True,
    file: TextIO | None = None,
) -> None:
    """
    Render Markdown once to the terminal.
    Prefer `glow -` (stdin pipe); never create temp files.
    Falls back to plain Markdown if glow is missing or fails.
    """
    out = file if file is not None else sys.stdout
    if use_glow and glow_available() and file is None:
        try:
            proc = subprocess.run(
                ["glow", "-"],
                input=text.encode("utf-8"),
                stdout=None,  # inherit terminal
                stderr=subprocess.PIPE,
                check=False,
            )
            if proc.returncode == 0:
                return
            err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
            if err:
                eprint(f"warning: glow failed ({err}); showing plain Markdown")
        except OSError as exc:
            eprint(f"warning: could not run glow ({exc}); showing plain Markdown")

    if not text.endswith("\n"):
        text = text + "\n"
    out.write(text)
    out.flush()
