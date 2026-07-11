#!/usr/bin/env bash
set -e

# ============================================================
# LUMA Uninstaller
# Linux + macOS
# ============================================================

echo "============================================"
echo "Uninstalling LUMA Package Manager"
echo "============================================"
echo

OS_NAME="$(uname -s)"

run_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

ask_confirm() {
  echo "This will remove LUMA manager files."
  echo
  echo "Installed LUMA apps may also be removed if you choose full removal."
  echo
  printf "Continue? [y/N]: "
  read -r ANSWER

  case "$ANSWER" in
    y|Y|yes|YES)
      ;;
    *)
      echo "Cancelled."
      exit 0
      ;;
  esac
}

ask_full_remove() {
  echo
  printf "Remove installed LUMA apps too? [y/N]: "
  read -r FULL

  case "$FULL" in
    y|Y|yes|YES)
      FULL_REMOVE="yes"
      ;;
    *)
      FULL_REMOVE="no"
      ;;
  esac
}

ask_confirm
ask_full_remove

case "$OS_NAME" in
  Linux)
    echo
    echo "Detected Linux."

    LUMA_BIN="/usr/local/bin/luma"
    LUMA_HOME="/opt/luma"
    LUMA_CACHE="/var/cache/luma"
    LUMA_REGISTRY="/var/lib/luma"

    echo "Removing command..."
    run_root rm -f "$LUMA_BIN"

    if [ "$FULL_REMOVE" = "yes" ]; then
      echo "Removing LUMA apps and manager..."
      run_root rm -rf "$LUMA_HOME"
      run_root rm -rf "$LUMA_CACHE"
      run_root rm -rf "$LUMA_REGISTRY"
    else
      echo "Removing manager only, keeping apps if possible..."
      run_root rm -rf "$LUMA_HOME/manager"
      run_root rm -f "$LUMA_HOME/uninstall.sh"
      run_root rm -rf "$LUMA_CACHE"
    fi
    ;;

  Darwin)
    echo
    echo "Detected macOS."

    LUMA_BIN="/usr/local/bin/luma"
    LUMA_HOME="$HOME/Library/Application Support/LUMA"
    LUMA_CACHE="$HOME/Library/Caches/LUMA"
    LUMA_REGISTRY="$LUMA_HOME/registry"

    echo "Removing command..."
    run_root rm -f "$LUMA_BIN"

    if [ "$FULL_REMOVE" = "yes" ]; then
      echo "Removing LUMA apps and manager..."
      rm -rf "$LUMA_HOME"
      rm -rf "$LUMA_CACHE"
    else
      echo "Removing manager only, keeping apps if possible..."
      rm -rf "$LUMA_HOME/manager"
      rm -f "$LUMA_HOME/uninstall.sh"
      rm -rf "$LUMA_CACHE"
    fi
    ;;

  *)
    echo "Unsupported OS: $OS_NAME"
    exit 1
    ;;
esac

echo
echo "============================================"
echo "LUMA uninstall completed."
echo "============================================"
echo

if command -v luma >/dev/null 2>&1; then
  echo "Warning: luma command is still found in PATH:"
  command -v luma
  echo "You may have another LUMA installation."
else
  echo "luma command removed."
fi
