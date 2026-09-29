"""Config load/save and CLI precedence."""

from pathlib import Path

from ollux.config import Config, load_config, merge_cli, save_config


def test_defaults(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OLLUX_HOST", raising=False)
    monkeypatch.delenv("OLLUX_MODEL", raising=False)
    monkeypatch.setattr("ollux.config.DEFAULT_CONFIG_PATH", tmp_path / "missing.toml")
    cfg = load_config(tmp_path / "missing.toml")
    assert cfg.host == "http://127.0.0.1:11434"
    assert cfg.math_mode == "unicode"
    assert cfg.obsidian_math_mode == "latex"


def test_load_and_save_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OLLUX_HOST", raising=False)
    path = tmp_path / "config.toml"
    cfg = Config(
        default_model="ornith-1.5:9b",
        host="http://127.0.0.1:11434",
        math_mode="unicode",
        obsidian_directory="/vault",
        obsidian_math_mode="latex",
    )
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.default_model == "ornith-1.5:9b"
    assert loaded.obsidian_directory == "/vault"
    assert loaded.math_mode == "unicode"


def test_env_host_override(tmp_path: Path, monkeypatch):
    path = tmp_path / "config.toml"
    save_config(Config(host="http://127.0.0.1:11434"), path)
    monkeypatch.setenv("OLLUX_HOST", "http://127.0.0.1:9999")
    loaded = load_config(path)
    assert loaded.host == "http://127.0.0.1:9999"


def test_cli_precedence():
    cfg = Config(math_mode="unicode", host="http://a")
    merged = merge_cli(cfg, math_mode="latex", host=None)
    assert merged.math_mode == "latex"
    assert merged.host == "http://a"  # None does not override
