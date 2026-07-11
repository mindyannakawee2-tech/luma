#!/usr/bin/env bash
set -e

# ============================================================
# LUMA Installer
# Linux + macOS
# ============================================================

LUMA_NAME="LUMA"
LUMA_VERSION="0.4"
LUMA_BASE_URL="${LUMA_BASE_URL:-https://mindyannakawee2-tech.github.io/luma}"

echo "============================================"
echo "Installing $LUMA_NAME Package Manager"
echo "Version: $LUMA_VERSION"
echo "Source:  $LUMA_BASE_URL"
echo "============================================"
echo

OS_NAME="$(uname -s)"

case "$OS_NAME" in
  Linux)
    PLATFORM="linux"
    INSTALL_MODE="system"
    LUMA_HOME="/opt/luma"
    LUMA_APPS="/opt/luma/apps"
    LUMA_BIN="/usr/local/bin/luma"
    LUMA_MANAGER="$LUMA_HOME/manager"
    LUMA_CACHE="/var/cache/luma"
    LUMA_REGISTRY="/var/lib/luma"
    NEED_SUDO="yes"
    ;;
  Darwin)
    PLATFORM="macos"
    INSTALL_MODE="user"
    LUMA_HOME="$HOME/Library/Application Support/LUMA"
    LUMA_APPS="$LUMA_HOME/apps"
    LUMA_BIN="/usr/local/bin/luma"
    LUMA_MANAGER="$LUMA_HOME/manager"
    LUMA_CACHE="$HOME/Library/Caches/LUMA"
    LUMA_REGISTRY="$LUMA_HOME/registry"
    NEED_SUDO="mixed"
    ;;
  *)
    echo "Unsupported OS: $OS_NAME"
    exit 1
    ;;
esac

echo "Detected platform: $PLATFORM"
echo

# ------------------------------------------------------------
# Check required tools
# ------------------------------------------------------------

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required but not installed."
  echo

  if [ "$PLATFORM" = "linux" ]; then
    echo "Install Python 3 using your distro package manager:"
    echo
    echo "Ubuntu/Debian:"
    echo "  sudo apt update && sudo apt install -y python3"
    echo
    echo "Fedora:"
    echo "  sudo dnf install -y python3"
    echo
    echo "Arch:"
    echo "  sudo pacman -S python"
    echo
  else
    echo "Install Python 3 from:"
    echo "  https://www.python.org/downloads/macos/"
    echo
    echo "Or with Homebrew:"
    echo "  brew install python"
    echo
  fi

  exit 1
fi

if command -v curl >/dev/null 2>&1; then
  DOWNLOAD_CMD="curl -fsSL"
elif command -v wget >/dev/null 2>&1; then
  DOWNLOAD_CMD="wget -qO-"
else
  echo "ERROR: curl or wget is required."
  exit 1
fi

# ------------------------------------------------------------
# Sudo helper
# ------------------------------------------------------------

run_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

write_root_file() {
  TARGET="$1"
  CONTENT="$2"

  if [ "$(id -u)" -eq 0 ]; then
    printf "%s\n" "$CONTENT" > "$TARGET"
  else
    printf "%s\n" "$CONTENT" | sudo tee "$TARGET" >/dev/null
  fi
}

# ------------------------------------------------------------
# Create folders
# ------------------------------------------------------------

echo "Creating LUMA folders..."

if [ "$PLATFORM" = "linux" ]; then
  run_root mkdir -p "$LUMA_HOME"
  run_root mkdir -p "$LUMA_MANAGER"
  run_root mkdir -p "$LUMA_APPS"
  run_root mkdir -p "$LUMA_CACHE"
  run_root mkdir -p "$LUMA_REGISTRY"
else
  mkdir -p "$LUMA_HOME"
  mkdir -p "$LUMA_MANAGER"
  mkdir -p "$LUMA_APPS"
  mkdir -p "$LUMA_CACHE"
  mkdir -p "$LUMA_REGISTRY"
fi

# ------------------------------------------------------------
# Download luma.py
# ------------------------------------------------------------

echo "Downloading luma.py..."

TMP_LUMA="$(mktemp)"

if ! $DOWNLOAD_CMD "$LUMA_BASE_URL/luma.py" > "$TMP_LUMA"; then
  echo "ERROR: Could not download:"
  echo "$LUMA_BASE_URL/luma.py"
  rm -f "$TMP_LUMA"
  exit 1
