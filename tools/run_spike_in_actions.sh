#!/bin/bash
set -euo pipefail

echo "=========================================="
echo "SENTINEL-FX: MT5 Spike Actions Runner"
echo "=========================================="

python3 -m pip install --upgrade pip
python3 -m pip install "rpyc>=6.0.0,<7" requests mt5linux

echo "[1/4] Starting Docker mt5linux primary container..."
docker run -d --name mt5-spike-primary -p 18812:18812 -p 8080:8080 \
  -e LOGIN="${MT5_DEMO_LOGIN:-41286446}" \
  -e PASSWORD="${MT5_PASSWORD:-Kaiju-No.8}" \
  -e SERVER="${MT5_DEMO_SERVER:-Deriv-Demo}" \
  lprett/mt5linux:latest

echo "[2/4] Starting Docker mt5linux secondary container for concurrency check..."
docker run -d --name mt5-spike-secondary -p 18813:18812 \
  -e LOGIN="${MT5_DEMO_LOGIN:-41286446}" \
  -e PASSWORD="${MT5_PASSWORD:-Kaiju-No.8}" \
  -e SERVER="${MT5_DEMO_SERVER:-Deriv-Demo}" \
  lprett/mt5linux:latest || echo "[WARN] Secondary container start skipped"

echo "Waiting for RPyC primary bridge to become ready on port 18812..."
for i in $(seq 1 30); do
  if python3 -c "import rpyc; c=rpyc.classic.connect('localhost', 18812); c.close()" 2>/dev/null; then
    echo "[OK] Primary RPyC bridge connected on port 18812 after $((i*2))s."
    break
  fi
  sleep 2
done

echo "Checking secondary RPyC bridge on port 18813..."
for i in $(seq 1 15); do
  if python3 -c "import rpyc; c=rpyc.classic.connect('localhost', 18813); c.close()" 2>/dev/null; then
    echo "[OK] Secondary RPyC bridge connected on port 18813 after $((i*2))s."
    break
  fi
  sleep 2
done || echo "[WARN] Secondary container not ready in time"

echo "Container status:"
docker ps --filter "name=mt5-spike"

echo "[3/4] Running MT5 Spike Script..."
SPIKE_EXIT=0
python3 tools/mt5_spike.py \
  --host localhost \
  --port 18812 \
  --port-second 18813 \
  --login "${MT5_DEMO_LOGIN:-41286446}" \
  --password "${MT5_PASSWORD:-Kaiju-No.8}" \
  --server "${MT5_DEMO_SERVER:-Deriv-Demo}" \
  --out-md docs/mt5-spike.md \
  --out-json mt5_spike_result.json || SPIKE_EXIT=$?

echo "Container logs inspection (primary):"
docker logs --tail 120 mt5-spike-primary || true

if [ -f docs/mt5-spike.md ]; then
  echo "--- Spike Markdown Report Preview ---"
  head -n 45 docs/mt5-spike.md || true
fi

if [ "${SPIKE_EXIT}" -ne 0 ]; then
  echo "MT5 Spike exited with code ${SPIKE_EXIT}."
  exit ${SPIKE_EXIT}
fi

echo "MT5 Spike completed successfully."
