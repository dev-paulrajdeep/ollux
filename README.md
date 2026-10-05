# Ollux

**Ollama, but civilized.**

Ollux is a lightweight, local-first presentation and workflow layer over [Ollama](https://ollama.com). It works with **any** model you have installed, runs a **single** generation per turn, and turns raw model output into clean, readable Markdown for the terminal, files, pipes, and Obsidian.

Ollux is **not** official Ollama software. It talks only to your local Ollama daemon.

## Why it exists

Ollama is excellent at running models. Raw model output is often messy for reading and archiving: uneven blank lines, escaped Markdown, think-blocks, and LaTeX that is awkward in a terminal.

Ollux sits in front of Ollama as a thin Unix-style tool:

```
User → Ollux → Ollama → model
                ↓
         local normalization
                ↓
           clean Markdown
                ↓
    terminal / .md / Obsidian
```

Design rules:

- **One LLM generation only** — never send model output to another model for “cleanup”
- **Deterministic local formatting** — no cloud APIs, telemetry, databases, or agents
- **Treat model output as untrusted text** — never execute it
- **Token-efficient** — short system prompt; heavy lifting is local regex/normalization

## Architecture

| Module | Role |
|--------|------|
| `cli.py` | Argument parsing, stdin, interactive REPL, dispatch |
| `ollama.py` | Local HTTP client (`/api/tags`, `/api/chat` streaming) |
| `markdown.py` | Whitespace cleanup, think-strip, fence protection |
| `math.py` | Conservative LaTeX → Unicode (optional) |
| `renderer.py` | Optional `glow -` pipe, else plain Markdown |
| `config.py` | `~/.config/ollux/config.toml` |
| `obsidian.py` | Slug filenames, optional YAML frontmatter |
| `utils.py` | Safe writes, ANSI strip, heuristics |

Runtime dependencies: **Python 3.11+ standard library only**. Optional host tool: [`glow`](https://github.com/charmbracelet/glow). Development: `pytest`.

## Installation

### Requirements

- Linux (Arch and similar)
- Python 3.11+
- A running [Ollama](https://ollama.com) daemon with at least one model
- Optional: `glow` for pretty terminal Markdown (`pacman -S glow` on Arch)

### User-local install

On Arch Linux and other PEP 668 systems, the installer creates a project virtualenv and links `ollux` into `~/.local/bin`:

```bash
git clone <this-repo> ollux
cd ollux
chmod +x install.sh
./install.sh
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Ensure `~/.local/bin` is on your `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Verify

```bash
ollux --version
ollux --help
ollux --list
```

## Quick start

```bash
ollux --setup                          # optional: default model, vault path
ollux --list                           # installed Ollama models
ollux ornith-1.5:9b "Explain eigenvalues"
ollux --model ornith-1.5:9b "Explain Fourier transforms"
echo "Explain Maxwell's equations" | ollux ornith-1.5:9b
```

Interactive chat (no prompt):

```bash
ollux ornith-1.5:9b
```

## CLI reference

| Invocation | Behavior |
|------------|----------|
| `ollux` | Interactive using `default_model` (if set) |
| `ollux <model>` | Interactive chat with that model |
| `ollux "<prompt>"` | One-shot with `default_model` |
| `ollux <model> "<prompt>"` | One-shot |
| `ollux --model <model> "<prompt>"` | Explicit model (always unambiguous) |
| `ollux --list` | List installed models |
| `ollux --raw …` | Print raw model text (no normalization) |
| `ollux --markdown …` | Normalized Markdown only; **no** terminal renderer |
| `ollux --no-render …` | Skip glow; print Markdown |
| `ollux --live …` | Stream tokens with minimal/no normalization |
| `ollux --save file.md …` | Write pure Markdown to a file |
| `ollux --obsidian …` | Save into configured Obsidian vault |
| `ollux --math unicode\|latex` | Math handling |
| `ollux --force` | Allow overwriting for `--save` / `--obsidian` |
| `ollux --setup` | Interactive config writer |
| `ollux --debug` | Extra diagnostics on errors |
| `ollux --version` / `--help` | Version / help |

### Model vs prompt ambiguity

Ollux does **not** call `/api/tags` for ordinary prompts. It uses a local heuristic (`name:tag`-shaped tokens look like models; phrases with spaces look like prompts). Prefer `--model` when you want zero ambiguity.

Model discovery is cached **within a process** (e.g. `/models` in the REPL).

### Stdin and pipes

```bash
echo "Explain Maxwell's equations" | ollux ornith-1.5:9b
cat prompt.txt | ollux --markdown ornith-1.5:9b
```

### Default pipeline vs `--live`

**Default:** collect the streamed response → normalize locally → render **once** (glow or plain).

**`--live`:** print tokens as they arrive; skip post-normalization. Ideal for watching generation; not ideal for archives.

**`--markdown`:** always implies no glow / no TUI chrome — stdout is normalized Markdown only.

## Interactive mode

```text
Ollux · ornith-1.5:9b
Type /help for commands, /quit to exit.

> Explain π
```

Commands:

| Command | Action |
|---------|--------|
| `/help` | Show commands |
| `/model [name]` | Show or switch model |
| `/models` | List installed models |
| `/raw` | Toggle raw output |
| `/render` | Toggle terminal rendering |
| `/save <file>` | Save last assistant reply as Markdown |
| `/clear` | Clear conversation (keeps system prompt) |
| `/system` | Show system prompt |
| `/quit` | Exit |

Session context lives **in memory only**.

## Markdown normalization

Canonical internal format is GitHub-Flavored Markdown.

Local steps (deterministic):

1. Protect fenced code blocks (`` ``` `` / `~~~`)
2. Strip obvious `<think>…</think>` / `<thinking>…</thinking>` wrappers
3. Normalize newlines, trailing spaces, excessive blank lines
4. Undo a few accidental Markdown escapes
5. Optional conservative math conversion
6. Restore code fences **exactly**

Ollux does **not** summarize, paraphrase, reorder, change meaning, edit code, or invent content.

## Math

Default: `--math unicode` (terminal-friendly).

Safe examples:

| LaTeX | Unicode |
|-------|---------|
| `\alpha` | α |
| `\lambda` | λ |
| `\infty` | ∞ |
| `\partial` | ∂ |
| `\nabla` | ∇ |
| `\cdot` / `\times` | × |
| `\rightarrow` | → |
| `\leq` / `\geq` / `\neq` | ≤ ≥ ≠ |
| `\pm` | ± |
| `\sum` / `\int` | Σ ∫ |
| `\sqrt{x}` | √x |
| `\frac{a}{b}` | a/b (simple, non-nested only) |

Complex or uncertain forms are left unchanged. **Nothing inside fenced code is converted.**

`--math latex` preserves LaTeX/MathJax (good for Obsidian and MathJax renderers).

For `--obsidian`, math defaults to **latex** unless you override with `--math` or `obsidian_math_mode`.

## Rendering

If `glow` is on `PATH` and rendering is enabled:

```text
normalized Markdown → piped to `glow -` → terminal
```

No temporary files. If glow is missing or fails, Ollux prints readable plain Markdown.

`--markdown` and `--no-render` skip glow entirely.

## Saving files

```bash
ollux --save notes/eigen.md ornith-1.5:9b "Explain eigenvalues"
ollux --force --save notes/eigen.md ornith-1.5:9b "Again"
```

Saved files contain **pure Markdown**:

- no ANSI escapes
- no glow output
- no debug text

Existing files are **not** overwritten unless `--force` is set (same rule for Obsidian).

## Obsidian

```bash
ollux --setup   # set obsidian_directory
ollux --obsidian ornith-1.5:9b "Explain Fourier transforms"
# → <vault>/explain-fourier-transforms.md
```

Optional YAML frontmatter includes `title`, `model`, `created`, and an `ollux` tag. Use `--no-frontmatter` to omit it.

## Configuration

Path: `~/.config/ollux/config.toml` (override with `OLLUX_CONFIG`).

```toml
default_model = "ornith-1.5:9b"
host = "http://127.0.0.1:11434"
renderer = "glow"
math_mode = "unicode"
stream = true
obsidian_directory = "/path/to/vault"
obsidian_math_mode = "latex"
```

Run `ollux --setup` for an interactive wizard. Fields are validated before write:

- `host` — http(s) URL with hostname
- `renderer` — `glow` or `plain` (name or number)
- `math_mode` / `obsidian_math_mode` — `unicode` or `latex`
- `default_model` — must exist in Ollama when reachable (listed for selection); warned but allowed if Ollama is down
- `obsidian_directory` — empty or a usable path (`~` expanded); warns if missing

Invalid input is rejected and re-prompted. The config is written **atomically** only after the full configuration validates, so a failed setup cannot corrupt an existing file.

**Precedence:** CLI flags > environment (`OLLUX_HOST`, `OLLUX_MODEL`) > config file > built-in defaults.

## Token-efficiency philosophy

The system prompt is short (~100–200 tokens). It asks for clean GFM, sensible structure, and no hidden reasoning — **not** a full formatting spec. Cleanup is local and free of extra model calls. That keeps latency and token use predictable.

## Security

- Never executes model-generated commands or scripts
- No `eval` / `exec` of model text
- Subprocess use is limited to optional `glow`
- Model output is treated as untrusted display text
- No cloud calls, telemetry, or network destinations other than your configured Ollama host

## Troubleshooting

| Symptom | What to try |
|---------|-------------|
| `cannot reach Ollama` | Start the daemon (`ollama serve`); check `host` / `OLLUX_HOST` |
| Model not found | `ollux --list` / `ollama pull <model>` |
| Ambiguous model vs prompt | Use `--model <name>` |
| Ugly terminal output | Install `glow`, or use `--markdown` |
| File exists | Add `--force` |
| Obsidian path error | `ollux --setup` or set `obsidian_directory` |

Debug:

```bash
ollux --debug --model ornith-1.5:9b "ping"
```

## Development and testing

```bash
python3 -m pip install --user -e ".[dev]"
pytest
```

Unit tests **do not** require a live Ollama server. They cover math, Markdown/fences, config precedence, filenames, Obsidian output, CLI parsing, stdin, ANSI stripping, and connection errors.

## Benchmarking

Run a repeatable local inference benchmark with the configured default model, or choose one explicitly:

```bash
ollux --bench
ollux --bench --model qwen3:8b "Explain why the sky is blue."
ollux --bench --model qwen3:8b --runs 7 --warmup 2 --num-predict 256 --json > benchmark.json
```

The default prompt is fixed so results are comparable; a positional prompt or piped stdin can override it. The report includes:

- `ttft_s`: wall time from sending the request to the first non-empty generated text.
- `gen_tok_s` / `prompt_tok_s`: generated and prompt tokens per second, calculated from Ollama's evaluation counts and durations.
- `load_s` / `total_s`: model load and full request durations reported by Ollama.
- `eval_count` / `prompt_eval_count`: generated and processed prompt token counts.
- `cold_start_s`: wall time for the first request, only when `/api/ps` shows that the model was not already resident.

The memory section reports model size, VRAM-resident size, and estimated offload percentage from `/api/ps`. If `nvidia-smi` is available, GPU name, memory, power, and temperature are included. The JSON object contains settings, each measured run, median/min/max summaries, `/api/ps` information, and GPU information (`null` when unavailable).

The median is the headline statistic because an occasional slow run can skew the mean. Warmup runs are discarded because they include initial model loading and cache effects. Results still depend on thermals, power mode, and background GPU load; record those conditions when publishing benchmark numbers.

Manual smoke (with Ollama running):

```bash
ollux --list
ollux --markdown ornith-1.5:9b "Say hello in one sentence."
echo "What is 2+2?" | ollux --markdown ornith-1.5:9b
ollux --save /tmp/ollux-smoke.md --force ornith-1.5:9b "Name three quarks."
```

## Limitations

- Depends on a local Ollama-compatible HTTP API
- Normalization is heuristic, not a full Markdown parser
- Math conversion is intentionally conservative
- `--live` trades cleanliness for immediacy
- Interactive history is not persisted
- Not a multi-agent framework, RAG stack, or cloud client

## License

MIT — see [LICENSE](LICENSE).
