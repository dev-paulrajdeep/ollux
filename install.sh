#!/usr/bin/env bash
# User-local install for ollux. Prefer a project venv (Arch/PEP 668 friendly).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
VENV="${OLLUX_VENV:-$ROOT/.venv}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: python3 not found" >&2
  exit 1
fi

if [[ ! -d "$VENV" ]]; then
  echo "Creating virtualenv at $VENV …"
  "$PYTHON" -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "Installing ollux (editable) into $VENV …"
python -m pip install -U pip
python -m pip install -e ".[dev]"

# Symlink into ~/.local/bin when possible
TARGET="$HOME/.local/bin"
mkdir -p "$TARGET"
ln -sfn "$VENV/bin/ollux" "$TARGET/ollux"

if [[ ":$PATH:" != *":$TARGET:"* ]]; then
  echo
  echo "Note: add this to your shell rc so 'ollux' is found:"
  echo "  export PATH=\"$TARGET:\$PATH\""
fi

echo
echo "Done. Try: ollux --help"
echo "Tests:    $VENV/bin/pytest"
