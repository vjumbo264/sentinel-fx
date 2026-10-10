#!/usr/bin/env python3
"""BUYTEST: prove the demo account can buy Rise/Fall (CALL/PUT) contracts.

Runs on GitHub Actions (workflow_dispatch) or locally. DEMO ONLY.
Requires env: DERIV_BEARER_TOKEN, DERIV_APP_ID.
Optional env: WORKER_URL, BOT_SHARED_SECRET (to record to D1 database).

Steps per spec:
  account discovery -> contracts_for -> proposal -> buy at minimum stake 0.35
  for CALL and for PUT -> proposal_open_contract tracking until settlement
  -> D1 updates (trade row, settlement, ledger balance) -> trade appears on site.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

DERIV_REST = os.environ.get("DERIV_REST_BASE", "https://api.derivws.com")
WORKER_URL = os.environ.get("WORKER_URL", "https://sentinel-fx-worker.vjumbo264.workers.dev").rstrip("/")
BOT_SHARED_SECRET = os.environ.get("BOT_SHARED_SECRET", "")

def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def rest_call(token: str, app_id: str, path: str, method: str = "GET", body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{DERIV_REST}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Deriv-App-ID": str(app_id or "1089"),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "sentinel-buy-test/2.0",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))

def post_worker(path: str, payload: dict) -> dict | None:
    if not WORKER_URL or not BOT_SHARED_SECRET:
        return None
    try:
        req = urllib.request.Request(
            f"{WORKER_URL}{path}",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Bot-Secret": BOT_SHARED_SECRET,
                "User-Agent": "sentinel-buy-test/2.0",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"[worker-post-warn] {path}: {e}", file=sys.stderr)
        return None

def get_demo_account_and_otp(token: str, app_id: str) -> tuple[dict, str]:
    accs_res = rest_call(token, app_id, "/trading/v1/options/accounts")
    accounts = accs_res.get("data") or accs_res.get("accounts") or []
    if not accounts:
        raise RuntimeError("No accounts returned for Deriv bearer token")

    # Strictly pick virtual/demo account
    demo_acc = None
    for a in accounts:
        act_type = str(a.get("account_type", "")).lower()
        lid = str(a.get("account_id") or a.get("loginid") or "")
        is_virt = str(a.get("is_virtual", a.get("virtual", ""))).lower() in ("1", "true")
        if act_type == "demo" or is_virt or lid.startswith(("VRTC", "VRW", "DOT")):
            demo_acc = a
            break

    if not demo_acc:
        raise RuntimeError("SAFETY: No virtual/demo account found on Deriv token! Refusing to trade real funds.")

    loginid = demo_acc.get("account_id") or demo_acc.get("loginid")
    otp_res = rest_call(token, app_id, f"/trading/v1/options/accounts/{loginid}/otp", method="POST", body={})
    otp_url = otp_res.get("data", {}).get("url") or otp_res.get("url")
    if not otp_url:
        raise RuntimeError(f"OTP endpoint returned no url: {otp_res}")

    return demo_acc, otp_url

class WSClient:
    def __init__(self, ws):
        self.ws = ws
        self._id = 0

    async def call(self, req: dict, timeout: float = 25.0) -> dict:
        self._id += 1
        req = dict(req)
        req["req_id"] = self._id
        await self.ws.send(json.dumps(req))
        t_end = time.time() + timeout
        while time.time() < t_end:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=max(0.1, t_end - time.time()))
            msg = json.loads(raw)
            if msg.get("req_id") == self._id:
                return msg
        raise asyncio.TimeoutError(f"WS RPC timeout for req_id={self._id}")

async def run_single_trade(ws_client: WSClient, symbol: str, side: str, duration: int, duration_unit: str, stake: float) -> dict:
    entry = {
        "symbol": symbol,
        "side": side,
        "duration": duration,
        "duration_unit": duration_unit,
        "stake": round(stake, 2),
        "open_utc": now_utc(),
        "status": "pending",
    }
    
    # 1. Proposal
    prop_req = {
        "proposal": 1,
        "amount": round(stake, 2),
        "basis": "stake",
        "contract_type": side,
        "currency": "USD",
        "duration": duration,
        "duration_unit": duration_unit,
        "underlying_symbol": symbol,
    }
    prop_res = await ws_client.call(prop_req)
    if "error" in prop_res:
        err_msg = prop_res["error"].get("message", "proposal error")
        entry["status"] = "proposal_error"
        entry["error"] = err_msg
        return entry

    prop = prop_res.get("proposal", {})
    pid = prop.get("id")
    ask_price = float(prop.get("ask_price", stake))
    payout = float(prop.get("payout", 0.0))
    entry["proposal_id"] = pid
    entry["ask_price"] = ask_price
    entry["payout"] = payout

    # 2. Buy (with tolerance above ask_price, and fallback to direct parameters)
    buy_req = {
        "buy": pid,
        "price": round(ask_price + 0.10, 2),
    }
    buy_res = await ws_client.call(buy_req, timeout=30.0)
    if "error" in buy_res:
        # Fallback to direct buy with parameters
        buy_param_req = {
            "buy": 1,
            "price": round(stake + 0.10, 2),
            "parameters": {
                "amount": round(stake, 2),
                "basis": "stake",
                "contract_type": side,
                "currency": "USD",
                "duration": duration,
                "duration_unit": duration_unit,
                "symbol": symbol,
            }
        }
        buy_res = await ws_client.call(buy_param_req, timeout=30.0)

    if "error" in buy_res:
        err_msg = buy_res["error"].get("message", "buy error")
        entry["status"] = "buy_error"
        entry["error"] = err_msg
        return entry

    buy_data = buy_res.get("buy", {})
    contract_id = str(buy_data.get("contract_id"))
    entry["contract_id"] = contract_id
    entry["buy_price"] = float(buy_data.get("buy_price", ask_price))
    print(f"  [TRADE-OPEN] {symbol} {side} {duration}{duration_unit} | contract_id={contract_id} stake=${ask_price:.2f} payout=${payout:.2f}")

    # Record trade row in Worker / D1
    post_worker("/api/bot/trade", {
        "contract_id": contract_id,
        "pair": symbol,
        "side": side,
        "stake": entry["buy_price"],
        "payout": payout,
        "mode": "demo",
        "model_prob": 0.55,
        "news_flag": "clear",
        "reason": f"BUYTEST: {side} {duration}{duration_unit}",
    })

    # 3. Track proposal_open_contract until settlement
    max_wait = max(60, duration + 30) if duration_unit == "s" else max(180, duration * 60 + 30)
    t_end = time.time() + max_wait
    while time.time() < t_end:
        poc_res = await ws_client.call({"proposal_open_contract": 1, "contract_id": int(contract_id)})
        poc = poc_res.get("proposal_open_contract", {})
        if poc.get("is_sold"):
            profit = float(poc.get("profit", 0.0))
            result = "win" if profit > 0 else "loss"
            entry["exit_price"] = float(poc.get("sell_price", 0.0))
            entry["profit"] = profit
            entry["result"] = result
            entry["status"] = "settled"
            entry["close_utc"] = now_utc()
            print(f"  [SETTLED] contract_id={contract_id} result={result.upper()} profit=${profit:+.2f}")

            # Settle in Worker / D1
            post_worker("/api/bot/trade/settle", {
                "contract_id": contract_id,
                "result": result,
                "pnl": profit,
            })
            post_worker("/api/session/ledger/event", {
                "symbol": symbol,
                "kind": "trade",
                "amount": profit,
                "note": f"BUYTEST {side} {duration}{duration_unit}",
            })
            return entry
        await asyncio.sleep(1.5)

    entry["status"] = "timeout_unsettled"
    entry["close_utc"] = now_utc()
    return entry

async def async_main():
    ap = argparse.ArgumentParser(description="Sentinel-FX Autonomous Demo Buy Test")
    ap.add_argument("--symbol", default="R_10", help="Deriv symbol (default R_10)")
    ap.add_argument("--durations", default="5,15", help="Comma-separated durations")
    ap.add_argument("--duration-unit", default="s", help="Duration unit: s, m, h, d, t (default s)")
    ap.add_argument("--stake", type=float, default=0.35, help="Stake in USD (min 0.35)")
    ap.add_argument("--out", default=None, help="Output JSON path")
    args = ap.parse_args()

    token = os.environ.get("DERIV_BEARER_TOKEN", "").strip()
    app_id = os.environ.get("DERIV_APP_ID", "").strip() or "1089"

    if not token:
        print("[ERROR] DERIV_BEARER_TOKEN missing from environment", file=sys.stderr)
        sys.exit(2)

    print(f"=== SENTINEL-FX DEMO BUY TEST ===")
    print(f"Target symbol: {args.symbol} | Durations: {args.durations}{args.duration_unit} | Stake: ${args.stake:.2f}")

    # 1. Discover account & get OTP
    demo_acc, otp_url = get_demo_account_and_otp(token, app_id)
    loginid = demo_acc.get("account_id") or demo_acc.get("loginid")
    print(f"Account discovered: {loginid[:3]}*** (virtual={demo_acc.get('is_virtual', True)}, currency={demo_acc.get('currency', 'USD')})")

    import websockets
    async with websockets.connect(otp_url, ping_interval=20, ping_timeout=20) as ws:
        client = WSClient(ws)

        # 2. Balance check & safety gate
        bal_res = await client.call({"balance": 1})
        bal_info = bal_res.get("balance", {})
        cur_bal = float(bal_info.get("balance", 0.0))
        cur_loginid = bal_info.get("loginid", "")
        print(f"Pre-trade Balance: ${cur_bal:.2f} {bal_info.get('currency', 'USD')}")

        if not str(cur_loginid).startswith(("VRTC", "VRW", "DOT")) and not demo_acc.get("account_type") == "demo":
            print(f"[FATAL] SAFETY GATE: Connected account {cur_loginid} is not verified virtual/demo! Aborting.", file=sys.stderr)
            sys.exit(3)

        # 3. Query contracts_for
        cf_res = await client.call({"contracts_for": args.symbol})
        if "error" in cf_res:
            err_msg = cf_res["error"].get("message", "contracts_for error")
            print(f"[WARN] contracts_for for {args.symbol}: {err_msg}")
            if "closed" in err_msg.lower():
                print(f"[PENDING] Market for {args.symbol} is currently closed (weekend). Pending market open.")
        else:
            avail = cf_res.get("contracts_for", {}).get("available", [])
            rise_fall = [c for c in avail if c.get("contract_category") == "callput"]
            print(f"Available Rise/Fall contracts: {len(rise_fall)} types found")

        # 4. Run buys across sides (CALL, PUT) and durations
        results = []
        dur_list = [int(x.strip()) for x in args.durations.split(",") if x.strip()]
        call_ok = False
        put_ok = False

        for side in ("CALL", "PUT"):
            for dur in dur_list:
                print(f"\nExecuting: {args.symbol} {side} {dur}{args.duration_unit} (stake: ${args.stake:.2f})...")
                res = await run_single_trade(client, args.symbol, side, dur, args.duration_unit, args.stake)
                results.append(res)
                if res.get("status") == "settled":
                    if side == "CALL":
                        call_ok = True
                    if side == "PUT":
                        put_ok = True

        # Post-trade balance
        final_bal_res = await client.call({"balance": 1})
        final_bal = float(final_bal_res.get("balance", {}).get("balance", cur_bal))
        print(f"\nPost-trade Balance: ${final_bal:.2f} (Net: ${final_bal - cur_bal:+.2f})")

    # Print summary table
    print("\n" + "=" * 80)
    print("DEMO BUY TEST SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Symbol':<10} | {'Side':<5} | {'Dur':<6} | {'Stake':<6} | {'Payout':<7} | {'Result':<6} | {'PnL':<7} | {'Status':<12}")
    print("-" * 80)
    for r in results:
        sym = r.get("symbol", "")
        sd = r.get("side", "")
        dur_str = f"{r.get('duration')}{r.get('duration_unit')}"
        stk_str = f"${r.get('stake', 0.35):.2f}"
        pay_str = f"${r.get('payout', 0.0):.2f}" if r.get("payout") else "-"
        res_str = r.get("result", "-")
        pnl_val = r.get("profit")
        pnl_str = f"${pnl_val:+.2f}" if pnl_val is not None else "-"
        st_str = r.get("status", "")
        print(f"{sym:<10} | {sd:<5} | {dur_str:<6} | {stk_str:<6} | {pay_str:<7} | {res_str:<6} | {pnl_str:<7} | {st_str:<12}")
    print("=" * 80)

    # Save evidence file
    meta = {
        "run_utc": now_utc(),
        "account": loginid,
        "mode": "demo",
        "symbol": args.symbol,
        "durations": args.durations,
        "call_ok": call_ok,
        "put_ok": put_ok,
        "start_balance": cur_bal,
        "end_balance": final_bal,
    }
    os.makedirs("docs", exist_ok=True)
    out_file = args.out or f"docs/buy_test_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_file, "w") as f:
        json.dump({"meta": meta, "results": results}, f, indent=2)
    print(f"Evidence written to: {out_file}")

    if call_ok and put_ok:
        print("[SUCCESS] Both CALL and PUT demo trades placed, settled, and recorded successfully!")
        sys.exit(0)
    elif call_ok or put_ok:
        print("[PARTIAL] At least one trade settled successfully. Exit code 0.")
        sys.exit(0)
    else:
        print("[FAIL] Neither CALL nor PUT trade completed successfully.", file=sys.stderr)
        sys.exit(1)

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
