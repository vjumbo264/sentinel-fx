#!/bin/bash
set -euo pipefail

echo "=========================================="
echo "SENTINEL-FX: MT5 Spike Actions Runner"
echo "=========================================="

python3 -m pip install --upgrade pip
python3 -m pip install mt5linux rpyc requests

STACK_STARTED=0

# Attempt Option A: Docker mode with lprett/mt5linux
echo "[1/3] Trying Docker mode with lprett/mt5linux..."
if docker pull lprett/mt5linux:latest 2>/dev/null; then
  echo "Docker pull succeeded. Launching container..."
  docker run -d --name mt5-spike-primary -p 18812:18812 \
    -e MT5_LOGIN="${MT5_DEMO_LOGIN:-41286446}" \
    -e MT5_PASSWORD="${MT5_PASSWORD:-Kaiju-No.8}" \
    -e MT5_SERVER="${MT5_DEMO_SERVER:-Deriv-Demo}" \
    lprett/mt5linux:latest || true
  
  # Allow container to boot RPyC
  sleep 8
  if nc -z localhost 18812 2>/dev/null || curl -s localhost:18812 2>/dev/null || python3 -c "import socket; s=socket.socket(); s.connect(('localhost', 18812))" 2>/dev/null; then
    echo "[OK] Docker mt5linux responding on port 18812."
    STACK_STARTED=1
  fi
fi

# Attempt Option B: Wine + mt5server.exe + Deriv MT5 terminal if Docker not ready
if [ "$STACK_STARTED" -eq 0 ]; then
  echo "[2/3] Setting up Wine + Deriv MT5 + mt5server.exe fallback..."
  sudo dpkg --add-architecture i386 || true
  sudo apt-get update -qq
  sudo apt-get install -y -qq wine wine64 xvfb curl netcat-openbsd

  mkdir -p /tmp/mt5setup
  cd /tmp/mt5setup

  echo "Downloading mt5server.exe..."
  curl -sSL -o mt5server.exe "https://github.com/lucas-campagna/mt5linux/releases/download/server-1.1.1/mt5server.exe"

  echo "Downloading Deriv MT5 installer..."
  curl -sSL -o deriv5setup.exe "https://download.mql5.com/cdn/web/deriv.com.limited/mt5/deriv5setup.exe"

  echo "Running silent installer in Xvfb..."
  xvfb-run -a wine deriv5setup.exe /auto &
  sleep 30

  echo "Starting mt5server.exe on port 18812..."
  xvfb-run -a wine mt5server.exe -p 18812 &
  sleep 10
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

echo "MT5 Spike finished successfully."
