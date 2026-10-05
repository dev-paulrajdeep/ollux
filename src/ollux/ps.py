"""Ollama model residency and GPU status view."""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
from datetime import datetime, timezone
from io import StringIO
from typing import Any

from ollux.ollama import OllamaClient
from ollux.utils import OlluxError, eprint

# GiB uses powers of two, matching Ollama's byte-oriented memory counters.
_GIB = 1024**3


def offload(size: int | float, size_vram: int | float | None) -> dict[str, float | str | None]:
    """Calculate the GPU/CPU memory split without dividing by invalid sizes."""
    if not isinstance(size, (int, float)) or isinstance(size, bool) or size <= 0:
        return {"gpu_pct": None, "cpu_pct": None, "state": "unknown"}
    if not isinstance(size_vram, (int, float)) or isinstance(size_vram, bool) or size_vram < 0:
        return {"gpu_pct": None, "cpu_pct": None, "state": "unknown"}
    gpu_pct = min(100.0, size_vram / size * 100)
    cpu_pct = 100.0 - gpu_pct
    state = "cpu" if size_vram == 0 else ("gpu" if size_vram >= size else "partial")
    return {"gpu_pct": gpu_pct, "cpu_pct": cpu_pct, "state": state}


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _size(value: int | float | None) -> str:
    if value is None:
        return "unknown"
    amount = value / _GIB
    if amount >= 1 or amount == 0:
        return f"{amount:.2f} GiB"
    if amount >= 0.01:
        return f"{amount:.2f} GiB"
    return f"{amount:.3g} GiB"


def _until_expiry(value: Any, now: datetime) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        expiry = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        seconds = int((expiry - now).total_seconds())
    except (ValueError, OverflowError):
        return None
    if seconds <= 0:
        return None
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def gpu_info() -> list[dict[str, str | float | None]] | None:
    """Read optional device stats; any NVIDIA utility problem is non-fatal."""
    executable = shutil.which("nvidia-smi")
    if not executable:
        return None
    args = [
        executable,
        "--query-gpu=name,memory.used,memory.total,utilization.gpu,power.draw,temperature.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=3, check=True)
    except Exception:  # noqa: BLE001 - GPU telemetry must never fail the view.
        return None
    rows: list[dict[str, str | float | None]] = []
    try:
        parsed = csv.reader(StringIO(result.stdout), skipinitialspace=True)
        for fields in parsed:
            if len(fields) != 6:
                continue
            values = [field.strip() or None for field in fields]
            values = [
                None if value and value.upper() in {"[N/A]", "N/A", "NOT SUPPORTED"} else value
                for value in values
            ]
            name, used, total, utilization, power, temperature = values
            rows.append({
                "name": name,
                "memory_used_gib": _mib_to_gib(used),
                "memory_total_gib": _mib_to_gib(total),
                "utilization_pct": _float_or_none(utilization),
                "power_w": _float_or_none(power),
                "temperature_c": _float_or_none(temperature),
            })
    except (csv.Error, TypeError):
        return None
    return rows or None


def _float_or_none(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _mib_to_gib(value: str | None) -> float | None:
    # nvidia-smi reports memory in MiB; convert to GiB for consistent units.
    mib = _float_or_none(value)
    return mib / 1024 if mib is not None else None


def _clean_models(payload: dict[str, Any], warn: bool) -> list[dict[str, Any]]:
    raw = payload.get("models")
    if raw is None:
        if warn:
            eprint("note: Ollama /api/ps response has no models list")
        return []
    if not isinstance(raw, list):
        if warn:
            eprint("note: Ollama /api/ps models field is not a list")
        return []
    models = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            if warn:
                eprint(f"note: skipping malformed /api/ps model entry {index + 1}")
            continue
        name = entry.get("name") or entry.get("model")
        size = _number(entry.get("size"))
        if not isinstance(name, str) or not name.strip() or size is None:
            if warn:
                eprint(f"note: skipping /api/ps model entry {index + 1} without a valid name and size")
            continue
        vram = _number(entry.get("size_vram"))
        split = offload(size, vram)
        models.append({
            "name": name,
            "size": size,
            "size_vram": vram,
            "cpu_size": max(0, size - vram) if vram is not None else None,
            "gpu_pct": split["gpu_pct"],
            "cpu_pct": split["cpu_pct"],
            "state": split["state"],
            "context_length": entry.get("context_length"),
            "expires_at": entry.get("expires_at"),
        })
    return sorted(models, key=lambda model: model["name"].casefold())


def _display(
    models: list[dict[str, Any]],
    gpus: list[dict[str, str | float | None]] | None,
    now: datetime,
) -> tuple[str, list[str]]:
    lines: list[str] = []
    notes: list[str] = []
    if not models:
        lines.append("no models loaded")
        notes.append("Hint: Ollama unloads models after their keep-alive period; the next prompt loads one again.")
    else:
        for index, model in enumerate(models):
            if index:
                lines.append("")
            lines.append(model["name"])
            lines.append(f"  Total: {_size(model['size'])}")
            lines.append(f"  VRAM: {_size(model['size_vram'])}")
            lines.append(f"  CPU: {_size(model['cpu_size'])}")
            if model["gpu_pct"] is None:
                lines.append("  Split: unknown")
                lines.append("  Memory split could not be determined.")
            else:
                lines.append(f"  Split: {model['gpu_pct']:.0f}% GPU / {model['cpu_pct']:.0f}% CPU")
                if model["state"] == "gpu":
                    lines.append("  Fully on GPU.")
                elif model["state"] == "partial":
                    notes.append(f"Warning: {model['name']} is partly on CPU; generation will be slower than fully offloaded.")
                    notes.append("Reducing context length or using a smaller or more heavily quantized model can help.")
                elif model["state"] == "cpu":
                    notes.append(f"Warning: {model['name']} is running entirely on CPU.")
            if model["context_length"] is not None:
                lines.append(f"  Context: {model['context_length']} tokens")
            expiry = _until_expiry(model["expires_at"], now)
            if expiry:
                lines.append(f"  Unloads in: {expiry}")
        if len(models) > 1:
            total_vram = sum(model["size_vram"] or 0 for model in models)
            lines.extend(("", f"Combined VRAM: {_size(total_vram)}"))
    if gpus:
        if lines:
            lines.append("")
        for device in gpus:
            memory = "unknown"
            if device["memory_used_gib"] is not None and device["memory_total_gib"] is not None:
                memory = f"{device['memory_used_gib']:.2f}/{device['memory_total_gib']:.2f} GiB"
            line = f"GPU: {device['name'] or 'unknown'}; memory {memory}"
            if device["utilization_pct"] is not None:
                line += f"; utilization {device['utilization_pct']}%"
            if device["power_w"] is not None:
                line += f"; power {device['power_w']} W"
            if device["temperature_c"] is not None:
                line += f"; temperature {device['temperature_c']} °C"
            lines.append(line)
    return "\n".join(lines) + "\n", notes


def show_status(client: OllamaClient, *, json_output: bool = False) -> None:
    """Fetch and print the shared status view; diagnostics stay on stderr."""
    try:
        payload = client.ps_data()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OlluxError("Ollama returned malformed JSON for /api/ps") from exc
    models = _clean_models(payload, warn=True)
    devices = gpu_info()
    if devices is None:
        eprint("gpu stats unavailable")
    if json_output:
        print(json.dumps({"models": models, "gpu": {"devices": devices} if devices is not None else None}, ensure_ascii=False, indent=2))
        notes = []
    else:
        output, notes = _display(models, devices, datetime.now(timezone.utc))
        print(output, end="")
    for note in notes:
        eprint(note)
