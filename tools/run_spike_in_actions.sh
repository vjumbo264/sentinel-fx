#!/bin/bash
set -euo pipefail

echo "=========================================="
echo "SENTINEL-FX: MT5 Spike Actions Runner"
echo "=========================================="

python3 -m pip install --upgrade pip
python3 -m pip install "rpyc>=6.0.0,<7" requests

echo "[1/3] Starting Docker mt5linux container..."
docker run -d --name mt5-spike-primary -p 18812:18812 \
  -e LOGIN="${MT5_DEMO_LOGIN:-41286446}" \
  -e PASSWORD="${MT5_PASSWORD:-Kaiju-No.8}" \
  -e SERVER="${MT5_DEMO_SERVER:-Deriv-Demo}" \
  lprett/mt5linux:latest

echo "Waiting for RPyC bridge to become ready on port 18812..."
for i in $(seq 1 30); do
  if python3 -c "import rpyc; c=rpyc.classic.connect('localhost', 18812); c.close()" 2>/dev/null; then
    echo "[OK] RPyC bridge connected on port 18812 after $((i*2))s."
    break
  fi
  sleep 2
done

echo "Container status:"
docker ps --filter "name=mt5-spike-primary"

echo "[2/3] Running MT5 Spike Script..."
python3 tools/mt5_spike.py \
  --host localhost \
  --port 18812 \
  --login "${MT5_DEMO_LOGIN:-41286446}" \
  --password "${MT5_PASSWORD:-Kaiju-No.8}" \
  --server "${MT5_DEMO_SERVER:-Deriv-Demo}" \
  --out-md docs/mt5-spike.md \
  --out-json mt5_spike_result.json

echo "Container logs inspection:"
docker logs --tail 30 mt5-spike-primary || true

echo "MT5 Spike completed successfully."
