"""CLI parsing, stdin, and error-path tests (no live Ollama)."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest

from ollux.cli import build_parser, main, resolve_model_and_prompt
from ollux.config import Config
from ollux.utils import looks_like_model_name


def test_looks_like_model():
    assert looks_like_model_name("qwen3:8b")
    assert looks_like_model_name("ornith-1.5:9b")
    assert looks_like_model_name("llama3.2")
    assert not looks_like_model_name("Explain Fourier transforms")
    assert not looks_like_model_name("What is π?")


def test_parser_flags():
    p = build_parser()
    args = p.parse_args(
        ["--markdown", "--math", "latex", "--force", "--save", "out.md", "m", "hi"]
    )
    assert args.markdown is True
    assert args.math == "latex"
    assert args.force is True
    assert args.save == "out.md"
    assert args.model_or_prompt == "m"
    assert args.prompt == "hi"


def test_resolve_explicit_model():
    args = build_parser().parse_args(["--model", "ornith-1.5:9b", "hello"])
    cfg = Config(default_model="")
    client = MagicMock()
    model, prompt, interactive = resolve_model_and_prompt(args, cfg, client)
    assert model == "ornith-1.5:9b"
    assert prompt == "hello"
    assert interactive is False
    client.list_models.assert_not_called()


def test_resolve_model_and_prompt_positional():
    args = build_parser().parse_args(["ornith-1.5:9b", "Explain π"])
    cfg = Config()
    client = MagicMock()
    model, prompt, interactive = resolve_model_and_prompt(args, cfg, client)
    assert model == "ornith-1.5:9b"
    assert prompt == "Explain π"
    assert interactive is False
    client.list_models.assert_not_called()


def test_resolve_prompt_only_uses_default():
    args = build_parser().parse_args(["Explain eigenvalues without listing models"])
    cfg = Config(default_model="ornith-1.5:9b")
    client = MagicMock()
    model, prompt, interactive = resolve_model_and_prompt(args, cfg, client)
    assert model == "ornith-1.5:9b"
    assert "eigenvalues" in prompt
    assert interactive is False
    client.list_models.assert_not_called()


def test_resolve_model_only_interactive():
    args = build_parser().parse_args(["ornith-1.5:9b"])
    cfg = Config()
    client = MagicMock()
    model, prompt, interactive = resolve_model_and_prompt(args, cfg, client)
    assert model == "ornith-1.5:9b"
    assert prompt is None
    assert interactive is True


def test_version(capsys):
    assert main(["--version"]) == 0
    assert "ollux 0.1.0" in capsys.readouterr().out


def test_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "civilized" in capsys.readouterr().out.lower()


def test_stdin_prompt(monkeypatch):
    args = build_parser().parse_args(["ornith-1.5:9b"])
    cfg = Config()
    client = MagicMock()
    monkeypatch.setattr(
        "ollux.cli.read_stdin_if_piped", lambda: "Explain Maxwell's equations"
    )
    model, prompt, interactive = resolve_model_and_prompt(args, cfg, client)
    assert model == "ornith-1.5:9b"
    assert prompt == "Explain Maxwell's equations"
    assert interactive is False


def test_ollama_connection_error(capsys):
    from ollux.ollama import OllamaClient
    from ollux.utils import OlluxError

    client = OllamaClient(host="http://127.0.0.1:1")
    with pytest.raises(OlluxError, match="cannot reach Ollama"):
        client.list_models(refresh=True)


def test_oneshot_markdown_no_glow(tmp_path, monkeypatch, capsys):
    chunks = ["# Title\n\n", r"Value \alpha", "\n"]

    def fake_chat(model, messages, stream=True):
        yield from chunks

    monkeypatch.setattr(
        "ollux.cli.OllamaClient.chat", lambda self, *a, **k: fake_chat(*a, **k)
    )
    monkeypatch.setattr("ollux.cli.OllamaClient.__init__", lambda self, host="": None)

    code = main(
        [
            "--markdown",
            "--model",
            "fake:1b",
            "Say hello",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "# Title" in out
    assert "α" in out
    assert "\x1b[" not in out


def test_save_no_ansi(tmp_path, monkeypatch, capsys):
    def fake_chat(model, messages, stream=True):
        yield "Hello \\beta\n"

    monkeypatch.setattr(
        "ollux.cli.OllamaClient.chat", lambda self, *a, **k: fake_chat(*a, **k)
    )
    monkeypatch.setattr("ollux.cli.OllamaClient.__init__", lambda self, host="": None)

    out_file = tmp_path / "out.md"
    code = main(
        ["--save", str(out_file), "--model", "fake:1b", "prompt"]
    )
    assert code == 0
    text = out_file.read_text(encoding="utf-8")
    assert "β" in text
    assert "\x1b" not in text
