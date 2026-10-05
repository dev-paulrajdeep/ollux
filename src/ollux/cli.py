"""Ollux command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ollux import __version__
from ollux.config import Config, ConfigError, load_config, merge_cli
from ollux.bench import DEFAULT_PROMPT, benchmark, print_human, print_json
from ollux.markdown import normalize_markdown
from ollux.obsidian import save_obsidian_note
from ollux.ollama import SYSTEM_PROMPT, OllamaClient
from ollux.renderer import render_markdown
from ollux.setup import run_setup
from ollux.utils import (
    OlluxError,
    eprint,
    looks_like_model_name,
    read_stdin_if_piped,
    write_markdown_file,
)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return parsed


def _nonnegative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ollux",
        description="Ollama, but civilized. Local Markdown presentation layer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  ollux
  ollux qwen3:8b
  ollux qwen3:8b "Explain Fourier transforms"
  ollux --model ornith-1.5:9b "Explain eigenvalues"
  echo "Explain Maxwell" | ollux ornith-1.5:9b
  ollux --save out.md ornith-1.5:9b "Explain π"
  ollux --obsidian ornith-1.5:9b "Explain Fourier transforms"
""",
    )
    p.add_argument("model_or_prompt", nargs="?", help="model name or prompt")
    p.add_argument("prompt", nargs="?", help="prompt (when model is first)")
    p.add_argument("--model", "-m", dest="model_flag", help="explicit model name")
    p.add_argument("--list", "-l", action="store_true", help="list installed models")
    p.add_argument("--bench", action="store_true", help="benchmark local model inference")
    p.add_argument("--runs", type=_positive_int, default=5, help="measured benchmark runs (default: 5)")
    p.add_argument("--warmup", type=_nonnegative_int, default=1, help="discarded warmup runs (default: 1)")
    p.add_argument("--num-predict", type=_positive_int, default=256, help="tokens to generate per run (default: 256)")
    p.add_argument("--seed", type=_nonnegative_int, default=0, help="generation seed (default: 0)")
    p.add_argument("--temperature", type=_nonnegative_float, default=0.0, help="generation temperature (default: 0)")
    p.add_argument("--json", action="store_true", help="emit benchmark results as JSON")
    p.add_argument(
        "--raw", action="store_true", help="print raw model output (no normalization)"
    )
    p.add_argument(
        "--markdown",
        action="store_true",
        help="output normalized Markdown only (no terminal renderer)",
    )
    p.add_argument(
        "--no-render",
        action="store_true",
        help="skip glow; print Markdown",
    )
    p.add_argument(
        "--live",
        action="store_true",
        help="stream tokens directly with minimal/no normalization",
    )
    p.add_argument("--save", metavar="FILE", help="write pure Markdown to FILE")
    p.add_argument(
        "--obsidian",
        action="store_true",
        help="save note into configured Obsidian vault",
    )
    p.add_argument(
        "--math",
        choices=("unicode", "latex"),
        default=None,
        help="math mode (default: unicode; obsidian default: latex)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing files for --save / --obsidian",
    )
    p.add_argument("--setup", action="store_true", help="interactive config setup")
    p.add_argument("--debug", action="store_true", help="print debug details on errors")
    p.add_argument("--version", "-V", action="store_true", help="print version")
    p.add_argument(
        "--host",
        default=None,
        help="Ollama host (default: http://127.0.0.1:11434)",
    )
    p.add_argument(
        "--no-frontmatter",
        action="store_true",
        help="omit YAML frontmatter for --obsidian",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"ollux {__version__}")
        return 0

    try:
        cfg = load_config()
    except ConfigError as exc:
        eprint(f"error: {exc}")
        return 1

    cfg = merge_cli(cfg, host=args.host, math_mode=args.math)

    if args.setup:
        return run_setup(cfg)

    client = OllamaClient(host=cfg.host)

    if args.list:
        return cmd_list(client)

    if args.bench:
        model = args.model_flag or cfg.default_model
        prompt = args.prompt or args.model_or_prompt or DEFAULT_PROMPT
        piped = read_stdin_if_piped()
        if piped:
            prompt = f"{prompt}\n{piped}" if prompt != DEFAULT_PROMPT else piped
        if not model:
            return _fail(OlluxError("no model specified; pass --model or set default_model in config"))
        try:
            result = benchmark(
                client, model, prompt, runs=args.runs, warmup=args.warmup,
                num_predict=args.num_predict, seed=args.seed, temperature=args.temperature,
            )
        except OlluxError as exc:
            return _fail(exc)
        (print_json if args.json else print_human)(result)
        return 130 if result["interrupted"] else 0

    try:
        model, prompt, interactive = resolve_model_and_prompt(args, cfg, client)
    except OlluxError as exc:
        return _fail(exc, debug=args.debug)

    if interactive:
        try:
            return run_interactive(client, cfg, model, args)
        except OlluxError as exc:
            return _fail(exc, debug=args.debug)
        except KeyboardInterrupt:
            eprint("\nInterrupted.")
            return 130

    if not prompt:
        eprint("error: empty prompt")
        return 1

    try:
        return run_oneshot(client, cfg, model, prompt, args)
    except OlluxError as exc:
        return _fail(exc, debug=args.debug)
    except KeyboardInterrupt:
        eprint("\nInterrupted.")
        return 130


