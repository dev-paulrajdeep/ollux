"""Terminal Markdown rendering via glow (piped) or plain fallback."""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import TextIO
import base64
import re

from ollux.utils import eprint


def glow_available() -> bool:
    return shutil.which("glow") is not None

def chafa_available() -> bool:
    return shutil.which("chafa") is not None

def _render_base64_images(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        alt = m.group(1)
        b64 = m.group(2)
        try:
            image_data = base64.b64decode(b64)
            proc = subprocess.run(
                ["chafa", "-f", "symbols", "-"],
                input=image_data,
                capture_output=True,
                check=False
            )
            if proc.returncode == 0:
                ansi_output = proc.stdout.decode("utf-8").strip()
                if ansi_output:
                    # Place a newline before/after so markdown rendering handles it nicely
                    header = f"{alt}:" if alt else ""
                    return f"\n{header}\n{ansi_output}\n"
        except Exception:
            pass
        return m.group(0)

    # Match ![alt](data:image/xxx;base64,yyy)
    return re.sub(
        r'!\[([^\]]*)\]\(data:image/[^;]+;base64,([^)]+)\)',
        repl,
        text,
    )


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
    if chafa_available():
        text = _render_base64_images(text)
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
