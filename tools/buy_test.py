#!/usr/bin/env python3
"""BUYTEST: prove the demo account can buy Rise/Fall (CALL/PUT) contracts.

Runs on GitHub Actions (workflow_dispatch) or locally. DEMO ONLY.
Requires env: DERIV_BEARER_TOKEN, DERIV_APP_ID.
Writes a JSON evidence file to docs/ (path from --out).

For each symbol x side (CALL, PUT) x duration in --durations:
  authorize (OTP via bearer) -> buy 1 USD stake -> poll portfolio/proposal_open_contract
  until settled -> record contract_id, side, duration, buy_price, pnl, result.
Exit code 0 if at least one CALL and one PUT buy succeeded.
"""
import argparse, json, os, sys, time, urllib.request
from datetime import datetime, timezone

WS = "wss://ws.derivws.com/websockets/v3?app_id={app_id}"
REST = "https://api.derivws.com"

def _rest(bearer, path, method="GET", data=None):
    req = urllib.request.Request(REST + path, data=data, method=method, headers={
        "Authorization": f"Bearer {bearer}", "Accept": "application/json",
        "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def get_otp(bearer):
    """Mirror tools/fetch_candles.py proven auth flow: list accounts -> POST per-loginid OTP."""
    accs = _rest(bearer, "/trading/v1/options/accounts")
    accounts = accs.get("accounts") or accs.get("data", {}).get("accounts") or []
    # Prefer the virtual (demo) account.
    loginid = None
    for a in accounts:
        lid = a.get("loginid") or a.get("id") or ""
        if str(a.get("is_virtual", a.get("virtual", ""))).lower() in ("1", "true") or str(lid).startswith(("VRTC", "VRW")):
            loginid = lid; break
    if not loginid and accounts:
        loginid = accounts[0].get("loginid") or accounts[0].get("id")
    if not loginid:
        raise RuntimeError("no Deriv account found for bearer token")
    d = _rest(bearer, f"/trading/v1/options/accounts/{loginid}/otp", method="POST", data=b"{}")
    otp = d.get("otp") or d.get("data", {}).get("otp") or d.get("token")
    if not otp:
        raise RuntimeError(f"OTP response had no token: {list(d.keys())}")
    return otp, loginid

class WSClient:
    def __init__(self, url):
        import websocket  # websocket-client
        self.ws = websocket.create_connection(url, timeout=30)
        self._id = 0
    def call(self, **req):
        self._id += 1
        req["req_id"] = self._id
        self.ws.send(json.dumps(req))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("req_id") == self._id:
                if "error" in m:
                    raise RuntimeError(m["error"].get("message", "api error"))
                return m
    def close(self):
        try: self.ws.close()
        except Exception: pass

def run_one(ws, symbol, side, dur_s, stake):
    """Buy one contract, wait for settlement. Returns evidence dict."""
    buy = ws.call(buy=1, price=stake, parameters={
        "amount": stake, "basis": "stake", "contract_type": side,
        "currency": "USD", "duration": dur_s, "duration_unit": "s",
        "symbol": symbol})
    cid = buy["buy"]["contract_id"]
    entry = {"contract_id": cid, "symbol": symbol, "side": side,
             "duration_s": dur_s, "buy_price": buy["buy"]["buy_price"],
             "open_utc": now()}
    deadline = time.time() + dur_s + 60
    while time.time() < deadline:
        try:
            poc = ws.call(proposal_open_contract=1, contract_id=cid)
            c = poc["proposal_open_contract"]
            if c.get("is_sold"):
                entry.update(exit_price=c.get("sell_price"),
                             profit=c.get("profit"),
                             result="win" if (c.get("profit") or 0) > 0 else "loss",
                             close_utc=now())
                return entry
        except Exception:
            pass
        time.sleep(2)
    entry.update(result="timeout_unsettled", close_utc=now())
    return entry

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="R_10")
    ap.add_argument("--durations", default="5,15,60",
                    help="comma list of seconds (synthetics allow >=5s)")
    ap.add_argument("--stake", type=float, default=1.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    bearer = os.environ.get("DERIV_BEARER_TOKEN")
    app_id = os.environ.get("DERIV_APP_ID", "1089")
    if not bearer:
        print("DERIV_BEARER_TOKEN missing", file=sys.stderr); sys.exit(2)

    otp, loginid = get_otp(bearer)
    ws = WSClient(WS.format(app_id=app_id))
    auth = ws.call(authorize=otp)
    acct = auth["authorize"]
    print(f"authorized: {acct.get('loginid')} virtual={acct.get('is_virtual')} "
          f"balance={acct.get('balance')} {acct.get('currency')}")
    if not acct.get("is_virtual"):
        print("SAFETY: not a demo account - aborting", file=sys.stderr); sys.exit(3)

    results, meta = [], {"run_utc": now(), "account": acct.get("loginid"),
                         "mode": "demo", "symbol": args.symbol}
    ok_call = ok_put = False
    for side in ("CALL", "PUT"):
        for d in [int(x) for x in args.durations.split(",")]:
            try:
                r = run_one(ws, args.symbol, side, d, args.stake)
                print(json.dumps(r))
                if r.get("result") in ("win", "loss"):
                    ok_call = ok_call or side == "CALL"
                    ok_put = ok_put or side == "PUT"
                results.append(r)
            except Exception as e:
                print(f"FAIL {side} {d}s: {e}", file=sys.stderr)
                results.append({"symbol": args.symbol, "side": side, "duration_s": d,
                                "error": str(e), "close_utc": now()})
    ws.close()
    meta["call_ok"], meta["put_ok"] = ok_call, ok_put
    out = args.out or f"docs/buy_test_{now().replace(':','').replace('-','')}.json"
    with open(out, "w") as f:
        json.dump({"meta": meta, "results": results}, f, indent=1)
    print("evidence ->", out)
    sys.exit(0 if (ok_call and ok_put) else 1)

if __name__ == "__main__":
    main()
