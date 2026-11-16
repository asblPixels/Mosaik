#!/bin/sh
rm -rf "$HOME/.local/share/mosaik" "$HOME/.local/bin/mosaik" "$HOME/.local/share/applications/mosaik.desktop"
find "$HOME/.local/share/icons/hicolor" -name 'mosaik.*' -delete 2>/dev/null || true
echo "Mosaïk a été désinstallé (vos fichiers récupérés sont conservés)."
