#!/usr/bin/env python3
"""
Test MT5 account login script for Fix Mission 5 (H4).
Connects to MetaTrader 5 in demo or real (read-only) mode,
reports account balance, equity, and broker status to Worker,
or reports broker error. Never executes any orders.
Never logs or prints the password.
"""
import sys
import os
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def report_to_worker(result):
    worker_url = os.environ.get("WORKER_URL", "https://sentinel-fx-worker.vjumbo264.workers.dev")
    token = os.environ.get("GH_CHAIN_PAT") or os.environ.get("GITHUB_TOKEN") or ""
    req = urllib.request.Request(
        f"{worker_url}/api/settings/test-login-result",
        data=json.dumps(result).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "X-Bot-Secret": os.environ.get("BOT_SHARED_SECRET", ""),
            "User-Agent": "sentinel-mt5-login/1.0"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print("Reported test login result to Worker:", r.status)
    except Exception as e:
        print("Notice: could not report to Worker:", e)

def main():
    mode = os.environ.get("LOGIN_MODE", "demo").lower()
    print(f"=== TESTING MT5 LOGIN (MODE: {mode.upper()}) ===")
    
    # Import MT5Broker
    from bot.mt5_broker import MT5Broker
    broker = MT5Broker()
    
    now_utc = datetime.now(timezone.utc).isoformat()
    try:
        connected = broker.connect(mode)
        if not connected:
            last_err = "Broker authentication failed"
            try:
                api = broker._get_api()
                if api and hasattr(api, "last_error"):
                    last_err = str(api.last_error())
            except Exception:
                pass
            res = {
                "ok": False,
                "mode": mode,
                "error": f"Login failed: {last_err}",
                "timestamp_utc": now_utc
            }
            print("[FAIL]", res["error"])
            report_to_worker(res)
            sys.exit(1)
            
        probes = {}
        api = broker._get_api()
        if mode != 'demo' or int(api.account_info().trade_mode) != 0:
            raise RuntimeError('Demo account required; no real-account probe permitted')
        if os.environ.get('PROBE_WRONG_PASSWORD', '').lower() == 'true':
            import secrets
            invalid = 'invalid-probe-' + secrets.token_hex(16)
            wrong_ok = api.login(login=int(broker.demo_login), password=invalid, server=broker.demo_server, timeout=15000)
            error = tuple(api.last_error())
            restored = api.login(login=int(broker.demo_login), password=broker.password, server=broker.demo_server, timeout=60000)
            if wrong_ok or not restored:
                raise RuntimeError('Wrong-password rejection or correct-login restoration failed')
            probes['wrong_password'] = {'ok': False, 'rejected': True, 'error': str(error)}
            print('[PASS] Wrong password rejected by broker:', error)
            print('[PASS] Correct stored credentials restored')
        # Connected successfully! Retrieve read-only account details
        acct = broker.account_info()
        login_masked = str(acct.get("login", ""))
        if len(login_masked) > 3:
            login_masked = login_masked[:3] + "***"
            
        res = {
            "ok": True,
            "mode": mode,
            "account_type": acct.get("mode", mode),
            "balance": float(acct.get("balance", 0.0)),
            "equity": float(acct.get("equity", 0.0)),
            "currency": acct.get("currency", "USD"),
            "login": login_masked,
            "server": acct.get("server", broker.demo_server if mode == "demo" else broker.real_server),
            "timestamp_utc": now_utc,
            "probes": probes
        }
        print(f"[PASS] MT5 Login Successful: Type={res['account_type']}, Server={res['server']}, Balance={res['balance']} {res['currency']}")
        report_to_worker(res)
        
    except Exception as exc:
        err_msg = str(exc)
        res = {
            "ok": False,
            "mode": mode,
            "error": f"Connection exception: {err_msg}",
            "timestamp_utc": now_utc
        }
        print("[FAIL] Exception during MT5 login test:", err_msg)
        report_to_worker(res)
        sys.exit(1)
    finally:
        try:
            broker.disconnect()
        except Exception:
            pass

if __name__ == "__main__":
    main()
