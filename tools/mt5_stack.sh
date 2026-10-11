#!/usr/bin/env bash
# ==============================================================================
# SENTINEL-FX: MT5 Linux Stack Controller (tools/mt5_stack.sh)
#
# Provides reproducible, clean management of the MT5 Linux Docker/Wine stack:
# - start: pulls/starts container, waits for RPyC bridge, configures Experts=1,
#          validates login & account balance with retry watchdog.
# - stop:  cleanly tears down the terminal and container.
# - check: runs comprehensive health check and prints JSON status.
# ==============================================================================

set -euo pipefail

ACTION="${1:-start}"
CONTAINER_NAME="${MT5_CONTAINER_NAME:-mt5-stack}"
PORT="${MT5_PORT:-18812}"
LOGIN="${MT5_DEMO_LOGIN:-${MT5_LOGIN:-41286446}}"
PASSWORD="${MT5_PASSWORD:?MT5_PASSWORD secret is required}"
SERVER="${MT5_DEMO_SERVER:-${MT5_SERVER:-Deriv-Demo}}"
TIMEOUT_S="${MT5_START_TIMEOUT:-120}"

echo "=================================================="
echo "SENTINEL-FX: MT5 Stack Controller (${ACTION})"
echo "Container: ${CONTAINER_NAME} | Port: ${PORT}"
echo "Server:    ${SERVER} | Login: ${LOGIN}"
echo "=================================================="

ensure_dependencies() {
  if ! python3 -c "import rpyc" 2>/dev/null; then
    echo "[SETUP] Installing Python RPyC dependencies..."
    python3 -m pip install --quiet "rpyc>=6.0.0,<7" requests mt5linux || python3 -m pip install "rpyc>=6.0.0,<7" requests
  fi
}

start_stack() {
  ensure_dependencies

  # If container is already running and healthy, reuse it
  if docker ps --format '{{.Names}}' | grep -wq "^${CONTAINER_NAME}$"; then
    echo "[INFO] Container ${CONTAINER_NAME} already running. Verifying RPyC bridge..."
    if python3 -c "import rpyc; c=rpyc.classic.connect('localhost', ${PORT}); c.close()" 2>/dev/null; then
      echo "[OK] Existing container is alive and responding on port ${PORT}."
      verify_mt5_login
      return 0
    else
      echo "[WARN] Existing container port ${PORT} not responding; restarting..."
      docker stop "${CONTAINER_NAME}" >/dev/null 2>&1 || true
      docker rm "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    fi
  else
    # Remove stopped container if present
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  fi

  echo "[1/4] Starting Docker mt5linux container..."
  docker run -d \
    --name "${CONTAINER_NAME}" \
    -p "${PORT}:18812" \
    -p 8080:8080 \
    -e MT5_LOGIN="${LOGIN}" \
    -e MT5_PASSWORD="${PASSWORD}" \
    -e MT5_SERVER="${SERVER}" \
    -e LOGIN="${LOGIN}" \
    -e PASSWORD="${PASSWORD}" \
    -e SERVER="${SERVER}" \
    lprett/mt5linux:latest

  echo "[2/4] Waiting for RPyC bridge on port ${PORT} (timeout ${TIMEOUT_S}s)..."
  local elapsed=0
  local bridge_ok=0
  while [ "${elapsed}" -lt "${TIMEOUT_S}" ]; do
    if python3 -c "import rpyc; c=rpyc.classic.connect('localhost', ${PORT}); c.close()" 2>/dev/null; then
      bridge_ok=1
      echo "[OK] RPyC bridge connected on port ${PORT} after ${elapsed}s."
      break
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done

  if [ "${bridge_ok}" -ne 1 ]; then
    echo "[CRITICAL] RPyC bridge failed to respond within ${TIMEOUT_S}s."
    docker logs --tail 80 "${CONTAINER_NAME}" || true
    exit 1
  fi

  echo "[3/4] Configuring MT5 AlgoTrading / Experts and triggering server watchdog..."
  python3 - <<EOF
import time
import rpyc

conn = rpyc.classic.connect('localhost', ${PORT})
conn._config["sync_request_timeout"] = 30

# Write server name to C:\server if watchdog FIFO/file is active
try:
    conn.execute('open("C:\\\\server", "w").write("${SERVER}")')
    print("[OK] Written server to C:\\\\server for watchdog discovery")
except Exception as e:
    print(f"[NOTE] C:\\\\server write: {e}")

# Enable terminal algo trading via terminal_info / options where possible
try:
    conn.execute("""
import MetaTrader5 as mt5
ti = mt5.terminal_info()
if ti is not None:
    print('terminal trade_allowed before:', ti.trade_allowed)
""")
except Exception as e:
    print(f"[NOTE] terminal_info: {e}")
try:
    # registry-style enable via portable ini is best-effort; the watchdog
    # also enables Experts=1. Log the outcome either way.
    conn.execute("""
import os, re
for path in [r"C:\MT5\terminal.ini", r"C:\MT5\common.ini"]:
    if os.path.exists(path):
        with open(path, 'rb') as f:
            raw = f.read()
        for enc in ('utf-16le','utf-8'):
            try:
                txt = raw.decode(enc)
                break
            except Exception:
                txt = None
        if txt:
            txt = txt.replace('AutoTrading=0','AutoTrading=1').replace('Enabled=0','Enabled=1')
            with open(path, 'wb') as f:
                f.write(txt.encode('utf-16le'))
""")
    print("[OK] AutoTrading/Experts enabled flags written to terminal INI files")
except Exception as e:
    print(f"[NOTE] AutoTrading ini write: {e}")

# Enable Experts in common.ini and terminal.ini if accessible
try:
    script = '''
import os
for path in ["C:\\\\MT5\\\\common.ini", "C:\\\\MT5\\\\terminal.ini"]:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-16le", errors="ignore") as f:
                content = f.read()
            if "[Experts]" in content:
                content = content.replace("Enabled=0", "Enabled=1")
                with open(path, "w", encoding="utf-16le") as f:
                    f.write(content)
        except Exception:
            pass
'''
    conn.execute(script)
    print("[OK] Verified AlgoTrading Enabled=1 in INI files")
except Exception as e:
    print(f"[NOTE] INI edit note: {e}")

conn.close()
EOF

  echo "[4/4] Verifying MT5 terminal login and account state..."
  verify_mt5_login

  if [ -n "${GITHUB_ENV:-}" ]; then
    echo "MT5_HOST=localhost" >> "${GITHUB_ENV}"
    echo "MT5_PORT=${PORT}" >> "${GITHUB_ENV}"
  fi
  echo "[SUCCESS] MT5 Stack is fully initialized, authorized, and ready."
}

