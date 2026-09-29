"""Setup wizard validation and interactive rejection tests."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ollux.config import (
    Config,
    ConfigError,
    load_config,
    save_config,
    save_config_validated,
    validate_config,
    validate_default_model,
    validate_host,
    validate_math_mode,
    validate_obsidian_directory,
    validate_obsidian_math_mode,
    validate_renderer,
)
from ollux.setup import run_setup


def test_invalid_host_rejected():
    with pytest.raises(ConfigError):
        validate_host("wassup man")
    with pytest.raises(ConfigError):
        validate_host("ftp://127.0.0.1")
    with pytest.raises(ConfigError):
        validate_host("http://")
    with pytest.raises(ConfigError):
        validate_host("")


def test_valid_host_normalized():
    assert validate_host("http://127.0.0.1:11434/") == "http://127.0.0.1:11434"
    assert validate_host("https://example.com") == "https://example.com"


def test_invalid_renderer():
    with pytest.raises(ConfigError, match="renderer"):
        validate_renderer("fancy")
    with pytest.raises(ConfigError):
        validate_renderer("wassup")
    assert validate_renderer("Glow") == "glow"
    assert validate_renderer("plain") == "plain"


def test_invalid_math_mode():
    with pytest.raises(ConfigError, match="math_mode"):
        validate_math_mode("ascii")
    assert validate_math_mode("LaTeX") == "latex"


def test_invalid_obsidian_math_mode():
    with pytest.raises(ConfigError, match="obsidian_math_mode"):
        validate_obsidian_math_mode("mathml")
    assert validate_obsidian_math_mode("unicode") == "unicode"


def test_invalid_model_when_ollama_lists():
    with pytest.raises(ConfigError, match="not found"):
        validate_default_model(
            "nosuch-model:99b",
            models=["ornith-1.5:9b"],
            ollama_available=True,
        )


def test_model_allowed_when_ollama_down():
    value, warnings = validate_default_model(
        "future-model:7b",
        models=None,
        ollama_available=False,
    )
    assert value == "future-model:7b"
    assert warnings


def test_empty_model_ok():
    value, warnings = validate_default_model(
        "", models=["ornith-1.5:9b"], ollama_available=True
    )
    assert value == ""
    assert warnings == []


def test_invalid_obsidian_path_null():
    with pytest.raises(ConfigError):
        validate_obsidian_directory("foo\x00bar")


def test_obsidian_path_warns_if_missing(tmp_path: Path):
    missing = tmp_path / "vault-not-yet"
    path, warnings = validate_obsidian_directory(str(missing))
    assert path == str(missing.resolve())
    assert warnings


def test_obsidian_path_rejects_file(tmp_path: Path):
    f = tmp_path / "notadir"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(ConfigError, match="not a directory"):
        validate_obsidian_directory(str(f))


def test_obsidian_empty_ok():
    path, warnings = validate_obsidian_directory("")
    assert path == ""
    assert warnings == []


def test_validate_config_rejects_bad_renderer():
    cfg = Config(renderer="nope")
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_save_config_rejects_invalid_without_writing(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('default_model = "keep-me"\nhost = "http://127.0.0.1:11434"\n', encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    with pytest.raises(ConfigError):
        save_config(Config(host="wassup man", renderer="glow"), path)
    assert path.read_text(encoding="utf-8") == before


def test_atomic_save_success(tmp_path: Path):
    path = tmp_path / "config.toml"
    save_config(
        Config(
            default_model="",
            host="http://127.0.0.1:11434",
            renderer="plain",
            math_mode="latex",
            obsidian_math_mode="unicode",
        ),
        path,
    )
    loaded = load_config(path)
    assert loaded.renderer == "plain"
    assert loaded.math_mode == "latex"


def test_setup_retries_invalid_host_then_succeeds(tmp_path: Path):
    cfg = Config()
    # Sequence: model empty, bad host, good host, renderer, math, obsidian empty, obsidian math
    user = io.StringIO(
        "\n"  # default_model keep empty
        "wassup man\n"
        "http://127.0.0.1:11434\n"
        "glow\n"
        "unicode\n"
        "\n"  # obsidian empty
        "latex\n"
    )
    out = io.StringIO()
    client = MagicMock()
    client.list_models.return_value = ["ornith-1.5:9b"]

    code = run_setup(
        cfg,
        path=tmp_path / "config.toml",
        stdin=user,
        stdout=out,
        client=client,
    )
    assert code == 0
    text = out.getvalue()
    assert "error:" in text
    loaded = load_config(tmp_path / "config.toml")
    assert loaded.host == "http://127.0.0.1:11434"
    assert loaded.renderer == "glow"


def test_setup_rejects_invalid_renderer_until_valid(tmp_path: Path):
    user = io.StringIO(
        "\n"
        "http://127.0.0.1:11434\n"
        "neon\n"
        "plain\n"
        "unicode\n"
        "\n"
        "latex\n"
    )
    out = io.StringIO()
    client = MagicMock()
    client.list_models.return_value = ["ornith-1.5:9b"]
    code = run_setup(
        Config(),
        path=tmp_path / "c.toml",
        stdin=user,
        stdout=out,
        client=client,
    )
    assert code == 0
    assert "error:" in out.getvalue()
    assert load_config(tmp_path / "c.toml").renderer == "plain"


def test_setup_rejects_unknown_model(tmp_path: Path):
    user = io.StringIO(
        "nosuch:1b\n"
        "1\n"  # select first installed
        "http://127.0.0.1:11434\n"
        "glow\n"
        "unicode\n"
        "\n"
        "latex\n"
    )
    out = io.StringIO()
    client = MagicMock()
    client.list_models.return_value = ["ornith-1.5:9b"]
    code = run_setup(
        Config(),
        path=tmp_path / "c.toml",
        stdin=user,
        stdout=out,
        client=client,
    )
    assert code == 0
    assert "not found" in out.getvalue()
    assert load_config(tmp_path / "c.toml").default_model == "ornith-1.5:9b"


def test_setup_choice_by_number(tmp_path: Path):
    user = io.StringIO(
        "\n"
        "http://127.0.0.1:11434\n"
        "2\n"  # plain (sorted: glow, plain → 1=glow 2=plain)
        "2\n"  # latex (sorted: latex, unicode → 1=latex 2=unicode) wait sorted is latex, unicode
        "\n"
        "1\n"  # obsidian math: latex=1 unicode=2 when sorted
    )
    # sorted(ALLOWED_MATH_MODES) = ["latex", "unicode"]
    # sorted(ALLOWED_RENDERERS) = ["glow", "plain"]
    out = io.StringIO()
    client = MagicMock()
    client.list_models.return_value = []
    code = run_setup(
        Config(),
        path=tmp_path / "c.toml",
        stdin=user,
        stdout=out,
        client=client,
    )
    assert code == 0
    loaded = load_config(tmp_path / "c.toml")
    assert loaded.renderer == "plain"
    assert loaded.math_mode == "unicode"
    assert loaded.obsidian_math_mode == "latex"


def test_setup_does_not_write_on_eof(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('host = "http://127.0.0.1:11434"\n', encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    user = io.StringIO("")  # immediate EOF
    out = io.StringIO()
    client = MagicMock()
    client.list_models.return_value = ["ornith-1.5:9b"]
    code = run_setup(Config(), path=path, stdin=user, stdout=out, client=client)
    assert code == 1
    assert path.read_text(encoding="utf-8") == before
    assert "not written" in out.getvalue()


def test_save_config_validated_aborts_bad_math(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("# old\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        save_config_validated(
            Config(math_mode="nope"),
            path,
            models=[],
            ollama_available=True,
        )
    assert path.read_text(encoding="utf-8") == "# old\n"