def _fail(exc: BaseException, *, debug: bool = False) -> int:
    eprint(f"error: {exc}")
    if debug:
        import traceback

        traceback.print_exc()
    code = getattr(exc, "exit_code", 1)
    return int(code) if isinstance(code, int) else 1


def resolve_model_and_prompt(
    args: argparse.Namespace,
    cfg: Config,
    client: OllamaClient,
) -> tuple[str, str | None, bool]:
    """
    Resolve (model, prompt, interactive).

    Avoids /api/tags for ordinary prompts. Uses a local heuristic; only
    queries Ollama when the first token looks like a model name and was
    not given via --model. --model always wins.
    """
    stdin_prompt = read_stdin_if_piped()
    first = args.model_or_prompt
    second = args.prompt

    model: str | None = args.model_flag
    prompt: str | None = None

    if model:
        # Explicit --model: remaining positionals are prompt pieces
        parts = [p for p in (first, second) if p]
        prompt = " ".join(parts) if parts else None
    elif first and second:
        model = first
        prompt = second
    elif first:
        if looks_like_model_name(first):
            # Likely a model → interactive or stdin prompt
            model = first
            prompt = None
        else:
            # Treat as prompt; need default_model
            prompt = first
            model = cfg.default_model or None
    else:
        model = cfg.default_model or None
        prompt = None

    if stdin_prompt:
        if prompt:
            prompt = f"{prompt}\n{stdin_prompt}"
        else:
            prompt = stdin_prompt

    if not model:
        raise OlluxError(
            "no model specified; pass a model, use --model, "
            "set default_model in config, or run `ollux --setup`"
        )

    interactive = prompt is None
    return model, prompt, interactive


def cmd_list(client: OllamaClient) -> int:
    try:
        models = client.list_models(refresh=True)
    except OlluxError as exc:
        eprint(f"error: {exc}")
        return 1
    if not models:
        print("No models installed. Use `ollama pull <model>`.")
        return 0
    for name in models:
        print(name)
    return 0


def _system_message(math_mode: str) -> dict[str, str]:
    extra = ""
    if math_mode == "latex":
        extra = " Prefer LaTeX/MathJax notation for mathematics."
    return {"role": "system", "content": SYSTEM_PROMPT + extra}


def run_oneshot(
    client: OllamaClient,
    cfg: Config,
    model: str,
    prompt: str,
    args: argparse.Namespace,
) -> int:
    math_mode = _effective_math(cfg, args)
    messages = [_system_message(math_mode), {"role": "user", "content": prompt}]

    # Fail fast on destination collisions before spending a generation.
    if args.save:
        dest = Path(args.save).expanduser()
        if dest.exists() and not args.force:
            raise OlluxError(
                f"refusing to overwrite existing file: {dest} (use --force)"
            )
    if args.obsidian:
        vault = Path(cfg.obsidian_directory).expanduser() if cfg.obsidian_directory else None
        if not cfg.obsidian_directory:
            raise OlluxError(
                "obsidian_directory is not set; run `ollux --setup` "
                "or set it in ~/.config/ollux/config.toml"
            )
        from ollux.obsidian import make_filename

        dest = vault / make_filename(prompt)  # type: ignore[operator]
        if dest.exists() and not args.force:
            raise OlluxError(
                f"refusing to overwrite existing file: {dest} (use --force)"
            )

    print(f"Ollux · {model}", file=sys.stderr)

    if args.live and not args.save and not args.obsidian and not args.markdown:
        # Stream directly; minimal/no normalization
        for chunk in client.chat(model, messages, stream=True):
            sys.stdout.write(chunk)
            sys.stdout.flush()
        sys.stdout.write("\n")
        return 0

    # Default: collect → normalize → render/save once
    parts: list[str] = []
    for chunk in client.chat(model, messages, stream=True):
        parts.append(chunk)
    raw = "".join(parts)

    if args.raw:
        text = raw if raw.endswith("\n") else raw + "\n"
    else:
        text = normalize_markdown(raw, math_mode=math_mode)

    return _emit(text, model=model, prompt=prompt, cfg=cfg, args=args)


def _effective_math(cfg: Config, args: argparse.Namespace) -> str:
    if args.math:
        return args.math
    if args.obsidian:
        return cfg.obsidian_math_mode or "latex"
    return cfg.math_mode or "unicode"


def _emit(
    text: str,
    *,
    model: str,
    prompt: str,
    cfg: Config,
    args: argparse.Namespace,
) -> int:
    if args.save:
        path = write_markdown_file(Path(args.save), text, force=args.force)
        eprint(f"saved {path}")
        # Still allow simultaneous stdout only if not --markdown forced quiet?
        # Spec: --save writes file; we don't also render unless useful.
        # Keep quiet on stdout for save-only.
        if not args.obsidian and not args.markdown and not args.no_render:
            return 0

    if args.obsidian:
        path = save_obsidian_note(
            cfg.obsidian_directory,
            prompt,
            text,
            model=model,
            force=args.force,
            frontmatter=not args.no_frontmatter,
        )
        eprint(f"obsidian {path}")
        return 0

    # --markdown implies no terminal renderer
    if args.markdown or args.no_render or args.raw:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
        return 0

    use_glow = (cfg.renderer or "glow") == "glow"
    render_markdown(text, use_glow=use_glow)
    return 0


