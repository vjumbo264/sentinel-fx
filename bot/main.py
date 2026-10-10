"""SENTINEL-FX live bot.

Design (per spec):
- One ~3h50m run per Actions job; dispatches the next run ~5min before end;
  stops opening new trades ~2min before end.
- All state in D1 via the Worker. On start, reconciles any open contracts.
- Deriv auth: /trading/v1/options/accounts -> pick DOT (demo) or ROT (real) ->
  POST /otp -> open pre-authenticated WebSocket (no `authorize` call).
- Live payout re-check before every buy; break-even recomputed from the live
  payout; trade only if prob >= be + pack.margin.
- News fetched once per run; price reactions logged for past events.
- 15-minute CALL/PUT contracts; min stake 0.35; stake rounded to 2 dp.
- Shadow-mode pairs: compute signal, log virtual trade, settle later.
- Global kill switch overrides everything.
"""
from __future__ import annotations
import asyncio
import json
import os
import time
import urllib.request
import websockets
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from sentinel_engine import load_pack
from sentinel_engine.news import fetch_calendar, normalize, affected_pairs, pair_currencies, minutes_to_event

WORKER = os.environ["WORKER_URL"].rstrip("/")
BOT_SECRET = os.environ["BOT_SHARED_SECRET"]
DERIV_TOKEN = os.environ["DERIV_BEARER_TOKEN"]
DERIV_APP_ID = os.environ["DERIV_APP_ID"]
GH_PAT = os.environ.get("GH_CHAIN_PAT", "")
BOT_MODE_DEFAULT = os.environ.get("BOT_MODE", "demo")

WALL_S = int(os.environ.get("BOT_WALL_SECONDS", "13800"))
HANDOFF_LEAD_S = int(os.environ.get("BOT_HANDOFF_LEAD_S", "300"))
STOP_OPEN_LEAD_S = int(os.environ.get("BOT_STOP_OPEN_LEAD_S", "120"))

PUBLIC_WS = "wss://ws.derivws.com/websockets/v3?app_id=1089"
ACCOUNTS_URL = "https://api.derivws.com/trading/v1/options/accounts"
OWNER_TAG = f"actions-{int(time.time())}"


def http(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{WORKER}{path}", data=data, method=method,
        headers={"X-Bot-Secret": BOT_SECRET, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode() or "{}")


def log(level, pair, message, data=None):
    try:
        http("POST", "/api/bot/log", {"level": level, "pair": pair, "message": message, "data": data})
    except Exception as e:
        print(f"[log-fail] {e}: {level} {pair} {message}")


def heartbeat(mode, balance, note=""):
    try:
        http("POST", "/api/bot/heartbeat", {"mode": mode, "balance": balance, "note": note})
    except Exception:
        pass


def acquire_lock():
    r = http("POST", "/api/bot/lock", {"owner": OWNER_TAG})
    return bool(r.get("acquired"))


def release_lock():
    try:
        http("POST", "/api/bot/unlock", {"owner": OWNER_TAG})
    except Exception:
        pass


def deriv_rest(path, method="GET", body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"https://api.derivws.com{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {DERIV_TOKEN}", "Deriv-App-ID": DERIV_APP_ID,
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def pick_account(mode: str) -> str:
    accs = deriv_rest("/trading/v1/options/accounts")["data"]
    want = "demo" if mode == "demo" else "real"
    for a in accs:
        if a["account_type"] == want:
            return a["account_id"]
    raise RuntimeError(f"no {want} account on this Deriv token")


def otp_ws_url(loginid: str) -> str:
    r = deriv_rest(f"/trading/v1/options/accounts/{loginid}/otp", method="POST", body={})
    return r["data"]["url"]


async def ws_rpc(ws, payload, timeout=20):
    req_id = int(time.time() * 1000) & 0x7fffffff
    payload = dict(payload); payload["req_id"] = req_id
    await ws.send(json.dumps(payload))
    end = time.time() + timeout
    while time.time() < end:
        msg = await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - time.time()))
        d = json.loads(msg)
        if d.get("req_id") == req_id:
            return d
    raise asyncio.TimeoutError("ws rpc timeout")


