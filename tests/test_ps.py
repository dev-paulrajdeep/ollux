from __future__ import annotations

import json
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from ollux.cli import _handle_slash, build_parser, main
from ollux.config import Config
from ollux.ollama import OllamaClient
from ollux.ps import _clean_models, _display, _size, offload, show_status
from ollux.utils import OlluxError


class MockPS(ThreadingHTTPServer):
    def __init__(self, handler):
        super().__init__(("127.0.0.1", 0), handler)
        self.payload = {"models": []}
        self.body_override = None
        self.status = 200
        self.delay = 0.0


@pytest.fixture
def ps_server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if server.delay:
                time.sleep(server.delay)
            if server.status != 200:
                body = json.dumps({"error": "Ollama unavailable"}).encode()
                self.send_response(server.status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = server.body_override
            if body is None:
                body = json.dumps(server.payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = MockPS(Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def client_for(server):
    return OllamaClient(f"http://127.0.0.1:{server.server_port}")


def test_offload_known_answer():
    assert offload(6_000_000_000, 4_500_000_000) == {
        "gpu_pct": 75.0, "cpu_pct": 25.0, "state": "partial",
    }


def test_offload_full_gpu():
    assert offload(10, 10) == {"gpu_pct": 100.0, "cpu_pct": 0.0, "state": "gpu"}


def test_offload_full_cpu():
    assert offload(10, 0) == {"gpu_pct": 0.0, "cpu_pct": 100.0, "state": "cpu"}


def test_offload_missing_vram_is_unknown():
    assert offload(10, None) == {"gpu_pct": None, "cpu_pct": None, "state": "unknown"}


def test_offload_zero_size_is_unknown():
    assert offload(0, 0)["state"] == "unknown"


def test_offload_negative_size_is_unknown():
    assert offload(-1, 0)["state"] == "unknown"


def test_offload_vram_larger_than_size_clamps():
    assert offload(10, 12) == {"gpu_pct": 100.0, "cpu_pct": 0.0, "state": "gpu"}


def test_gpu_model_rendering_exact(ps_server, monkeypatch, capsys):
    ps_server.payload = {"models": [{"name": "gpu-model", "size": 6_000_000_000, "size_vram": 6_000_000_000}]}
    monkeypatch.setattr("ollux.ps.gpu_info", lambda: [])
    show_status(client_for(ps_server))
    captured = capsys.readouterr()
    assert captured.out == (
        "gpu-model\n"
        "  Total: 5.59 GiB\n"
        "  VRAM: 5.59 GiB\n"
        "  CPU: 0.00 GiB\n"
        "  Split: 100% GPU / 0% CPU\n"
        "  Fully on GPU.\n"
    )
    assert captured.err == ""


def test_partial_model_rendering_and_warning_exact(ps_server, monkeypatch, capsys):
    ps_server.payload = {"models": [{"name": "partial", "size": 6_000_000_000, "size_vram": 4_500_000_000}]}
    monkeypatch.setattr("ollux.ps.gpu_info", lambda: [])
    show_status(client_for(ps_server))
    captured = capsys.readouterr()
    assert captured.out == (
        "partial\n"
        "  Total: 5.59 GiB\n"
        "  VRAM: 4.19 GiB\n"
        "  CPU: 1.40 GiB\n"
        "  Split: 75% GPU / 25% CPU\n"
    )
    assert captured.err == (
        "Warning: partial is partly on CPU; generation will be slower than fully offloaded.\n"
        "Reducing context length or using a smaller or more heavily quantized model can help.\n"
    )


def test_cpu_model_rendering_warning_exact(ps_server, monkeypatch, capsys):
    ps_server.payload = {"models": [{"name": "cpu-model", "size": 100, "size_vram": 0}]}
    monkeypatch.setattr("ollux.ps.gpu_info", lambda: [])
    show_status(client_for(ps_server))
    captured = capsys.readouterr()
    assert captured.out == (
        "cpu-model\n"
        "  Total: 9.31e-08 GiB\n"
        "  VRAM: 0.00 GiB\n"
        "  CPU: 9.31e-08 GiB\n"
        "  Split: 0% GPU / 100% CPU\n"
    )
    assert captured.err == "Warning: cpu-model is running entirely on CPU.\n"


def test_empty_output_and_keep_alive_hint(ps_server, monkeypatch, capsys):
    ps_server.payload = {"models": []}
    monkeypatch.setattr("ollux.ps.gpu_info", lambda: [])
    show_status(client_for(ps_server))
    captured = capsys.readouterr()
    assert captured.out == "no models loaded\n"
    assert captured.err == "Hint: Ollama unloads models after their keep-alive period; the next prompt loads one again.\n"


def test_multiple_models_sorted_with_combined_vram(ps_server, monkeypatch, capsys):
    ps_server.payload = {"models": [
        {"name": "zeta", "size": 2 * 1024**3, "size_vram": 1024**3},
        {"name": "alpha", "size": 1024**3, "size_vram": 1024**3},
    ]}
    monkeypatch.setattr("ollux.ps.gpu_info", lambda: [])
    show_status(client_for(ps_server))
    output = capsys.readouterr().out
    assert output.startswith("alpha\n")
    assert "\nzeta\n" in output
    assert output.endswith("Combined VRAM: 2.00 GiB\n")


def test_context_and_expiry_rendering():
    models = _clean_models({"models": [{
        "name": "timed", "size": 1024**3, "size_vram": None,
        "context_length": 8192, "expires_at": "2030-01-01T00:04:12Z",
    }]}, warn=False)
    fixed_now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    output, _ = _display(models, None, fixed_now)
    assert output == (
        "timed\n"
        "  Total: 1.00 GiB\n"
        "  VRAM: unknown\n"
        "  CPU: unknown\n"
        "  Split: unknown\n"
        "  Memory split could not be determined.\n"
        "  Context: 8192 tokens\n"
        "  Unloads in: 4m 12s\n"
    )


def test_missing_expiry_omits_timer():
    models = _clean_models({"models": [{"name": "m", "size": 2, "size_vram": 2}]}, warn=False)
    output, _ = _display(models, None, datetime.now(timezone.utc))
    assert "Unloads in" not in output


def test_unparseable_expiry_omits_timer():
    models = _clean_models({"models": [{"name": "m", "size": 2, "size_vram": 2, "expires_at": "tomorrow"}]}, warn=False)
    output, _ = _display(models, None, datetime.now(timezone.utc))
    assert "Unloads in" not in output


def test_past_expiry_omits_timer():
    models = _clean_models({"models": [{"name": "m", "size": 2, "size_vram": 2, "expires_at": "2000-01-01T00:00:00Z"}]}, warn=False)
    output, _ = _display(models, None, datetime.now(timezone.utc))
    assert "Unloads in" not in output


def test_tiny_size_does_not_round_to_zero():
    assert _size(1) == "9.31e-10 GiB"


def test_missing_models_field_degrades_to_empty(ps_server, monkeypatch, capsys):
    ps_server.payload = {}
    monkeypatch.setattr("ollux.ps.gpu_info", lambda: [])
    show_status(client_for(ps_server))
    captured = capsys.readouterr()
    assert captured.out == "no models loaded\n"
    assert "no models list" in captured.err


def test_null_models_field_degrades_to_empty(ps_server, monkeypatch, capsys):
    ps_server.payload = {"models": None}
    monkeypatch.setattr("ollux.ps.gpu_info", lambda: [])
    show_status(client_for(ps_server))
    assert capsys.readouterr().out == "no models loaded\n"


def test_malformed_entry_is_skipped_without_hiding_valid(ps_server, monkeypatch, capsys):
    ps_server.payload = {"models": [
        {"name": "bad"},
        {"name": "valid", "size": 1024**3, "size_vram": 1024**3},
    ]}
    monkeypatch.setattr("ollux.ps.gpu_info", lambda: [])
    show_status(client_for(ps_server))
    captured = capsys.readouterr()
    assert captured.out.startswith("valid\n")
    assert "without a valid name and size" in captured.err


def test_malformed_json_is_clear_error(ps_server, monkeypatch):
    ps_server.body_override = b"{broken\n"
    monkeypatch.setattr("ollux.ps.gpu_info", lambda: [])
    with pytest.raises(OlluxError, match="malformed JSON"):
        show_status(client_for(ps_server))


def test_connection_refused_is_clear_error():
    with pytest.raises(OlluxError, match="cannot reach Ollama"):
        show_status(OllamaClient("http://127.0.0.1:1", timeout=0.1))


def test_request_timeout_is_clear_error(ps_server):
    ps_server.delay = 0.1
    client = OllamaClient(f"http://127.0.0.1:{ps_server.server_port}", timeout=0.01)
    with pytest.raises(OlluxError, match="timed out"):
        show_status(client)


def test_gpu_missing_is_nonfatal_and_model_remains(ps_server, monkeypatch, capsys):
    ps_server.payload = {"models": [{"name": "m", "size": 1000, "size_vram": 500}]}
    monkeypatch.setattr("ollux.ps.shutil.which", lambda _: None)
    show_status(client_for(ps_server))
    captured = capsys.readouterr()
    assert "m\n" in captured.out
    assert captured.err.count("gpu stats unavailable") == 1


@pytest.mark.parametrize("failure", [
    subprocess.CalledProcessError(1, "nvidia-smi"),
    subprocess.TimeoutExpired("nvidia-smi", 3),
])
def test_gpu_failure_and_timeout_are_nonfatal(ps_server, monkeypatch, capsys, failure):
    ps_server.payload = {"models": [{"name": "m", "size": 1000, "size_vram": 500}]}
    monkeypatch.setattr("ollux.ps.shutil.which", lambda _: "/usr/bin/nvidia-smi")
    def fail(*_args, **_kwargs):
        raise failure
    monkeypatch.setattr("ollux.ps.subprocess.run", fail)
    show_status(client_for(ps_server))
    captured = capsys.readouterr()
    assert "m\n" in captured.out
    assert captured.err.count("gpu stats unavailable") == 1


def test_gpu_na_fields_parse_defensively(ps_server, monkeypatch, capsys):
    ps_server.payload = {"models": [{"name": "m", "size": 1000, "size_vram": 500}]}
    monkeypatch.setattr("ollux.ps.shutil.which", lambda _: "/usr/bin/nvidia-smi")
    monkeypatch.setattr("ollux.ps.subprocess.run", lambda *a, **k: SimpleNamespace(stdout="RTX, [N/A], 8000, , [N/A], 45\n", returncode=0))
    show_status(client_for(ps_server))
    captured = capsys.readouterr()
    assert "GPU: RTX; memory unknown; temperature 45.0 °C" in captured.out
    assert "gpu stats unavailable" not in captured.err


def test_multiple_gpu_devices_each_rendered(ps_server, monkeypatch, capsys):
    ps_server.payload = {"models": []}
    monkeypatch.setattr("ollux.ps.shutil.which", lambda _: "/usr/bin/nvidia-smi")
    monkeypatch.setattr("ollux.ps.subprocess.run", lambda *a, **k: SimpleNamespace(stdout="GPU A, 1, 8, 10, 20, 30\nGPU B, 2, 8, 20, 30, 40\n", returncode=0))
    show_status(client_for(ps_server))
    output = capsys.readouterr().out
    assert "GPU: GPU A" in output
    assert "GPU: GPU B" in output


def test_gpu_memory_converted_to_gib(ps_server, monkeypatch, capsys):
    ps_server.payload = {"models": []}
    monkeypatch.setattr("ollux.ps.shutil.which", lambda _: "/usr/bin/nvidia-smi")
    monkeypatch.setattr("ollux.ps.subprocess.run", lambda *a, **k: SimpleNamespace(stdout="GPU, 4096, 8192, 25, 50, 60\n", returncode=0))
    show_status(client_for(ps_server))
    assert "GPU: GPU; memory 4.00/8.00 GiB" in capsys.readouterr().out


def test_garbage_gpu_output_is_unavailable(ps_server, monkeypatch, capsys):
    ps_server.payload = {"models": []}
    monkeypatch.setattr("ollux.ps.shutil.which", lambda _: "/usr/bin/nvidia-smi")
    monkeypatch.setattr("ollux.ps.subprocess.run", lambda *a, **k: SimpleNamespace(stdout="garbage", returncode=0))
    show_status(client_for(ps_server))
    assert "gpu stats unavailable" in capsys.readouterr().err


def test_ps_json_is_clean_stdout(ps_server, monkeypatch, capsys):
    ps_server.payload = {"models": [{"name": "m", "size": 100, "size_vram": 50}]}
    monkeypatch.setattr("ollux.ps.gpu_info", lambda: None)
    show_status(client_for(ps_server), json_output=True)
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["models"][0]["gpu_pct"] == 50.0
    assert payload["models"][0]["state"] == "partial"
    assert payload["gpu"] is None
    assert captured.err == "gpu stats unavailable\n"


def test_parser_registers_ps_and_json():
    args = build_parser().parse_args(["--ps", "--json"])
    assert args.ps and args.json


def test_cli_ps_json_uses_shared_view(ps_server, monkeypatch, capsys):
    ps_server.payload = {"models": [{"name": "cli-model", "size": 100, "size_vram": 100}]}
    monkeypatch.setattr("ollux.cli.load_config", lambda: Config(host=f"http://127.0.0.1:{ps_server.server_port}"))
    monkeypatch.setattr("ollux.ps.gpu_info", lambda: [])
    assert main(["--ps", "--json"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["models"][0]["name"] == "cli-model"
    assert captured.err == ""


def test_repl_help_lists_ps_and_server_error_returns_to_prompt(ps_server, monkeypatch, capsys):
    ps_server.status = 503
    answers = iter(["/help", "/ps", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    client = client_for(ps_server)
    args = build_parser().parse_args([])
    from ollux.cli import run_interactive

    assert run_interactive(client, Config(), "test:latest", args) == 0
    captured = capsys.readouterr()
    assert "/ps                show loaded model GPU/CPU memory status" in captured.out
    assert "error: Ollama unavailable" in captured.err


def test_repl_slash_dispatch_catches_ps_error(capsys):
    class BrokenClient:
        def ps_data(self):
            raise OlluxError("cannot reach Ollama")

    result = _handle_slash(
        "/ps", client=BrokenClient(), cfg=Config(), model="m", math_mode="unicode",
        raw_mode=False, render_on=True, messages=[], args=build_parser().parse_args([]),
    )
    assert result[0] is True
    assert "cannot reach Ollama" in capsys.readouterr().err
