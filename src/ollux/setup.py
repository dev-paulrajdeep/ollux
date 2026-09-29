"""Interactive setup wizard with validated, selection-friendly prompts."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from ollux.config import (
    ALLOWED_MATH_MODES,
    ALLOWED_RENDERERS,
    Config,
    ConfigError,
    save_config_validated,
    validate_default_model,
    validate_host,
    validate_math_mode,
    validate_obsidian_directory,
    validate_obsidian_math_mode,
    validate_renderer,
)
from ollux.ollama import OllamaClient
from ollux.utils import OlluxError, eprint


def run_setup(
    cfg: Config,
    *,
    path: Path | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    client: OllamaClient | None = None,
) -> int:
    """
    Interactive setup. Never writes until the full config validates.
    Returns 0 on success, 1 on abort/failure.
    """
    inp = stdin or sys.stdin
    out = stdout or sys.stdout

    def write(msg: str = "") -> None:
        print(msg, file=out)

    write("Ollux setup")
    write("(press Enter to keep the current value)\n")

    models, ollama_ok = _fetch_models(cfg.host, client=client)

    try:
        default_model = _ask_model(
            cfg.default_model,
            models=models,
            ollama_available=ollama_ok,
            inp=inp,
            out=out,
        )
        host = _ask_until(
            "host",
            cfg.host or "http://127.0.0.1:11434",
            choices=None,
            parse=validate_host,
            inp=inp,
            out=out,
        )
        renderer = _ask_choice(
            "renderer",
            cfg.renderer or "glow",
            sorted(ALLOWED_RENDERERS),
            parse=validate_renderer,
            inp=inp,
            out=out,
        )
        math_mode = _ask_choice(
            "math_mode",
            cfg.math_mode or "unicode",
            sorted(ALLOWED_MATH_MODES),
            parse=validate_math_mode,
            inp=inp,
            out=out,
        )
        obsidian_directory = _ask_obsidian_directory(
            cfg.obsidian_directory, inp=inp, out=out
        )
        obsidian_math_mode = _ask_choice(
            "obsidian_math_mode",
            cfg.obsidian_math_mode or "latex",
            sorted(ALLOWED_MATH_MODES),
            parse=validate_obsidian_math_mode,
            inp=inp,
            out=out,
        )
    except (EOFError, KeyboardInterrupt):
        write("\nSetup cancelled; config not written.")
        return 1

    draft = Config(
        default_model=default_model,
        host=host,
        renderer=renderer,
        math_mode=math_mode,
        stream=cfg.stream,
        obsidian_directory=obsidian_directory,
        obsidian_math_mode=obsidian_math_mode,
    )

    try:
        dest, warnings = save_config_validated(
            draft,
            path,
            models=models if ollama_ok else None,
            ollama_available=ollama_ok if ollama_ok else False,
        )
    except ConfigError as exc:
        eprint(f"error: {exc}")
        eprint("Setup aborted; existing config left unchanged.")
        return 1

    for w in warnings:
        write(f"warning: {w}")
    write(f"\nWrote {dest}")
    return 0


def _fetch_models(
    host: str, *, client: OllamaClient | None = None
) -> tuple[list[str] | None, bool]:
    try:
        c = client or OllamaClient(host=host)
        return c.list_models(refresh=True), True
    except (OlluxError, OSError) as exc:
        eprint(f"warning: Ollama unavailable ({exc}); model will not be verified")
        return None, False


def _prompt_line(
    label: str,
    current: str,
    *,
    choices: Sequence[str] | None,
    inp: TextIO,
    out: TextIO,
) -> str:
    shown = current if current else "(none)"
    if choices:
        choice_hint = "/".join(choices)
        print(f"{label} [{shown}] ({choice_hint}): ", end="", file=out, flush=True)
    else:
        print(f"{label} [{shown}]: ", end="", file=out, flush=True)
    return inp.readline()


def _ask_until(
    label: str,
    current: str,
    *,
    choices: Sequence[str] | None,
    parse: Callable[[str], str],
    inp: TextIO,
    out: TextIO,
) -> str:
    while True:
        line = _prompt_line(label, current, choices=choices, inp=inp, out=out)
        if line == "":
            raise EOFError
        raw = line.rstrip("\n\r").strip()
        if not raw:
            # Keep current — still validate it
            candidate = current
        else:
            candidate = raw
        try:
            return parse(candidate)
        except ConfigError as exc:
            print(f"error: {exc}", file=out)
            # do not accept; ask again


def _ask_choice(
    label: str,
    current: str,
    choices: Sequence[str],
    *,
    parse: Callable[[str], str],
    inp: TextIO,
    out: TextIO,
) -> str:
    """Enum field: accept name, or 1-based index when choices are shown."""
    choice_list = list(choices)
    print(f"  options: {', '.join(f'{i+1}={c}' for i, c in enumerate(choice_list))}", file=out)

    def parse_choice(raw: str) -> str:
        text = raw.strip().lower()
        if text.isdigit():
            idx = int(text)
            if 1 <= idx <= len(choice_list):
                return parse(choice_list[idx - 1])
            raise ConfigError(f"choose a number 1–{len(choice_list)} or a name")
        return parse(text)

    return _ask_until(
        label,
        current,
        choices=choice_list,
        parse=parse_choice,
        inp=inp,
        out=out,
    )


def _ask_model(
    current: str,
    *,
    models: list[str] | None,
    ollama_available: bool,
    inp: TextIO,
    out: TextIO,
) -> str:
    if models:
        print("Installed models:", file=out)
        for i, name in enumerate(models, start=1):
            print(f"  {i}) {name}", file=out)
        print("Enter number, model name, or leave empty for none.", file=out)
    elif not ollama_available:
        print(
            "Ollama unreachable — enter a model name unchecked, or leave empty.",
            file=out,
        )

    while True:
        line = _prompt_line(
            "default_model", current, choices=None, inp=inp, out=out
        )
        if line == "":
            raise EOFError
        raw = line.rstrip("\n\r").strip()
        if not raw:
            candidate = current
        elif models and raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(models):
                candidate = models[idx - 1]
            else:
                print(
                    f"error: choose a number 1–{len(models)}, a model name, or empty",
                    file=out,
                )
                continue
        else:
            candidate = raw

        try:
            value, warnings = validate_default_model(
                candidate,
                models=models,
                ollama_available=ollama_available if ollama_available else False,
            )
        except ConfigError as exc:
            print(f"error: {exc}", file=out)
            continue
        for w in warnings:
            print(f"warning: {w}", file=out)
        return value


def _ask_obsidian_directory(current: str, *, inp: TextIO, out: TextIO) -> str:
    print("Leave empty to disable Obsidian export.", file=out)

    def parse(raw: str) -> str:
        path, warnings = validate_obsidian_directory(raw)
        for w in warnings:
            print(f"warning: {w}", file=out)
        return path

    return _ask_until(
        "obsidian_directory",
        current,
        choices=None,
        parse=parse,
        inp=inp,
        out=out,
    )
