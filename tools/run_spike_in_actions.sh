#!/bin/bash
set -euo pipefail

echo "=========================================="
echo "SENTINEL-FX: MT5 Spike Actions Runner"
echo "=========================================="

python3 -m pip install --upgrade pip
python3 -m pip install "rpyc>=6.0.0,<7" requests

echo "[1/3] Setting up Wine + Xvfb..."
sudo dpkg --add-architecture i386 || true
sudo apt-get update -qq
sudo apt-get install -y -qq wine64 wine xvfb curl netcat-openbsd

export WINEARCH=win64
export WINEPREFIX="$HOME/.wine"
export DISPLAY=:99

echo "Initializing Wine prefix..."
Xvfb :99 -screen 0 1024x768x16 >/dev/null 2>&1 &
XVFB_PID=$!
sleep 2

wineboot -u || true
sleep 5

SETUP_DIR="/tmp/mt5setup"
mkdir -p "$SETUP_DIR"
cd "$SETUP_DIR"

echo "[2/3] Downloading Deriv MT5 installer and mt5server.exe..."
curl -sSL -o mt5server.exe "https://github.com/lucas-campagna/mt5linux/releases/download/server-1.1.1/mt5server.exe"
curl -sSL -o deriv5setup.exe "https://download.mql5.com/cdn/web/deriv.com.limited/mt5/deriv5setup.exe"

echo "Installing Deriv MT5 silently..."
wine deriv5setup.exe /auto &
INSTALLER_PID=$!

echo "Waiting for Deriv MT5 installation to complete..."
for i in $(seq 1 45); do
  TERMINAL_PATH=$(find "$HOME/.wine" -name "terminal64.exe" 2>/dev/null | head -n 1 || true)
  if [ -n "$TERMINAL_PATH" ] && [ -f "$TERMINAL_PATH" ]; then
    echo "[OK] Found terminal64.exe at: $TERMINAL_PATH"
    break
  fi
  echo "Waiting for installer... ($i/45)"
  sleep 2
done

TERMINAL_PATH=$(find "$HOME/.wine" -name "terminal64.exe" 2>/dev/null | head -n 1 || true)
if [ -z "$TERMINAL_PATH" ]; then
  echo "[WARN] Deriv installer did not produce terminal64.exe in time. Checking fallback..."
fi

# Ensure terminal is running
if [ -n "$TERMINAL_PATH" ]; then
  echo "Launching Deriv MT5 terminal in Wine..."
  wine "$TERMINAL_PATH" /portable &
  sleep 10
fi

echo "Starting mt5server.exe on port 18812..."
wine mt5server.exe -p 18812 &
SERVER_PID=$!

echo "Polling RPyC 6 bridge readiness..."
STACK_OK=0
for i in $(seq 1 30); do
  if python3 -c "import rpyc; c=rpyc.classic.connect('localhost', 18812); c.close()" 2>/dev/null; then
    echo "[OK] mt5server responding on port 18812."
    STACK_OK=1
    break
  fi
  echo "Waiting for mt5server... ($i/30)"
  sleep 2
done

if [ "$STACK_OK" -eq 0 ]; then
  echo "[FAIL] mt5server failed to start on port 18812."
fi

echo "[3/3] Running MT5 Spike Script..."
cd /home/runner/work/sentinel-fx/sentinel-fx
python3 tools/mt5_spike.py \
  --host localhost \
  --port 18812 \
  --login "${MT5_DEMO_LOGIN:-41286446}" \
  --password "${MT5_PASSWORD:-Kaiju-No.8}" \
  --server "${MT5_DEMO_SERVER:-Deriv-Demo}" \
  --out-md docs/mt5-spike.md \
  --out-json mt5_spike_result.json

echo "MT5 Spike completed successfully."