def run_interactive(
    client: OllamaClient,
    cfg: Config,
    model: str,
    args: argparse.Namespace,
) -> int:
    math_mode = args.math or cfg.math_mode or "unicode"
    raw_mode = bool(args.raw)
    render_on = not (args.markdown or args.no_render)
    messages: list[dict[str, str]] = [_system_message(math_mode)]

    print(f"Ollux · {model}")
    print("Type /help for commands, /quit to exit.\n")

    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            print()
            break

        if not line:
            continue

        if line.startswith("/"):
            cont, model, math_mode, raw_mode, render_on, messages = _handle_slash(
                line,
                client=client,
                cfg=cfg,
                model=model,
                math_mode=math_mode,
                raw_mode=raw_mode,
                render_on=render_on,
                messages=messages,
                args=args,
            )
            if not cont:
                break
            continue

        messages.append({"role": "user", "content": line})
        try:
            if args.live and not raw_mode:
                parts: list[str] = []
                for chunk in client.chat(model, messages, stream=True):
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                    parts.append(chunk)
                sys.stdout.write("\n")
                assistant = "".join(parts)
            else:
                parts = list(client.chat(model, messages, stream=True))
                assistant = "".join(parts)
                if raw_mode:
                    out = assistant if assistant.endswith("\n") else assistant + "\n"
                    sys.stdout.write(out)
                else:
                    text = normalize_markdown(assistant, math_mode=math_mode)
                    if render_on:
                        use_glow = (cfg.renderer or "glow") == "glow"
                        render_markdown(text, use_glow=use_glow)
                    else:
                        sys.stdout.write(text if text.endswith("\n") else text + "\n")
        except OlluxError as exc:
            eprint(f"error: {exc}")
            messages.pop()  # remove failed user turn
            continue

        messages.append({"role": "assistant", "content": assistant})

    return 0


def _handle_slash(
    line: str,
    *,
    client: OllamaClient,
    cfg: Config,
    model: str,
    math_mode: str,
    raw_mode: bool,
    render_on: bool,
    messages: list[dict[str, str]],
    args: argparse.Namespace,
) -> tuple[bool, str, str, bool, bool, list[dict[str, str]]]:
    parts = line.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd in ("/quit", "/exit", "/q"):
        return False, model, math_mode, raw_mode, render_on, messages

    if cmd == "/help":
        print(
            """\
/help              show this help
/model [name]      show or switch model
/models            list installed models
/raw               toggle raw output
/render            toggle terminal rendering
/save <file>       save last assistant reply as Markdown
/clear             clear conversation (keep system prompt)
/system            show system prompt
/quit              exit"""
        )
        return True, model, math_mode, raw_mode, render_on, messages

    if cmd == "/model":
        if arg:
            model = arg.strip()
            print(f"model → {model}")
        else:
            print(model)
        return True, model, math_mode, raw_mode, render_on, messages

    if cmd == "/models":
        for name in client.list_models(refresh=True):
            print(name)
        return True, model, math_mode, raw_mode, render_on, messages

    if cmd == "/raw":
        raw_mode = not raw_mode
        print(f"raw → {'on' if raw_mode else 'off'}")
        return True, model, math_mode, raw_mode, render_on, messages

    if cmd == "/render":
        render_on = not render_on
        print(f"render → {'on' if render_on else 'off'}")
        return True, model, math_mode, raw_mode, render_on, messages

    if cmd == "/save":
        if not arg:
            eprint("usage: /save <file.md>")
            return True, model, math_mode, raw_mode, render_on, messages
        last = _last_assistant(messages)
        if last is None:
            eprint("error: no assistant reply to save yet")
            return True, model, math_mode, raw_mode, render_on, messages
        body = last if raw_mode else normalize_markdown(last, math_mode=math_mode)
        try:
            path = write_markdown_file(Path(arg), body, force=args.force)
        except OlluxError as exc:
            eprint(f"error: {exc}")
            return True, model, math_mode, raw_mode, render_on, messages
        print(f"saved {path}")
        return True, model, math_mode, raw_mode, render_on, messages

    if cmd == "/clear":
        messages = [_system_message(math_mode)]
        print("conversation cleared")
        return True, model, math_mode, raw_mode, render_on, messages

    if cmd == "/system":
        print(messages[0]["content"] if messages else SYSTEM_PROMPT)
        return True, model, math_mode, raw_mode, render_on, messages

    eprint(f"unknown command: {cmd} (try /help)")
    return True, model, math_mode, raw_mode, render_on, messages


def _last_assistant(messages: list[dict[str, str]]) -> str | None:
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            return msg.get("content")
    return None


if __name__ == "__main__":
    raise SystemExit(main())
