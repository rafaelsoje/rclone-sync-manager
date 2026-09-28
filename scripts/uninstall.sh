#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now rclone-sync-manager.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/rclone-sync-manager.service"
rm -f "$HOME/.local/bin/rsm"
rm -f "$HOME/.local/share/applications/rclone-sync-manager.desktop"
rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/rclone-sync-manager.svg"
systemctl --user daemon-reload 2>/dev/null || true
if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null; then
  gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi
echo "Rclone Sync Manager removido do systemd e ~/.local/bin."
