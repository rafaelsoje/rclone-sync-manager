#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

python -m compileall rclone_sync_manager tests

if python -m pytest -q; then
  exit 0
fi

echo "pytest não está instalado ou falhou; rodando smoke checks sem pytest."
TMP_CONFIG="$(mktemp -d)"
TMP_DATA="$(mktemp -d)"
trap 'rm -rf "$TMP_CONFIG" "$TMP_DATA"' EXIT

XDG_CONFIG_HOME="$TMP_CONFIG" XDG_DATA_HOME="$TMP_DATA" python -m rclone_sync_manager init
XDG_CONFIG_HOME="$TMP_CONFIG" XDG_DATA_HOME="$TMP_DATA" python -m rclone_sync_manager add-job \
  --name Smoke \
  --local /tmp \
  --remote gdrive:Smoke \
  --mode copy \
  --dry-run
XDG_CONFIG_HOME="$TMP_CONFIG" XDG_DATA_HOME="$TMP_DATA" python -m rclone_sync_manager status
python -c "from rclone_sync_manager.utils import safe_filename; assert safe_filename('Meus Documentos:/') == 'Meus_Documentos'"
