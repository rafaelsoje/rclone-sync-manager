#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
while [[ -L "$SCRIPT_PATH" ]]; do
  SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
  SCRIPT_PATH="$(readlink "$SCRIPT_PATH")"
  [[ "$SCRIPT_PATH" != /* ]] && SCRIPT_PATH="$SCRIPT_DIR/$SCRIPT_PATH"
done
PROJECT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$PROJECT_DIR"

venv_is_valid() {
  [[ -x "$VENV_PYTHON" ]] && "$VENV_PYTHON" - "$VENV_DIR" <<'PY' >/dev/null 2>&1
import pathlib
import sys

expected = pathlib.Path(sys.argv[1]).resolve()
actual = pathlib.Path(sys.prefix).resolve()
raise SystemExit(0 if actual == expected and sys.prefix != sys.base_prefix else 1)
PY
}

if ! venv_is_valid; then
  if [[ -e "$VENV_DIR" ]]; then
    echo "Ambiente virtual inválido ou movido. Recriando .venv..."
    rm -rf "$VENV_DIR"
  fi
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

export VIRTUAL_ENV="$VENV_DIR"
export PATH="$VENV_DIR/bin:$PATH"

"$VENV_PYTHON" - <<'PY' >/dev/null 2>&1 || "$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
import setuptools  # noqa: F401
import wheel  # noqa: F401
PY

deps_ok() {
  "$VENV_PYTHON" - <<'PY'
import importlib.util
import sys

required = ["PySide6", "watchdog", "yaml", "psutil"]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    print(", ".join(missing))
    sys.exit(1)
PY
}

if ! missing="$(deps_ok 2>/dev/null)"; then
  echo "Dependências ausentes na venv: $missing"
  echo "Tentando instalar dependências do projeto..."
  if ! "$VENV_PYTHON" -m pip install -e . pytest; then
    echo
    echo "Não foi possível instalar automaticamente."
    echo "Rode manualmente:"
    echo "  .venv/bin/python -m pip install --upgrade pip setuptools wheel"
    echo "  .venv/bin/python -m pip install -e . pytest"
    exit 1
  fi
fi

"$VENV_PYTHON" -m rclone_sync_manager init >/dev/null

if [[ $# -eq 0 ]]; then
  exec "$VENV_PYTHON" -m rclone_sync_manager gui
fi

exec "$VENV_PYTHON" -m rclone_sync_manager "$@"
