#!/bin/bash
# Install sailing-data-exporter on HALPI2 (HALOS).
# Run once after cloning. Re-run after HALOS updates if unit is overwritten.
set -e

REPO=/home/pi/GitHub/sailing-data-exporter
VENV=/home/pi/.local/sailing-data-exporter-venv

# 1. Virtualenv
if [ ! -d "$VENV" ]; then
  echo "Creating virtualenv..."
  /usr/bin/python3 -m venv "$VENV"
fi
"$VENV"/bin/pip install -q flask werkzeug influxdb-client

# 2. Systemd unit
sudo cp "$REPO/deploy/halos/sailing-data-exporter.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sailing-data-exporter.service

# 3. Traefik routing (live immediately)
sudo cp "$REPO/../morticia-project/halos/etc/halos/traefik-dynamic.d/sailing-data-exporter.yml" \
        /etc/halos/traefik-dynamic.d/sailing-data-exporter.yml \
  || sudo cp "$(dirname "$REPO")/morticia-project/halos/etc/halos/traefik-dynamic.d/sailing-data-exporter.yml" \
             /etc/halos/traefik-dynamic.d/sailing-data-exporter.yml

echo ""
echo "Done. Check status with: sudo systemctl status sailing-data-exporter"
echo "App available at: https://halos.local/sailing-data/"
