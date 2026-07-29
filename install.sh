#!/usr/bin/env bash
set -e

LUMA_BASE_URL="https://mindyannakawee2-tech.github.io/luma"
LUMA_INSTALL_DIR="/opt/luma/manager"

echo "Installing LUMA..."

TMP_DIR="$(mktemp -d)"
cd "$TMP_DIR"

echo "Downloading luma.py..."
curl -fsSL "$LUMA_BASE_URL/luma.py" -o luma.py

sudo mkdir -p "$LUMA_INSTALL_DIR"
sudo cp luma.py "$LUMA_INSTALL_DIR/luma.py"
sudo chmod +x "$LUMA_INSTALL_DIR/luma.py"

sudo tee /usr/local/bin/luma >/dev/null <<'EOF'
#!/usr/bin/env bash
exec python3 /opt/luma/manager/luma.py "$@"
EOF

sudo chmod +x /usr/local/bin/luma

cd /
rm -rf "$TMP_DIR"

echo "Installed LUMA"
luma version
