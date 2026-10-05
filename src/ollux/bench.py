"""Local Ollama inference benchmark support."""

from __future__ import annotations

import json
import shutil
import statistics
import subprocess
import time
from collections.abc import Callable
from typing import Any

from ollux.ollama import OllamaClient
from ollux.utils import OlluxError, eprint

DEFAULT_PROMPT = "In one concise paragraph, explain why the sky appears blue."
METRICS = (
    "ttft_s",
    "gen_tok_s",
    "prompt_tok_s",
    "load_s",
    "total_s",
    "eval_count",
    "prompt_eval_count",
)


def summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Return median/min/max for each metric over valid benchmark runs."""
    summary: dict[str, Any] = {}
    for metric in METRICS:
        values = [run[metric] for run in runs if run.get("valid") and run.get(metric) is not None]
        if not values:
            summary[metric] = {"median": None, "min": None, "max": None}
            continue
        summary[metric] = {
            "median": statistics.median(values),
            "min": min(values),
            "max": max(values),
        }
    return summary


def run_once(
    client: OllamaClient,
    model: str,
    prompt: str,
    *,
    num_predict: int,
    seed: int,
    temperature: float,
) -> dict[str, Any]:
    body = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {"num_predict": num_predict, "seed": seed, "temperature": temperature},
    }
    started = time.perf_counter()
    ttft: float | None = None
    final: dict[str, Any] | None = None
    for event in client.generate_stream(body):
        if ttft is None and event.get("response"):
            ttft = time.perf_counter() - started
        if event.get("done"):
            final = event
    elapsed = time.perf_counter() - started
    if final is None:
        raise OlluxError("benchmark generation stream ended without a done chunk")

    required = ("eval_count", "eval_duration", "prompt_eval_count", "prompt_eval_duration", "load_duration", "total_duration")
    missing = [field for field in required if field not in final]
    if missing:
        return {"valid": False, "error": "final chunk missing fields: " + ", ".join(missing), "wall_s": elapsed, "ttft_s": ttft}
    if not isinstance(final["eval_duration"], (int, float)) or final["eval_duration"] == 0:
        return {"valid": False, "error": "eval_duration is zero or invalid", "wall_s": elapsed, "ttft_s": ttft}
    if ttft is None:
        return {"valid": False, "error": "stream contained no non-empty response token", "wall_s": elapsed, "ttft_s": None}
    try:
        eval_count = int(final["eval_count"])
        prompt_count = int(final["prompt_eval_count"])
        eval_duration = float(final["eval_duration"])
        prompt_duration = float(final["prompt_eval_duration"])
        load_duration = float(final["load_duration"])
        total_duration = float(final["total_duration"])
        if prompt_duration == 0:
            raise ValueError("prompt_eval_duration is zero")
    except (TypeError, ValueError, OverflowError) as exc:
        return {"valid": False, "error": f"invalid final metrics: {exc}", "wall_s": elapsed, "ttft_s": ttft}
    return {
        "valid": True,
        "ttft_s": ttft,
        "gen_tok_s": eval_count / (eval_duration / 1e9),
        "prompt_tok_s": prompt_count / (prompt_duration / 1e9),
        "load_s": load_duration / 1e9,
        "total_s": total_duration / 1e9,
        "eval_count": eval_count,
        "prompt_eval_count": prompt_count,
        "wall_s": elapsed,
    }


def gpu_info() -> dict[str, Any] | None:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return None
    query = [
        executable,
        "--query-gpu=name,memory.used,memory.total,power.draw,temperature.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(query, capture_output=True, text=True, timeout=3, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    rows = []
    for line in result.stdout.splitlines():
        fields = [part.strip() for part in line.split(",")]
        if len(fields) == 5:
            rows.append(dict(zip(("name", "memory_used_mb", "memory_total_mb", "power_w", "temperature_c"), fields)))
    return {"gpus": rows} if rows else None


def benchmark(
    client: OllamaClient,
    model: str,
    prompt: str,
    *,
    runs: int,
    warmup: int,
    num_predict: int,
    seed: int = 0,
    temperature: float = 0.0,
    progress: Callable[[str], None] = eprint,
) -> dict[str, Any]:
    before = client.running_models()
    resident = next((item for item in before if item.get("name", item.get("model")) == model), None)
    cold_start_s: float | None = None
    results: list[dict[str, Any]] = []
    settings = {"model": model, "prompt": prompt, "runs": runs, "warmup": warmup, "num_predict": num_predict, "seed": seed, "temperature": temperature}

    def execute() -> tuple[dict[str, Any], float]:
        start = time.perf_counter()
        result = run_once(client, model, prompt, num_predict=num_predict, seed=seed, temperature=temperature)
        return result, time.perf_counter() - start

    total_unmeasured = warmup
    if not resident:
        progress("Model is not resident; measuring the first run as cold start.")
    cold_measured = False
    try:
        for index in range(total_unmeasured):
            result, wall = execute()
            if index == 0 and not resident:
                cold_start_s = wall
                cold_measured = True
            if not result.get("valid"):
                progress(f"Warmup {index + 1} invalid: {result['error']}")
        if warmup:
            progress(f"Completed {warmup} warmup run(s).")
        for index in range(runs):
            result, wall = execute()
            if index == 0 and not resident and not cold_measured:
                cold_start_s = wall
            result["run"] = index + 1
            results.append(result)
            if not result.get("valid"):
                progress(f"Run {index + 1} invalid: {result['error']}")
    except KeyboardInterrupt:
        progress("Benchmark interrupted; reporting completed runs.")
        interrupted = True
    else:
        interrupted = False

    after = client.running_models()
    gpu = gpu_info()
    ps_model = next((item for item in after if item.get("name", item.get("model")) == model), None)
    ps_info = None
    if ps_model is not None:
        size = ps_model.get("size")
        size_vram = ps_model.get("size_vram")
        offload = None
        if isinstance(size, (int, float)) and size > 0 and isinstance(size_vram, (int, float)):
            offload = 1 - size_vram / size
        ps_info = {"model": ps_model.get("name", ps_model.get("model")), "size": size, "size_vram": size_vram, "offload_pct": offload}
        if offload is not None and size_vram < size:
            progress(f"Warning: {offload:.1%} of the model is on CPU; generation speed will drop.")
    if gpu is None:
        progress("gpu stats unavailable")
    valid_count = sum(bool(item.get("valid")) for item in results)
    if valid_count < runs:
        progress(f"Only {valid_count} of {runs} requested measured runs were valid.")
    return {"settings": settings, "cold_start_s": cold_start_s, "runs": results, "summary": summarize(results), "ps": ps_info, "gpu": gpu, "interrupted": interrupted}


def print_human(result: dict[str, Any]) -> None:
    settings = result["settings"]
    print(f"Model: {settings['model']}  Runs: {len(result['runs'])}/{settings['runs']}")
    if result["cold_start_s"] is not None:
        print(f"Cold start: {result['cold_start_s']:.3f} s")
    print("Metric            Median       Min       Max")
    for metric in METRICS:
        stats = result["summary"][metric]
        unit = " tok/s" if metric.endswith("tok_s") else ("" if metric.endswith("count") else " s")
        vals = ["—" if stats[key] is None else f"{stats[key]:.3f}{unit}" for key in ("median", "min", "max")]
        print(f"{metric:<16} {vals[0]:>9} {vals[1]:>9} {vals[2]:>9}")
    ps = result["ps"]
    print("Memory / offload")
    if ps is None:
        print("  model memory info unavailable")
    else:
        print(f"  size: {ps['size']} bytes; VRAM: {ps['size_vram']} bytes")
        if ps["offload_pct"] is not None:
            print(f"  offload: {ps['offload_pct']:.1%}")
    if result["gpu"] is not None:
        for gpu in result["gpu"]["gpus"]:
            print(f"  GPU: {gpu['name']}, memory {gpu['memory_used_mb']}/{gpu['memory_total_mb']} MB, power {gpu['power_w']} W, {gpu['temperature_c']} °C")
    if result["interrupted"]:
        print("Interrupted; partial results shown.")


def print_json(result: dict[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))