fi

if [ ! -s "$TMP_LUMA" ]; then
  echo "ERROR: Downloaded luma.py is empty."
  rm -f "$TMP_LUMA"
  exit 1
fi

if [ "$PLATFORM" = "linux" ]; then
  run_root cp "$TMP_LUMA" "$LUMA_MANAGER/luma.py"
  run_root chmod +x "$LUMA_MANAGER/luma.py"
else
  cp "$TMP_LUMA" "$LUMA_MANAGER/luma.py"
  chmod +x "$LUMA_MANAGER/luma.py"
fi

rm -f "$TMP_LUMA"

# ------------------------------------------------------------
# Create launcher
# ------------------------------------------------------------

echo "Creating luma command..."

LAUNCHER_CONTENT='#!/usr/bin/env bash
set -e

OS_NAME="$(uname -s)"

case "$OS_NAME" in
  Linux)
    LUMA_MANAGER="/opt/luma/manager/luma.py"
    ;;
  Darwin)
    LUMA_MANAGER="$HOME/Library/Application Support/LUMA/manager/luma.py"
    ;;
  *)
    echo "Unsupported OS: $OS_NAME"
    exit 1
    ;;
esac

exec python3 "$LUMA_MANAGER" "$@"
'

if [ "$PLATFORM" = "linux" ]; then
  write_root_file "$LUMA_BIN" "$LAUNCHER_CONTENT"
  run_root chmod +x "$LUMA_BIN"
else
  if [ -w "/usr/local/bin" ]; then
    printf "%s\n" "$LAUNCHER_CONTENT" > "$LUMA_BIN"
    chmod +x "$LUMA_BIN"
  else
    echo "Need permission to write /usr/local/bin/luma"
    write_root_file "$LUMA_BIN" "$LAUNCHER_CONTENT"
    run_root chmod +x "$LUMA_BIN"
  fi
fi

# ------------------------------------------------------------
# Create uninstall script
# ------------------------------------------------------------

echo "Creating uninstall script..."

UNINSTALL_CONTENT='#!/usr/bin/env bash
set -e

OS_NAME="$(uname -s)"

run_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

case "$OS_NAME" in
  Linux)
    echo "Removing LUMA from Linux..."
    run_root rm -f /usr/local/bin/luma
    run_root rm -rf /opt/luma
    run_root rm -rf /var/cache/luma
    run_root rm -rf /var/lib/luma
    ;;
  Darwin)
    echo "Removing LUMA from macOS..."
    run_root rm -f /usr/local/bin/luma
    rm -rf "$HOME/Library/Application Support/LUMA"
    rm -rf "$HOME/Library/Caches/LUMA"
    ;;
  *)
    echo "Unsupported OS: $OS_NAME"
    exit 1
    ;;
esac

echo "LUMA removed."
'

if [ "$PLATFORM" = "linux" ]; then
  write_root_file "$LUMA_HOME/uninstall.sh" "$UNINSTALL_CONTENT"
  run_root chmod +x "$LUMA_HOME/uninstall.sh"
else
  printf "%s\n" "$UNINSTALL_CONTENT" > "$LUMA_HOME/uninstall.sh"
  chmod +x "$LUMA_HOME/uninstall.sh"
fi

# ------------------------------------------------------------
# PATH check
# ------------------------------------------------------------

echo

if ! command -v luma >/dev/null 2>&1; then
  echo "WARNING: /usr/local/bin may not be in your PATH."
  echo "Try opening a new terminal."
  echo
fi

# ------------------------------------------------------------
# Done
# ------------------------------------------------------------

echo "============================================"
echo "LUMA installed successfully."
echo "============================================"
echo
echo "Installed files:"
echo "  Manager:  $LUMA_MANAGER/luma.py"
echo "  Command:  $LUMA_BIN"
echo "  Apps:     $LUMA_APPS"
echo "  Registry: $LUMA_REGISTRY"
echo "  Cache:    $LUMA_CACHE"
echo
echo "Try:"
echo "  luma --version"
echo "  luma doctor"
echo
echo "To add your GitHub repo:"
echo "  luma install pkg-get $LUMA_BASE_URL"
echo
echo "To uninstall:"
if [ "$PLATFORM" = "linux" ]; then
  echo "  sudo /opt/luma/uninstall.sh"
else
  echo "  \"$HOME/Library/Application Support/LUMA/uninstall.sh\""
fi
