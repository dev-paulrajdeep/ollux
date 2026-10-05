from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ollux.bench import _find_running_model, benchmark, run_once, summarize
from ollux.cli import build_parser, main
from ollux.ollama import OllamaClient
from ollux.utils import OlluxError


class MockOllama(ThreadingHTTPServer):
    def __init__(self, handler):
        super().__init__(("127.0.0.1", 0), handler)
        self.events = []
        self.delay = 0.0
        self.mode = "ok"
        self.loaded = False


@pytest.fixture
def mock_server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if self.path == "/api/ps":
                models = [{"name": "test:latest", "size": 1000, "size_vram": 500}] if server.loaded else []
                payload = {"models": models}
            else:
                payload = {"models": [{"name": "test:latest"}]}
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            server.events.append(request)
            server.loaded = True
            if server.mode == "http":
                self.send_error(404, "model not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            if server.delay:
                time.sleep(server.delay)
            self.wfile.write((json.dumps({"response": "x", "done": False}) + "\n").encode())
            self.wfile.flush()
            if server.mode == "no_done":
                return
            final = {
                "response": "", "done": True, "eval_count": 100,
                "eval_duration": 2_000_000_000, "prompt_eval_count": 20,
                "prompt_eval_duration": 1_000_000_000, "load_duration": 3_000_000_000,
                "total_duration": 4_000_000_000,
            }
            if server.mode == "missing":
                final.pop("eval_count")
            if server.mode == "zero":
                final["eval_duration"] = 0
            self.wfile.write((json.dumps(final) + "\n").encode())
            self.wfile.flush()

    server = MockOllama(Handler)
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


def test_known_answer_rates_and_durations(mock_server, monkeypatch):
    monkeypatch.setattr("ollux.bench.gpu_info", lambda: None)
    result = benchmark(client_for(mock_server), "test:latest", "prompt", runs=1, warmup=0, num_predict=256, progress=lambda _: None)
    assert result["runs"][0]["gen_tok_s"] == 50.0
    assert result["runs"][0]["prompt_tok_s"] == 20.0
    assert result["runs"][0]["load_s"] == 3.0


def test_median_odd_even():
    runs = [{"valid": True, "gen_tok_s": v} for v in [10, 50, 20, 40, 30]]
    assert summarize(runs)["gen_tok_s"] == {"median": 30, "min": 10, "max": 50}
    even = [{"valid": True, "gen_tok_s": v} for v in [10, 20, 50, 100]]
    assert summarize(even)["gen_tok_s"]["median"] == 35


def test_ps_matches_short_model_name():
    models = [{"name": "qwen3:8b", "size": 100, "size_vram": 100}]
    assert _find_running_model(models, "qwen3") is models[0]


def test_ttft_includes_server_delay(mock_server):
    mock_server.delay = 0.08
    result = run_once(client_for(mock_server), "test:latest", "prompt", num_predict=20, seed=0, temperature=0)
    assert result["ttft_s"] >= 0.08
    assert result["ttft_s"] < 0.08 + 1.0


def test_warmup_is_excluded(mock_server, monkeypatch):
    monkeypatch.setattr("ollux.bench.gpu_info", lambda: None)
    result = benchmark(client_for(mock_server), "test:latest", "prompt", runs=2, warmup=3, num_predict=20, progress=lambda _: None)
    assert len(mock_server.events) == 5
    assert len(result["runs"]) == 2
    assert result["summary"]["eval_count"]["median"] == 100


def test_cold_start_measured_only_when_not_resident(mock_server, monkeypatch):
    monkeypatch.setattr("ollux.bench.gpu_info", lambda: None)
    result = benchmark(client_for(mock_server), "test:latest", "prompt", runs=1, warmup=0, num_predict=20, progress=lambda _: None)
    assert result["cold_start_s"] is not None
    assert len(mock_server.events) == 1


@pytest.mark.parametrize("mode", ["zero", "missing"])
def test_invalid_final_metrics_excluded(mock_server, mode, monkeypatch):
    mock_server.mode = mode
    monkeypatch.setattr("ollux.bench.gpu_info", lambda: None)
    result = benchmark(client_for(mock_server), "test:latest", "prompt", runs=1, warmup=0, num_predict=20, progress=lambda _: None)
    assert result["runs"][0]["valid"] is False
    assert result["summary"]["gen_tok_s"]["median"] is None


def test_stream_without_done_fails(mock_server):
    mock_server.mode = "no_done"
    with pytest.raises(OlluxError, match="without a done chunk"):
        run_once(client_for(mock_server), "test:latest", "prompt", num_predict=20, seed=0, temperature=0)


def test_http_model_error_is_clear(mock_server):
    mock_server.mode = "http"
    with pytest.raises(OlluxError, match="model not found"):
        run_once(client_for(mock_server), "missing:latest", "prompt", num_predict=20, seed=0, temperature=0)


@pytest.mark.parametrize(("args", "bad"), [(["--bench", "--runs", "0"], "runs"), (["--bench", "--warmup", "-1"], "warmup"), (["--bench", "--num-predict", "abc"], "num_predict")])
def test_bench_numeric_args_reject_invalid(args, bad):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(args)
    assert exc.value.code == 2


def test_json_stdout_is_json_and_gpu_missing_is_nonfatal(monkeypatch, capsys):
    import ollux.bench

    monkeypatch.setattr(ollux.bench.shutil, "which", lambda _: None)
    monkeypatch.setattr("ollux.cli.load_config", lambda: __import__("ollux.config", fromlist=["Config"]).Config(default_model="test:latest"))
    monkeypatch.setattr("ollux.cli.OllamaClient.__init__", lambda self, host="": None)
    result = {"settings": {}, "cold_start_s": None, "runs": [], "summary": {}, "ps": None, "gpu": None, "interrupted": False}
    monkeypatch.setattr("ollux.cli.benchmark", lambda *a, **k: result)
    assert main(["--bench", "--json"]) == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert set(parsed) == {"settings", "cold_start_s", "runs", "summary", "ps", "gpu", "interrupted"}
    assert captured.err == ""


def test_cli_json_with_mock_http_and_missing_nvidia_smi(mock_server, monkeypatch, capsys):
    import ollux.bench
    from ollux.config import Config

    monkeypatch.setattr(ollux.bench.shutil, "which", lambda _: None)
    monkeypatch.setattr("ollux.cli.load_config", lambda: Config(default_model="test:latest", host=f"http://127.0.0.1:{mock_server.server_port}"))
    assert main(["--bench", "--json", "--runs", "1", "--warmup", "0"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert set(payload) == {"settings", "cold_start_s", "runs", "summary", "ps", "gpu", "interrupted"}
    assert payload["summary"]["gen_tok_s"]["median"] == 50.0
    assert payload["gpu"] is None
    assert "gpu stats unavailable" in captured.err


def test_summarize_excludes_invalid_runs():
    assert summarize([{"valid": False, "gen_tok_s": 100}, {"valid": True, "gen_tok_s": 20}])["gen_tok_s"] == {
        "median": 20, "min": 20, "max": 20,
    }


def test_ctrl_c_returns_completed_partial_runs(monkeypatch):
    from ollux.bench import benchmark

    class Client:
        calls = 0

        def running_models(self):
            return [{"name": "test:latest", "size": 100, "size_vram": 100}]

        def generate_stream(self, _body):
            self.calls += 1
            if self.calls == 2:
                raise KeyboardInterrupt
            yield {"response": "x"}
            yield {"done": True, "eval_count": 1, "eval_duration": 1_000_000_000,
                   "prompt_eval_count": 1, "prompt_eval_duration": 1_000_000_000,
                   "load_duration": 0, "total_duration": 1_000_000_000}

    monkeypatch.setattr("ollux.bench.gpu_info", lambda: None)
    result = benchmark(Client(), "test:latest", "p", runs=3, warmup=0, num_predict=2, progress=lambda _: None)
    assert result["interrupted"] is True
    assert len(result["runs"]) == 1
