#!/usr/bin/env bash
# User-local install for ollux. No system-wide pip required.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: python3 not found" >&2
  exit 1
fi

echo "Installing ollux (user-local, editable)…"
"$PYTHON" -m pip install --user -e ".[dev]"

BIN_DIR="$("$PYTHON" -c 'import site; print(site.USER_BASE)')/bin"
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo
  echo "Note: add this to your shell rc so 'ollux' is found:"
  echo "  export PATH=\"$BIN_DIR:\$PATH\""
fi

echo
echo "Done. Try: ollux --help"
