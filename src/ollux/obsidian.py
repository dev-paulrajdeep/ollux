"""Obsidian vault helpers: safe filenames and optional frontmatter."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from ollux.utils import OlluxError, write_markdown_file

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_MULTI_DASH = re.compile(r"-{2,}")


def slugify(prompt: str, *, max_len: int = 80) -> str:
    """Generate a safe filename stem from a prompt, e.g. explain-fourier-transforms."""
    text = prompt.strip().lower()
    # Drop surrounding quotes
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        text = text[1:-1]
    text = _NON_ALNUM.sub("-", text)
    text = _MULTI_DASH.sub("-", text).strip("-")
    if not text:
        text = "note"
    if len(text) > max_len:
        text = text[:max_len].rstrip("-")
    return text


def make_filename(prompt: str) -> str:
    return f"{slugify(prompt)}.md"


def build_frontmatter(
    *,
    title: str,
    model: str,
    tags: list[str] | None = None,
) -> str:
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Escape YAML double quotes in title
    safe_title = title.replace('"', '\\"').replace("\n", " ").strip()
    lines = [
        "---",
        f'title: "{safe_title}"',
        f"model: {model}",
        f"created: {created}",
        "tags:",
        "  - ollux",
    ]
    for tag in tags or []:
        lines.append(f"  - {tag}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def compose_note(
    body: str,
    *,
    prompt: str,
    model: str,
    frontmatter: bool = True,
) -> str:
    parts: list[str] = []
    if frontmatter:
        parts.append(build_frontmatter(title=prompt.strip()[:120], model=model))
    parts.append(body if body.endswith("\n") else body + "\n")
    return "".join(parts)


def save_obsidian_note(
    vault: Path | str,
    prompt: str,
    body: str,
    *,
    model: str,
    force: bool = False,
    frontmatter: bool = True,
) -> Path:
    vault_path = Path(vault).expanduser()
    if not str(vault).strip():
        raise OlluxError(
            "obsidian_directory is not set; run `ollux --setup` "
            "or set it in ~/.config/ollux/config.toml"
        )
    if not vault_path.is_dir():
        raise OlluxError(f"obsidian directory does not exist: {vault_path}")

    name = make_filename(prompt)
    path = vault_path / name
    content = compose_note(body, prompt=prompt, model=model, frontmatter=frontmatter)
    return write_markdown_file(path, content, force=force)