async def fetch_candles(ws, symbol, count=600):
    r = await ws_rpc(ws, {"ticks_history": symbol, "style": "candles",
                          "granularity": 60, "count": count, "end": "latest"})
    cs = r.get("candles", [])
    return pd.DataFrame(cs) if cs else pd.DataFrame()


async def get_balance(ws):
    r = await ws_rpc(ws, {"balance": 1})
    return float(r.get("balance", {}).get("balance", 0.0))


async def propose_and_buy(ws, symbol, side, stake):
    prop = await ws_rpc(ws, {
        "proposal": 1, "amount": round(stake, 2), "basis": "stake",
        "contract_type": side, "currency": "USD", "duration": 15,
        "duration_unit": "m", "symbol": symbol})
    if "error" in prop:
        return {"error": prop["error"].get("message", "proposal error")}
    pid = prop["proposal"]["id"]
    payout = float(prop["proposal"]["payout"])
    buy = await ws_rpc(ws, {"buy": pid, "price": round(stake, 2)}, timeout=30)
    if "error" in buy:
        return {"error": buy["error"].get("message", "buy error")}
    return {"contract_id": str(buy["buy"]["contract_id"]), "payout": payout,
            "stake": round(stake, 2)}


def chain_next_run():
    """Self-chain: dispatch the next bot.yml run via the GitHub REST API."""
    if not GH_PAT:
        return
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/vjumbo264/sentinel-fx/actions/workflows/bot.yml/dispatches",
            data=json.dumps({"ref": "main", "inputs": {"mode": BOT_MODE_DEFAULT}}).encode(),
            method="POST",
            headers={"Authorization": f"token {GH_PAT}", "Accept": "application/vnd.github+json",
                     "User-Agent": "sentinel-fx-bot", "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20).read()
        log("info", None, "self-chain dispatched next run")
    except Exception as e:
        log("warn", None, f"self-chain failed: {e}")


def load_pack_for(symbol):
    path = os.path.join("pairs", symbol, "pack.json")
    if not os.path.exists(path):
        return None
    return load_pack(path)


async def main():
    t0 = time.time()
    deadline = t0 + WALL_S
    stop_open_at = deadline - STOP_OPEN_LEAD_S
    handoff_at = deadline - HANDOFF_LEAD_S
    chained = False

    # grab D1 lease
    if not acquire_lock():
        log("warn", None, "run_lock held by another runner; exiting")
        return

    state = http("GET", "/api/bot/state")
    settings = state.get("settings", {})
    mode = settings.get("mode", BOT_MODE_DEFAULT)
    if settings.get("kill", False):
        log("warn", None, "kill switch on; exiting")
        release_lock(); return

    loginid = pick_account(mode)
    log("info", None, f"deriv account picked: {loginid[:3]}***")
    ws_url = otp_ws_url(loginid)

    # News (once per run)
    try:
        events = normalize(fetch_calendar())
        symbols = [p["symbol"] for p in state.get("pairs", [])]
        for e in events:
            e["affected_pairs"] = affected_pairs(e["currency"], symbols)
        http("POST", "/api/bot/news", {"events": events})
        log("info", None, f"news upserted ({len(events)})")
    except Exception as e:
        events = []
        log("warn", None, f"news fetch failed: {e}")

    # Load pair packs
    packs = {}
    for p in state.get("pairs", []):
        pk = load_pack_for(p["symbol"])
        if pk is not None:
            packs[p["symbol"]] = (pk, p)
            log("info", p["symbol"], f"pack v{p['pack_version']} loaded")
        else:
            log("warn", p["symbol"], "no pack.json found; skipping")

    async with websockets.connect(ws_url, ping_interval=25) as ws:
        bal = await get_balance(ws)
        heartbeat(mode, bal, "ready")
        log("info", None, f"balance={bal} mode={mode}")

        # Reconcile open trades
        try:
            open_r = http("GET", "/api/bot/trades/open")
            for t in open_r.get("open", []):
                cid = t["contract_id"]
                st = await ws_rpc(ws, {"proposal_open_contract": 1, "contract_id": int(cid)})
                poc = st.get("proposal_open_contract", {})
                if poc.get("is_sold"):
                    pnl = float(poc.get("profit", 0.0))
                    result = "win" if pnl > 0 else "loss"
                    http("POST", "/api/bot/trade/settle",
                         {"contract_id": cid, "result": result, "pnl": pnl})
                    log("info", t["pair"], f"reconciled contract {cid}: {result} {pnl:+.2f}")
        except Exception as e:
            log("warn", None, f"reconcile failed: {e}")

        while time.time() < deadline:
            if time.time() >= handoff_at and not chained:
                chain_next_run(); chained = True

            # refresh runtime state
            try:
                state = http("GET", "/api/bot/state")
                settings = state.get("settings", {})
                if settings.get("kill"):
                    log("warn", None, "kill switch triggered; stopping")
                    break
                mode = settings.get("mode", mode)
            except Exception:
                pass

            bal = await get_balance(ws)
            heartbeat(mode, bal, "loop")

            for p in state.get("pairs", []):
                sym = p["symbol"]
                if not p.get("enabled") and not p.get("shadow_mode", 1):
                    continue
                if sym not in packs:
                    continue
                pack, prow = packs[sym]
                try:
                    df = await fetch_candles(ws, sym, count=500)
                    if df.empty or len(df) < 100:
                        continue
                    news_ctx = {}
                    nxt = minutes_to_event(events, datetime.now(timezone.utc), pair_currencies(sym))
                    if nxt is not None:
                        news_ctx["minutes_to_news"] = nxt
                    dec = pack.decide(df, news_ctx)
                    if not dec["allow"] or dec["side"] is None:
                        log("info", sym, "skipped: " + "; ".join(dec["reasons"]) or "rule-block",
                            {"prob": dec["prob"]})
                        continue
                    # payout check + break-even
                    stake_pct = float(p.get("stake_pct", 0.01))
                    raw_stake = max(0.35, min(float(p.get("max_stake", 10)), bal * stake_pct))
                    stake = round(raw_stake, 2)
                    if bal < 0.35 or stake < 0.35:
                        log("warn", sym, f"balance {bal:.2f} too low; pausing")
                        continue
                    # dry proposal to read live payout
                    prop_pre = await ws_rpc(ws, {"proposal": 1, "amount": stake, "basis": "stake",
                                                 "contract_type": dec["side"], "currency": "USD",
                                                 "duration": 15, "duration_unit": "m", "symbol": sym})
                    if "error" in prop_pre:
                        log("warn", sym, f"proposal error: {prop_pre['error'].get('message')}")
                        continue
                    live_payout_ratio = float(prop_pre["proposal"]["payout"]) / stake - 1.0
                    be = 1.0 / (1.0 + live_payout_ratio)
                    needed = be + float(dec.get("margin", 0))
                    if dec["edge"] < needed:
                        log("info", sym, f"skipped: edge {dec['edge']:.3f} < required {needed:.3f}",
                            {"live_payout": live_payout_ratio})
                        continue

                    if p.get("shadow_mode", 1) or not p.get("enabled"):
                        http("POST", "/api/bot/shadow", {
                            "pair": sym, "side": dec["side"], "stake": stake,
                            "entry_price": float(df["close"].iloc[-1]),
                            "model_prob": dec["prob"],
                            "reason": "; ".join(dec["reasons"]) or "ok"})
                        log("info", sym, f"shadow {dec['side']} @ {df['close'].iloc[-1]} prob={dec['prob']:.3f}")
                        continue
                    if time.time() >= stop_open_at:
                        log("info", sym, "near end-of-run; not opening")
                        continue

                    buy = await propose_and_buy(ws, sym, dec["side"], stake)
                    if "error" in buy:
                        log("warn", sym, f"buy failed: {buy['error']}")
                        continue
                    http("POST", "/api/bot/trade", {
                        "contract_id": buy["contract_id"], "pair": sym, "side": dec["side"],
                        "stake": buy["stake"], "payout": buy["payout"], "mode": mode,
                        "model_prob": dec["prob"],
                        "news_flag": news_ctx.get("news_state"),
                        "reason": "; ".join(dec["reasons"]) or "ok"})
                    log("info", sym, f"LIVE {dec['side']} stake={buy['stake']} contract={buy['contract_id']}")
                except Exception as e:
                    log("error", sym, f"loop exception: {e}")
            await asyncio.sleep(20)

    release_lock()
    heartbeat(mode, bal if 'bal' in locals() else None, "end-of-run")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        try: log("error", None, f"fatal: {e}")
        except Exception: pass
        raise
