#!/usr/bin/env bash
set -e
if [ -f /usr/local/bin/luma ]; then
  sudo rm -f /usr/local/bin/luma
  echo "Removed /usr/local/bin/luma"
elif [ -f "$HOME/.local/bin/luma" ]; then
  rm -f "$HOME/.local/bin/luma"
  echo "Removed ~/.local/bin/luma"
else
  echo "LUMA command not found in standard install paths."
fi
