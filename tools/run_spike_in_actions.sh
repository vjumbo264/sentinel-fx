#!/bin/bash
set -euo pipefail

echo "=========================================="
echo "SENTINEL-FX: MT5 Spike Actions Runner"
echo "=========================================="

python3 -m pip install --upgrade pip
python3 -m pip install "rpyc>=6.0.0,<7" requests

STACK_STARTED=0

# Option A: Try Docker container mode with full env mapping
echo "[1/3] Trying Docker mode with lprett/mt5linux..."
if docker pull lprett/mt5linux:latest 2>/dev/null; then
  echo "Docker pull succeeded. Launching container..."
  docker run -d --name mt5-spike-primary -p 18812:18812 \
    -e LOGIN="${MT5_DEMO_LOGIN:-41286446}" \
    -e PASSWORD="${MT5_PASSWORD:-Kaiju-No.8}" \
    -e SERVER="${MT5_DEMO_SERVER:-Deriv-Demo}" \
    -e MT5_LOGIN="${MT5_DEMO_LOGIN:-41286446}" \
    -e MT5_PASSWORD="${MT5_PASSWORD:-Kaiju-No.8}" \
    -e MT5_SERVER="${MT5_DEMO_SERVER:-Deriv-Demo}" \
    lprett/mt5linux:latest || true
  
  echo "Polling RPyC 6 bridge readiness..."
  for i in $(seq 1 30); do
    if python3 -c "import rpyc; c=rpyc.classic.connect('localhost', 18812); c.close()" 2>/dev/null; then
      echo "[OK] Docker mt5linux responding and connected on port 18812."
      STACK_STARTED=1
      break
    fi
    sleep 2
  done
  
  if [ "$STACK_STARTED" -eq 0 ]; then
    echo "[WARN] Docker container running but bridge handshake timed out. Inspecting logs..."
    docker logs --tail 50 mt5-spike-primary || true
    docker stop mt5-spike-primary 2>/dev/null || true
    docker rm mt5-spike-primary 2>/dev/null || true
  fi
fi

# Option B: Wine + Deriv MT5 + mt5server.exe fallback
if [ "$STACK_STARTED" -eq 0 ]; then
  echo "[2/3] Setting up Wine + Deriv MT5 + mt5server.exe fallback..."
  sudo dpkg --add-architecture i386 || true
  sudo apt-get update -qq
  sudo apt-get install -y -qq wine wine64 xvfb curl netcat-openbsd

  mkdir -p /tmp/mt5setup
  cd /tmp/mt5setup

  echo "Downloading mt5server.exe (v1.1.1)..."
  curl -sSL -o mt5server.exe "https://github.com/lucas-campagna/mt5linux/releases/download/server-1.1.1/mt5server.exe"

  echo "Downloading Deriv MT5 installer..."
  curl -sSL -o deriv5setup.exe "https://download.mql5.com/cdn/web/deriv.com.limited/mt5/deriv5setup.exe"

  echo "Running silent installer in Xvfb..."
  xvfb-run -a wine deriv5setup.exe /auto &
  sleep 30

  echo "Starting mt5server.exe on port 18812..."
  xvfb-run -a wine mt5server.exe -p 18812 &
  
  echo "Polling Wine RPyC 6 bridge readiness..."
  for i in $(seq 1 20); do
    if python3 -c "import rpyc; c=rpyc.classic.connect('localhost', 18812); c.close()" 2>/dev/null; then
      echo "[OK] Wine mt5server responding on port 18812."
      STACK_STARTED=1
      break
    fi
    sleep 2
  done
  cd -
fi

echo "[3/3] Running MT5 Spike Script..."
python3 tools/mt5_spike.py \
  --host localhost \
  --port 18812 \
  --login "${MT5_DEMO_LOGIN:-41286446}" \
  --password "${MT5_PASSWORD:-Kaiju-No.8}" \
  --server "${MT5_DEMO_SERVER:-Deriv-Demo}" \
  --out-md docs/mt5-spike.md \
  --out-json mt5_spike_result.json

echo "MT5 Spike completed successfully."
