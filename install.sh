#!/bin/sh
# Installation de Mosaïk pour l'utilisateur courant (aucun droit admin requis).
# Fonctionne sur toutes les distributions Linux disposant de Python 3.8+.
set -e
command -v python3 >/dev/null 2>&1 || { echo "Python 3 est requis (paquet python3)."; exit 1; }
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/mosaik"
BIN="$HOME/.local/bin"
mkdir -p "$DEST/assets/fonts" "$BIN" "$HOME/.local/share/applications"
cp "$SRC/mosaik.py" "$SRC/ui.html" "$DEST/"
cp "$SRC/assets/"*.svg "$SRC/assets/"*.png "$DEST/assets/"
cp "$SRC/assets/fonts/"* "$DEST/assets/fonts/"
chmod +x "$DEST/mosaik.py"
ln -sf "$DEST/mosaik.py" "$BIN/mosaik"
for s in 16 32 48 64 128 256 512; do
  d="$HOME/.local/share/icons/hicolor/${s}x${s}/apps"; mkdir -p "$d"
  cp "$SRC/assets/mosaik-$s.png" "$d/mosaik.png"
done
mkdir -p "$HOME/.local/share/icons/hicolor/scalable/apps"
cp "$SRC/assets/mosaik-icon.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/mosaik.svg"
sed "s|^Exec=.*|Exec=$BIN/mosaik|" "$SRC/packaging/mosaik.desktop" > "$HOME/.local/share/applications/mosaik.desktop"
update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
echo "Mosaïk est installé. Lancez-le depuis le menu des applications ou avec la commande : mosaik"
