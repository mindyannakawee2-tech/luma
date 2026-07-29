#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

sudo mkdir -p /opt/luma/manager
sudo cp luma.py /opt/luma/manager/luma.py
sudo chmod +x /opt/luma/manager/luma.py

sudo tee /usr/local/bin/luma >/dev/null <<'EOF'
#!/usr/bin/env bash
exec python3 /opt/luma/manager/luma.py "$@"
EOF

sudo chmod +x /usr/local/bin/luma

echo "Installed LUMA V1.2.0"
luma version
