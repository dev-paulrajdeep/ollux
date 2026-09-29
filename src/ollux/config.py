"""Configuration loading, validation, and atomic saving for ollux."""

from __future__ import annotations

import os
import tempfile
import tomllib
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "ollux"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"

ALLOWED_RENDERERS = frozenset({"glow", "plain"})
ALLOWED_MATH_MODES = frozenset({"unicode", "latex"})


@dataclass
class Config:
    default_model: str = ""
    host: str = DEFAULT_HOST
    renderer: str = "glow"
    math_mode: str = "unicode"
    stream: bool = True
    obsidian_directory: str = ""
    obsidian_math_mode: str = "latex"

    @classmethod
    def defaults(cls) -> Config:
        return cls()


class ConfigError(Exception):
    """Invalid or unreadable configuration."""


def config_path() -> Path:
    override = os.environ.get("OLLUX_CONFIG")
    if override:
        return Path(override)
    return DEFAULT_CONFIG_PATH


def load_config(path: Path | None = None) -> Config:
    """Load config from TOML. Missing file yields defaults."""
    cfg = Config.defaults()
    p = path or config_path()
    if not p.is_file():
        return _apply_env(cfg)

    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"failed to read config {p}: {exc}") from exc

    known = {f.name for f in fields(Config)}
    for key, value in data.items():
        if key in known:
            setattr(cfg, key, value)
    return _apply_env(cfg)


def _apply_env(cfg: Config) -> Config:
    host = os.environ.get("OLLUX_HOST")
    if host:
        cfg.host = host.rstrip("/")
    model = os.environ.get("OLLUX_MODEL")
    if model:
        cfg.default_model = model
    return cfg


def validate_host(value: str) -> str:
    """Require http(s) URL with a hostname. Returns normalized host (no trailing slash)."""
    raw = (value or "").strip()
    if not raw:
        raise ConfigError("host must be a non-empty HTTP/HTTPS URL")
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise ConfigError("host must use http:// or https://")
    if not parsed.hostname:
        raise ConfigError("host must include a hostname (e.g. 127.0.0.1)")
    if parsed.params or parsed.query or parsed.fragment:
        raise ConfigError("host must not include query, params, or fragment")
    # Rebuild without trailing path slash noise, keep explicit port
    netloc = parsed.netloc
    path = (parsed.path or "").rstrip("/")
    if path and path != "":
        # Allow path prefix (unusual but valid reverse-proxy); reject spaces etc.
        if " " in path:
            raise ConfigError("host path is invalid")
        normalized = f"{parsed.scheme}://{netloc}{path}"
    else:
        normalized = f"{parsed.scheme}://{netloc}"
    return normalized


def validate_renderer(value: str) -> str:
    v = (value or "").strip().lower()
    if v not in ALLOWED_RENDERERS:
        raise ConfigError(f"renderer must be one of: {', '.join(sorted(ALLOWED_RENDERERS))}")
    return v


def validate_math_mode(value: str) -> str:
    v = (value or "").strip().lower()
    if v not in ALLOWED_MATH_MODES:
        raise ConfigError(f"math_mode must be one of: {', '.join(sorted(ALLOWED_MATH_MODES))}")
    return v


def validate_obsidian_math_mode(value: str) -> str:
    v = (value or "").strip().lower()
    if v not in ALLOWED_MATH_MODES:
        raise ConfigError(
            f"obsidian_math_mode must be one of: {', '.join(sorted(ALLOWED_MATH_MODES))}"
        )
    return v


def validate_obsidian_directory(value: str) -> tuple[str, list[str]]:
    """
    Accept empty. Otherwise expand ~ and validate usability.
    Returns (normalized_path, warnings).
    """
    raw = (value or "").strip()
    if not raw:
        return "", []
    if "\x00" in raw or "\n" in raw or "\r" in raw:
        raise ConfigError("obsidian_directory contains invalid characters")
    path = Path(raw).expanduser()
    # Relative paths are OK but normalize to absolute for stability
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        path = path.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ConfigError(f"obsidian_directory is not a usable path: {exc}") from exc

    warnings: list[str] = []
    if path.exists() and not path.is_dir():
        raise ConfigError(f"obsidian_directory exists but is not a directory: {path}")
    if not path.exists():
        warnings.append(f"directory does not exist yet: {path}")
    return str(path), warnings


