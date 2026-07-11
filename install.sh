#!/usr/bin/env bash
set -euo pipefail

# LUMA GitHub Pages installer.
# Upload this whole folder to GitHub Pages.
# Default URL below is for mindyannakawee2-tech/luma-site.
# Override anytime with:
#   curl -fsSL https://YOUR.github.io/luma-site/install.sh | LUMA_BASE_URL=https://YOUR.github.io/luma-site bash

BASE_URL="${LUMA_BASE_URL:-https://mindyannakawee2-tech.github.io/luma-site}"
PREFIX="${PREFIX:-/usr/local}"
BINDIR="$PREFIX/bin"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

need_cmd() { command -v "$1" >/dev/null 2>&1; }

pm_detect() {
  for pm in apt dnf zypper pacman apk xbps-install eopkg; do
    if need_cmd "$pm"; then echo "$pm"; return 0; fi
  done
  echo "unknown"
}

install_python_hint() {
  pm="$(pm_detect)"
  echo "Python 3 is required. Detected package manager: $pm"
  case "$pm" in
    apt) echo "Run: sudo apt update && sudo apt install -y python3 curl" ;;
    dnf) echo "Run: sudo dnf install -y python3 curl" ;;
    zypper) echo "Run: sudo zypper install -y python3 curl" ;;
    pacman) echo "Run: sudo pacman -Sy --needed python curl" ;;
    apk) echo "Run: sudo apk add python3 curl" ;;
    xbps-install) echo "Run: sudo xbps-install -S python3 curl" ;;
    eopkg) echo "Run: sudo eopkg install python3 curl" ;;
    *) echo "Install python3 and curl/wget using your distro package manager." ;;
  esac
}

if ! need_cmd python3; then
  install_python_hint
  exit 1
fi

echo "Installing LUMA from: $BASE_URL"

if need_cmd curl; then
  curl -fsSL "$BASE_URL/luma.py" -o "$TMPDIR/luma.py"
elif need_cmd wget; then
  wget -qO "$TMPDIR/luma.py" "$BASE_URL/luma.py"
else
  python3 - "$BASE_URL/luma.py" "$TMPDIR/luma.py" <<'PY'
import sys, urllib.request
urllib.request.urlretrieve(sys.argv[1], sys.argv[2])
PY
fi

chmod +x "$TMPDIR/luma.py"

if [ "$(id -u)" -eq 0 ]; then
  install -d "$BINDIR"
  install -m 755 "$TMPDIR/luma.py" "$BINDIR/luma"
elif need_cmd sudo; then
  sudo install -d "$BINDIR"
  sudo install -m 755 "$TMPDIR/luma.py" "$BINDIR/luma"
else
  mkdir -p "$HOME/.local/bin"
  install -m 755 "$TMPDIR/luma.py" "$HOME/.local/bin/luma"
  BINDIR="$HOME/.local/bin"
fi

echo "Installed: $BINDIR/luma"
"$BINDIR/luma" --version || true

echo
echo "Optional: add this page as a LUMA app repo:"
echo "  luma install pkg-get $BASE_URL"
