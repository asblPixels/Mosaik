#!/bin/sh
# Mosaïk — installation en une ligne pour toutes les distributions Linux.
#   curl -fsSL https://raw.githubusercontent.com/asblPixels/Mosaik/main/scripts/install-linux.sh | sh
set -e

REPO="https://github.com/asblPixels/Mosaik"
SRC_DIR="$HOME/.local/share/mosaik-src"

say() { printf '\033[1;36m▶\033[0m %s\n' "$1"; }

ID_ALL=""
if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  ID_ALL="$ID ${ID_LIKE:-}"
fi

pkg_install() {
  case " $ID_ALL " in
    *fedora*|*rhel*|*centos*) sudo dnf install -y "$@" ;;
    *debian*|*ubuntu*)        sudo apt-get install -y "$@" ;;
    *arch*)                   sudo pacman -S --needed --noconfirm "$@" ;;
    *suse*)                   sudo zypper install -y "$@" ;;
    *gentoo*)                 echo "Gentoo : sudo emerge app-forensics/sleuthkit"; return 1 ;;
    *void*)                   sudo xbps-install -y "$@" ;;
    *alpine*)                 sudo apk add "$@" ;;
    *)                        return 1 ;;
  esac
}

say "Distribution détectée : ${PRETTY_NAME:-inconnue}"

if ! command -v python3 >/dev/null 2>&1; then
  say "Installation de Python 3…"
  pkg_install python3 || { echo "Installez Python 3 puis relancez ce script."; exit 1; }
fi

if ! command -v fls >/dev/null 2>&1; then
  printf 'Installer The Sleuth Kit (recommandé : noms de fichiers d origine) ? [O/n] '
  ans=""
  if [ -r /dev/tty ]; then read -r ans < /dev/tty || ans=""; fi
  case "$ans" in
    n|N|non|no) say "The Sleuth Kit ignoré (vous pourrez l'installer plus tard)." ;;
    *) say "Installation de The Sleuth Kit…"; pkg_install sleuthkit || say "Installation automatique impossible : installez le paquet « sleuthkit »." ;;
  esac
fi

say "Téléchargement de Mosaïk…"
if command -v git >/dev/null 2>&1; then
  if [ -d "$SRC_DIR/.git" ]; then git -C "$SRC_DIR" pull -q; else rm -rf "$SRC_DIR"; git clone -q --depth 1 "$REPO.git" "$SRC_DIR"; fi
else
  tmp=$(mktemp -d)
  curl -fsSL "$REPO/archive/refs/heads/main.tar.gz" | tar -xz -C "$tmp"
  rm -rf "$SRC_DIR"; mv "$tmp"/Mosaik-main "$SRC_DIR"; rmdir "$tmp"
fi

sh "$SRC_DIR/install.sh"
say "Terminé ! Lancez Mosaïk depuis le menu des applications ou avec : mosaik"
