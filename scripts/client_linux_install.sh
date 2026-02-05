#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "[error] This installer is designed for Linux."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[error] python3 is not installed."
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[info] Installing Belanova (Linux client mode)..."
python3 "$ROOT_DIR/scripts/bootstrap.py" --install-system-deps --upgrade-pip --torch cpu "$@"

if [[ -f "$ROOT_DIR/.env" ]]; then
  api_key_line="$(grep -E '^OPENROUTER_API_KEY=' "$ROOT_DIR/.env" || true)"
  if [[ -z "$api_key_line" || "$api_key_line" == "OPENROUTER_API_KEY=" || "$api_key_line" == "OPENROUTER_API_KEY=sk-or-..." ]]; then
    echo "[warn] Configure OPENROUTER_API_KEY in $ROOT_DIR/.env before running 'belanova'."
  fi
fi

echo "[ok] Installation complete."
if command -v belanova >/dev/null 2>&1; then
  echo "[ok] Run: belanova"
else
  echo "[ok] Run: $ROOT_DIR/.venv/bin/belanova"
fi
