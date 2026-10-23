#!/usr/bin/env python3
"""SENTINEL-FX candle data hub fetcher (DATA task).
Pulls OHLC history for one pair from Deriv.
Uses authenticated OTP WebSocket if DERIV_BEARER_TOKEN and DERIV_APP_ID exist;
otherwise falls back to Deriv public WebSocket with browser headers.
Paginates backwards (ticks_history style=candles, count 5000, end=oldest-1) at
~1.4 req/s, reconnects with backoff on drops, dedupes, sorts, asserts strictly
increasing epochs and flags non-weekend gaps (synthetics trade 24/7 with no weekend gaps).

Usage:
  python tools/fetch_candles.py --symbol frxEURUSD --granularity 60 \
      --mode full|incremental [--existing prev.csv.gz] --out out/

Symbols: forex frxEURUSD-style OR synthetic indices (R_10..100, 1HZ10V..300V).
Prints a final line "STATS {json}" for the workflow to parse.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import subprocess
import asyncio
import csv
import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

DERIV_REST = os.environ.get("DERIV_REST_BASE", "https://api.derivws.com")
DERIV_TOKEN = os.environ.get("DERIV_BEARER_TOKEN", "")
DERIV_APP_ID = os.environ.get("DERIV_APP_ID", "")
PUBLIC_WS_PRIMARY = "wss://ws.derivws.com/websockets/v3?app_id=1089"
PUBLIC_WS_FALLBACK = "wss://ws.binaryws.com/websockets/v3?app_id=1089"

MAX_PER_REQ = 5000
DEADLINE_S = 1500  # hard cap: 25 minutes

def get_auth_otp_url():
    if not DERIV_TOKEN or not DERIV_APP_ID:
        return None
    try:
        req = urllib.request.Request(
            f"{DERIV_REST}/trading/v1/options/accounts",
            headers={
                "Authorization": f"Bearer {DERIV_TOKEN}",
                "Deriv-App-ID": DERIV_APP_ID,
                "Accept": "application/json",
                "User-Agent": "sentinel-fx-fetcher/2.0"
            }
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            accs = json.loads(r.read().decode()).get("data", [])
        if not accs:
            return None
        # pick demo or first available account
        acc = next((a for a in accs if a.get("account_type") == "demo"), accs[0])
        loginid = acc.get("account_id") or acc.get("loginid")
        req_otp = urllib.request.Request(
            f"{DERIV_REST}/trading/v1/options/accounts/{loginid}/otp",
            data=b"{}",
            method="POST",
            headers={
                "Authorization": f"Bearer {DERIV_TOKEN}",
                "Deriv-App-ID": DERIV_APP_ID,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "sentinel-fx-fetcher/2.0"
            }
        )
        with urllib.request.urlopen(req_otp, timeout=20) as r:
            res = json.loads(r.read().decode())
            return res.get("data", {}).get("url")
    except Exception as e:
        print(f"[fetch] Auth OTP request failed: {e}; falling back to public WS", flush=True)
        return None

async def connect_ws():
    import websockets
    # 1. Try OTP authenticated WS if credentials present
    otp_url = get_auth_otp_url()
    if otp_url:
        try:
            ws = await websockets.connect(
                otp_url, ping_interval=20, ping_timeout=20, close_timeout=10, max_queue=64
            )
            return ws, "auth-otp"
        except Exception as e:
            print(f"[fetch] OTP WS connection failed: {e}; trying public", flush=True)
    
    # 2. Try Public WS with browser-like headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Origin": "https://deriv.com"
    }
    for url in [PUBLIC_WS_PRIMARY, PUBLIC_WS_FALLBACK]:
        try:
            ws = await websockets.connect(
                url, extra_headers=headers, ping_interval=20, ping_timeout=20, close_timeout=10, max_queue=64
            )
            return ws, f"public-ws ({url})"
        except Exception as e:
            print(f"[fetch] {url} failed: {e}", flush=True)
    
    raise ConnectionError("Could not connect to Deriv via OTP or public WS")

async def pull(symbol, gran, start_after=None):
    import time as _t
    deadline = _t.time() + DEADLINE_S
    rows, end, prev_oldest = [], "latest", None
    ws = None
    source_used = "unknown"
    backoff = 2.0

    while True:
        if _t.time() > deadline:
            print("[fetch] deadline reached; writing what we have", flush=True)
            break
        
        # Ensure connected
        if ws is None:
            try:
                ws, source_used = await connect_ws()
                print(f"[fetch] Connected to Deriv via {source_used}", flush=True)
                backoff = 2.0
            except Exception as e:
                print(f"[fetch] Connection error: {e}; retry in {backoff:.0f}s", flush=True)
                await asyncio.sleep(backoff)
                backoff = min(30.0, backoff * 1.5)
                continue
        
        # Request batch
        try:
            await ws.send(json.dumps({
                "ticks_history": symbol,
                "style": "candles",
                "granularity": gran,
                "count": MAX_PER_REQ,
                "end": end,
                **({"start": int(start_after) + 1} if start_after is not None else {})
            }))
            raw = await asyncio.wait_for(ws.recv(), 35)
            d = json.loads(raw)
            if d.get("error"):
                raise RuntimeError("deriv error: " + str(d["error"].get("message", "unknown")))
            cs = d.get("candles")
            if not cs:
                # No more older candles
                print(f"[fetch] No older candles returned for {symbol}", flush=True)
                break
            
            cs = sorted({int(c["epoch"]): c for c in cs}.values(), key=lambda c: int(c["epoch"]))
            oldest, newest = int(cs[0]["epoch"]), int(cs[-1]["epoch"])

            if start_after is not None:
                keep = [c for c in cs if int(c["epoch"]) > start_after]
                rows = keep + rows
                if oldest <= start_after:
                    print(f"[fetch] Reached start_after boundary {start_after}", flush=True)
                    break
            else:
                rows = cs + rows

            if prev_oldest is not None and oldest >= prev_oldest:
                print(f"[fetch] Reached beginning of history at epoch {oldest}", flush=True)
                break
            
            prev_oldest = oldest
            end = str(oldest - 1)
            ts = datetime.fromtimestamp(oldest, timezone.utc).strftime("%Y-%m-%d")
            print(f"[fetch] page -> {ts} (total {len(rows)})", flush=True)
            await asyncio.sleep(0.7)  # safe rate limit
        except Exception as e:
            print(f"[fetch] Batch error: {e}; reconnecting in {backoff:.0f}s", flush=True)
            try:
                await ws.close()
            except Exception:
                pass
            ws = None
            await asyncio.sleep(backoff)
            backoff = min(30.0, backoff * 1.5)

    if ws is not None:
        try:
            await ws.close()
        except Exception:
            pass
    return rows, source_used

def read_csv_gz(path):
    rows = {}
    with gzip.open(path, "rt") as f:
        for r in csv.DictReader(f):
            rows[int(r["epoch"])] = r
    return rows

def weekend_span(a, b):
    da, db = (datetime.fromtimestamp(x, timezone.utc) for x in (a, b))
    def closed(d):
        return d.weekday() == 5 or (d.weekday() == 6 and d.hour < 21) or \
               (d.weekday() == 4 and d.hour >= 21)
    return closed(da) and closed(db)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--granularity", type=int, default=60)
    ap.add_argument("--mode", choices=["full", "incremental"], default="incremental")
    ap.add_argument("--existing", default=None)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    assert re.match(r"^(frx[A-Z]{6}|R_\d+|1HZ\d+V)$", a.symbol), \
        "bad symbol: expected frxXXXYYY, R_<n> or 1HZ<n>V"
    os.makedirs(a.out, exist_ok=True)

    # Daily refresh is incremental for Forex AND synthetics; bulk is HistData only.
    index = json.loads(Path("data/index.json").read_text()) if Path("data/index.json").exists() else {}
    last_epoch = int(index.get(a.symbol, {}).get('last_epoch', 0) or 0)
    existing = {}
    start_after = last_epoch or None
    if a.mode == "incremental" and a.existing and os.path.exists(a.existing):
        existing = read_csv_gz(a.existing)
        if existing:
            start_after = max(last_epoch, max(existing))  # strict incremental boundary
            print(f"[merge] existing {len(existing)} rows, refetch after {start_after}", flush=True)

    rows, source_used = asyncio.run(pull(a.symbol, a.granularity, start_after))

    for c in rows:
        ep = int(c["epoch"])
        if ep <= last_epoch:
            continue
        if a.symbol.startswith('frx'):
            registry = json.loads(Path('data/symbols.json').read_text())['symbols']
            specs = registry[a.symbol[3:]]
            spread = float(specs.get('spread', specs.get('typical_spread_pts', 1.5))) * specs['point']
            item = {'epoch': ep}
            for field in ('open','high','low','close'):
                item['bid_'+field] = float(c[field])
                item['ask_'+field] = float(c[field]) + spread
            if 'tick_volume' in index.get(a.symbol, {}).get('columns', []):
                item['tick_volume'] = 0  # Deriv candles do not supply tick volume.
            existing[ep] = item
        else:
            existing[ep] = {"epoch": ep, "open": c["open"], "high": c["high"],
                            "low": c["low"], "close": c["close"]}

    epochs = sorted(existing)
    if not epochs:
        err_msg = f"Deriv returned no data for synthetic index {a.symbol} (source: {source_used})"
        print(f"[ERROR] {err_msg}", file=sys.stderr, flush=True)
        stats = {
            "symbol": a.symbol, "granularity": a.granularity, "rows": 0,
            "first_epoch": None, "last_epoch": None,
            "first_utc": None, "last_utc": None,
            "years_back": 0, "sha256": "", "gaps_flagged": [],
            "source": source_used,
            "last_checked_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "file": f"{a.symbol}_{a.granularity}s.csv.gz"
        }
        print("STATS " + json.dumps(stats), flush=True)
        sys.exit(1)

    assert all(b > x for x, b in zip(epochs, epochs[1:])), "epochs not increasing"
    is_fx = a.symbol.startswith("frx")
    gaps = []
    for x, b in zip(epochs, epochs[1:]):
        if b - x > a.granularity * 5 and (not is_fx or not weekend_span(x, b)):
            gaps.append({"from": x, "to": b, "seconds": b - x})

    fname = f"{a.symbol}_{a.granularity}s.csv.gz"
    path = os.path.join(a.out, fname)
    h = hashlib.sha256()
    with open(path + ".tmp", "wb") as raw:
        with gzip.open(raw, "wt", newline="") as f:
            w = csv.writer(f)
            columns = list(existing[epochs[0]])
            w.writerow(columns)
            for ep in epochs:
                r = existing[ep]
                w.writerow([r[key] for key in columns])

    with open(path + ".tmp", "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    os.replace(path + ".tmp", path)

    first = datetime.fromtimestamp(epochs[0], timezone.utc) if epochs else None
    last = datetime.fromtimestamp(epochs[-1], timezone.utc) if epochs else None
    stats = {
        "symbol": a.symbol, "granularity": a.granularity, "rows": len(epochs),
        "first_epoch": epochs[0] if epochs else None,
        "last_epoch": epochs[-1] if epochs else None,
        "first_utc": first.strftime("%Y-%m-%dT%H:%M:%SZ") if first else None,
        "last_utc": last.strftime("%Y-%m-%dT%H:%M:%SZ") if last else None,
        "years_back": round((epochs[-1] - epochs[0]) / 31_536_000, 2) if epochs else 0,
        "sha256": h.hexdigest(), "gaps_flagged": gaps[:20],
        "source": source_used,
        "last_checked_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "file": fname,
    }
    print("STATS " + json.dumps(stats), flush=True)

if __name__ == "__main__":
    main()
