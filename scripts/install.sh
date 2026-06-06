#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RSM_LINK="$HOME/.local/bin/rsm"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
SERVICE_NAME="rclone-sync-manager.service"
APP_ID="rclone-sync-manager"
DESKTOP_FILE="$APP_ID.desktop"
USER_APPLICATIONS_DIR="$HOME/.local/share/applications"
USER_ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
ICON_SOURCE="$PROJECT_DIR/assets/$APP_ID.svg"
ICON_TARGET="$USER_ICON_DIR/$APP_ID.svg"
PATH_MARKER="# rclone-sync-manager local bin"

cd "$PROJECT_DIR"

command -v "$PYTHON_BIN" >/dev/null || { echo "$PYTHON_BIN não encontrado"; exit 1; }
command -v rclone >/dev/null || echo "Aviso: rclone não encontrado. Instale/configure antes de sincronizar."

shell_profile() {
  case "${SHELL:-}" in
    */zsh) echo "$HOME/.zshrc" ;;
    */bash) echo "$HOME/.bashrc" ;;
    *) echo "$HOME/.profile" ;;
  esac
}

ensure_local_bin_on_path() {
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) return 0 ;;
  esac

  local profile
  profile="$(shell_profile)"
  mkdir -p "$(dirname "$profile")"
  touch "$profile"

  if ! grep -Fq "$PATH_MARKER" "$profile"; then
    {
      printf '\n%s\n' "$PATH_MARKER"
      printf 'export PATH="$HOME/.local/bin:$PATH"\n'
    } >> "$profile"
  fi

  echo "Adicionado ~/.local/bin ao PATH em: $profile"
  echo "Abra um novo terminal ou rode: source \"$profile\""
}

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

"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
"$VENV_PYTHON" -m pip install -e "$PROJECT_DIR"

mkdir -p "$HOME/.local/bin" "$USER_SYSTEMD_DIR" "$USER_APPLICATIONS_DIR" "$USER_ICON_DIR"
ln -sf "$VENV_DIR/bin/rsm" "$RSM_LINK"
ensure_local_bin_on_path
"$VENV_PYTHON" -m rclone_sync_manager init

cp "$PROJECT_DIR/systemd/$SERVICE_NAME" "$USER_SYSTEMD_DIR/"
cp "$ICON_SOURCE" "$ICON_TARGET"

cat > "$USER_APPLICATIONS_DIR/$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Rclone Sync Manager
Comment=Gerenciar sincronizações locais com rclone
Exec=$RSM_LINK gui
Icon=$APP_ID
Terminal=false
Categories=Network;FileTransfer;
Keywords=rclone;sync;backup;drive;cloud;
StartupNotify=true
EOF

chmod 0644 "$USER_APPLICATIONS_DIR/$DESKTOP_FILE" "$ICON_TARGET"

if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$USER_APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi

if command -v gtk-update-icon-cache >/dev/null; then
  gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

if command -v systemctl >/dev/null; then
  systemctl --user daemon-reload || {
    echo "Aviso: não foi possível recarregar o systemd de usuário agora."
    echo "Rode depois: systemctl --user daemon-reload"
  }
else
  echo "Aviso: systemctl não encontrado; serviço systemd não foi recarregado."
fi

echo "Instalado em: $PROJECT_DIR"
echo "Comando: $RSM_LINK"
echo "Atalho de aplicativos: $USER_APPLICATIONS_DIR/$DESKTOP_FILE"
echo "Para abrir a interface: rsm gui"
echo "Para iniciar com systemd: systemctl --user enable --now $SERVICE_NAME"
