"""Obsidian filename, frontmatter, and save behavior."""

from pathlib import Path

import pytest

from ollux.obsidian import compose_note, make_filename, save_obsidian_note, slugify
from ollux.utils import OlluxError, strip_ansi, write_markdown_file


def test_slugify_basic():
    assert slugify("Explain Fourier transforms") == "explain-fourier-transforms"


def test_slugify_punctuation():
    assert make_filename("What's an eigenvalue?") == "what-s-an-eigenvalue.md"


def test_compose_frontmatter():
    note = compose_note(
        "# Body\n",
        prompt="Explain Fourier transforms",
        model="ornith-1.5:9b",
        frontmatter=True,
    )
    assert note.startswith("---\n")
    assert 'title: "Explain Fourier transforms"' in note
    assert "model: ornith-1.5:9b" in note
    assert "# Body" in note


def test_save_obsidian(tmp_path: Path):
    path = save_obsidian_note(
        tmp_path,
        "Explain Fourier transforms",
        "# Hello\n",
        model="ornith-1.5:9b",
    )
    assert path.name == "explain-fourier-transforms.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "# Hello" in text


def test_refuse_overwrite(tmp_path: Path):
    path = tmp_path / "note.md"
    write_markdown_file(path, "one\n")
    with pytest.raises(OlluxError, match="refusing to overwrite"):
        write_markdown_file(path, "two\n", force=False)


def test_force_overwrite(tmp_path: Path):
    path = tmp_path / "note.md"
    write_markdown_file(path, "one\n")
    write_markdown_file(path, "two\n", force=True)
    assert path.read_text(encoding="utf-8") == "two\n"


def test_obsidian_force(tmp_path: Path):
    save_obsidian_note(tmp_path, "Same", "a\n", model="m")
    with pytest.raises(OlluxError):
        save_obsidian_note(tmp_path, "Same", "b\n", model="m", force=False)
    save_obsidian_note(tmp_path, "Same", "b\n", model="m", force=True)


def test_strip_ansi_from_saved():
    dirty = "Hello \x1b[31mRed\x1b[0m\n"
    assert "\x1b" not in strip_ansi(dirty)
    assert "Red" in strip_ansi(dirty)


def test_write_strips_ansi(tmp_path: Path):
    path = write_markdown_file(tmp_path / "x.md", "A\x1b[1mB\x1b[0mC\n")
    assert path.read_text(encoding="utf-8") == "ABC\n"


def test_missing_vault():
    with pytest.raises(OlluxError, match="not set"):
        save_obsidian_note("", "p", "b\n", model="m")
