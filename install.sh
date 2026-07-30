#!/usr/bin/env bash
set -e

echo "Uninstalling LUMA manager..."

sudo rm -f /usr/local/bin/luma
sudo rm -f /opt/luma/manager/luma.py

if [ -d /opt/luma/manager ] && [ -z "$(ls -A /opt/luma/manager 2>/dev/null)" ]; then
  sudo rmdir /opt/luma/manager
fi

if [ -d /opt/luma ] && [ -z "$(ls -A /opt/luma 2>/dev/null)" ]; then
  sudo rmdir /opt/luma
fi

echo
echo "LUMA manager removed."
echo "Installed packages and repo data were kept at:"
echo "  $HOME/.local/share/luma"
echo
echo "To remove installed LUMA apps too, run:"
echo "  rm -rf \"$HOME/.local/share/luma\""
echo
echo "To remove app shortcuts too, check:"
echo "  ls $HOME/.local/bin"