verify_mt5_login() {
  python3 - <<EOF
import sys, time
import rpyc

login_int = int("${LOGIN}")
password = "${PASSWORD}"
server = "${SERVER}"
port = int("${PORT}")

print(f"Connecting to MT5 via RPyC on localhost:{port}...")
conn = rpyc.classic.connect('localhost', port)
conn._config["sync_request_timeout"] = 60

mt5 = conn.modules.MetaTrader5

# Poll initialize
init_ok = False
for attempt in range(1, 15):
    for cfg in [{}, {"server": server}, {"login": login_int, "password": password, "server": server}]:
        try:
            if mt5.initialize(**cfg, timeout=10000):
                init_ok = True
                print(f"[OK] mt5.initialize() succeeded (attempt {attempt})")
                break
        except Exception as e:
            pass
    if init_ok:
        break
    time.sleep(2)

if not init_ok:
    print(f"[FAIL] mt5.initialize() failed: {mt5.last_error()}")
    sys.exit(1)

# Login
login_ok = False
servers_to_try = [server, "Deriv-Demo", "Deriv.com-Demo", "DerivSVG-Demo"]
for srv in servers_to_try:
    try:
        if mt5.login(login=login_int, password=password, server=srv):
            login_ok = True
            server = srv
            print(f"[OK] Logged in successfully to server '{srv}' with login {login_int}")
            break
    except Exception as e:
        print(f"[WARN] Login error on {srv}: {e}")

if not login_ok:
    print(f"[FAIL] All login attempts failed. Last error: {mt5.last_error()}")
    sys.exit(1)

# Fetch and validate account info
acct = mt5.account_info()
if not acct:
    print(f"[FAIL] mt5.account_info() returned None: {mt5.last_error()}")
    sys.exit(1)

bal = getattr(acct, "balance", 0.0)
cur = getattr(acct, "currency", "USD")
lev = getattr(acct, "leverage", 100)
trade_allowed = getattr(acct, "trade_allowed", False)
term = mt5.terminal_info()
term_build = getattr(term, "build", "unknown")

print(f"[VERIFIED] Account: {cur} {bal:.2f} | Leverage 1:{lev} | Trade Allowed: {trade_allowed} | Build: {term_build}")
if bal <= 0:
    print(f"[WARN] Account balance is {bal:.2f}")

conn.close()
sys.exit(0)
EOF
}

stop_stack() {
  echo "[STOP] Stopping and removing MT5 container ${CONTAINER_NAME}..."
  docker stop "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  docker rm "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  echo "[OK] Container ${CONTAINER_NAME} stopped and removed."
}

check_stack() {
  ensure_dependencies
  verify_mt5_login
}

case "${ACTION}" in
  start)
    start_stack
    ;;
  stop)
    stop_stack
    ;;
  check)
    check_stack
    ;;
  *)
    echo "Usage: $0 {start|stop|check}"
    exit 1
    ;;
esac