def model_in_list(name: str, models: list[str]) -> bool:
    if name in models:
        return True
    for n in models:
        if n == name or n.startswith(name + ":"):
            return True
    return False


def validate_default_model(
    value: str,
    *,
    models: list[str] | None = None,
    ollama_available: bool | None = None,
) -> tuple[str, list[str]]:
    """
    Empty is allowed. If non-empty and Ollama listing is available, model must exist.
    If Ollama is unavailable, accept with a warning.
    Returns (model, warnings).
    """
    raw = (value or "").strip()
    warnings: list[str] = []
    if not raw:
        return "", warnings
    if "\n" in raw or "\x00" in raw or " " in raw:
        raise ConfigError("default_model must be a single model name (no spaces)")

    if ollama_available is False or models is None:
        warnings.append(
            f"could not verify model against Ollama; saving {raw!r} unchecked"
        )
        return raw, warnings

    if not model_in_list(raw, models):
        raise ConfigError(
            f"model not found in Ollama: {raw} "
            f"(installed: {', '.join(models) if models else 'none'})"
        )
    return raw, warnings


def validate_config(
    cfg: Config,
    *,
    models: list[str] | None = None,
    ollama_available: bool | None = None,
) -> tuple[Config, list[str]]:
    """
    Validate entire config. Returns (normalized_config, warnings).
    Raises ConfigError on hard failures — caller must not write.
    """
    warnings: list[str] = []
    host = validate_host(cfg.host)
    renderer = validate_renderer(cfg.renderer)
    math_mode = validate_math_mode(cfg.math_mode)
    obsidian_math_mode = validate_obsidian_math_mode(cfg.obsidian_math_mode)
    obsidian_directory, w1 = validate_obsidian_directory(cfg.obsidian_directory)
    warnings.extend(w1)
    default_model, w2 = validate_default_model(
        cfg.default_model,
        models=models,
        ollama_available=ollama_available,
    )
    warnings.extend(w2)

    if not isinstance(cfg.stream, bool):
        raise ConfigError("stream must be a boolean")

    normalized = Config(
        default_model=default_model,
        host=host,
        renderer=renderer,
        math_mode=math_mode,
        stream=bool(cfg.stream),
        obsidian_directory=obsidian_directory,
        obsidian_math_mode=obsidian_math_mode,
    )
    return normalized, warnings


def save_config(cfg: Config, path: Path | None = None) -> Path:
    """
    Validate structural fields then write config as TOML atomically.
    A failed write never corrupts an existing config.toml.
    Model existence is not checked here (use save_config_validated in setup).
    """
    normalized, _warnings = validate_config(
        cfg, models=None, ollama_available=None
    )
    return _atomic_write_config(normalized, path or config_path())


def save_config_validated(
    cfg: Config,
    path: Path | None = None,
    *,
    models: list[str] | None = None,
    ollama_available: bool | None = None,
) -> tuple[Path, list[str]]:
    """Validate with optional model list, then atomic write. Returns (path, warnings)."""
    normalized, warnings = validate_config(
        cfg, models=models, ollama_available=ollama_available
    )
    path_out = _atomic_write_config(normalized, path or config_path())
    return path_out, warnings


def _atomic_write_config(cfg: Config, p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# ollux configuration", ""]
    for key, value in asdict(cfg).items():
        lines.append(f"{key} = {_toml_value(value)}")
    lines.append("")
    payload = "\n".join(lines).encode("utf-8")

    fd, tmp_name = tempfile.mkstemp(
        prefix=".ollux-config-",
        suffix=".tmp",
        dir=str(p.parent),
    )
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, p)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return p


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def merge_cli(cfg: Config, **overrides: Any) -> Config:
    """Apply non-None CLI overrides. Precedence: CLI > config > defaults."""
    merged = Config(**asdict(cfg))
    for key, value in overrides.items():
        if value is None:
            continue
        if hasattr(merged, key):
            setattr(merged, key, value)
    return merged
