#!/usr/bin/env python3
"""SENTINEL-FX candle data hub fetcher (DATA task).

Pulls OHLC history for one pair from Deriv's PUBLIC websocket
(wss://ws.derivws.com/websockets/v3?app_id=1089) — candle history is public and
identical with or without a token, so a missing token NEVER fails the job.
Paginates backwards (ticks_history style=candles, count 5000, end=oldest-1) at
~1.4 req/s, reconnects with backoff on drops, dedupes, sorts, asserts strictly
increasing epochs and flags non-weekend gaps.

Usage:
  python tools/fetch_candles.py --symbol frxEURUSD --granularity 60 \
      --mode full|incremental [--existing prev.csv.gz] --out out/

Output: <out>/<symbol>_<granularity>s.csv.gz  (epoch,open,high,low,close)
Prints a final line "STATS {json}" for the workflow to parse.
"""
from __future__ import annotations
import argparse
import asyncio
import csv
import gzip
import hashlib
import json
import sys
from datetime import datetime, timezone

PUBLIC_WS = "wss://ws.derivws.com/websockets/v3?app_id=1089"
MAX_PER_REQ = 5000


async def fetch_batch(symbol, gran, end, count):
    """One page of candles, reconnecting with backoff on any failure."""
    import websockets
    backoff = 1.0
    while True:
        try:
            async with websockets.connect(PUBLIC_WS, ping_interval=20,
                                          ping_timeout=20, close_timeout=10) as ws:
                await ws.send(json.dumps({
                    "ticks_history": symbol, "style": "candles",
                    "granularity": gran, "count": count, "end": end}))
                while True:
                    d = json.loads(await asyncio.wait_for(ws.recv(), 40))
                    if d.get("error"):
                        raise RuntimeError("deriv: " + str(
                            d["error"].get("message", "error")))
                    if d.get("candles") is not None:
                        return d["candles"]
        except Exception as e:
            print(f"[fetch] {type(e).__name__}: {e}; retry in {backoff:.0f}s",
                  flush=True)
            await asyncio.sleep(backoff)
            backoff = min(30.0, backoff * 2)


async def pull(symbol, gran, start_after=None):
    """Full backfill, or incremental (only epochs > start_after)."""
    rows, end, prev_oldest = [], "latest", None
    while True:
        cs = await fetch_batch(symbol, gran, end, MAX_PER_REQ)
        if not cs:
            break
        cs = sorted({int(c["epoch"]): c for c in cs}.values(),
                    key=lambda c: int(c["epoch"]))
        oldest, newest = int(cs[0]["epoch"]), int(cs[-1]["epoch"])
        if start_after is not None:
            keep = [c for c in cs if int(c["epoch"]) > start_after]
            rows = keep + rows
            if oldest <= start_after:
                break
        else:
            rows = cs + rows
        if prev_oldest is not None and oldest >= prev_oldest:
            break  # no further history
        prev_oldest = oldest
        end = str(oldest - 1)
        ts = datetime.fromtimestamp(oldest, timezone.utc).strftime("%Y-%m-%d")
        print(f"[fetch] page -> {ts} (total {len(rows)})", flush=True)
        await asyncio.sleep(0.7)  # ~1.4 req/s, well under Deriv limits
    return rows


def read_csv_gz(path):
    rows = {}
    with gzip.open(path, "rt") as f:
        for r in csv.DictReader(f):
            rows[int(r["epoch"])] = r
    return rows


def weekend_span(a, b):
    """True if the whole gap [a,b] lies inside the Fri 21:00 - Sun 21:00 UTC
    market close."""
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
    import os, re
    assert re.match(r"^frx[A-Z]{6}$", a.symbol), "bad symbol"
    os.makedirs(a.out, exist_ok=True)

    existing = {}
    start_after = None
    if a.mode == "incremental" and a.existing and os.path.exists(a.existing):
        existing = read_csv_gz(a.existing)
        if existing:
            start_after = max(existing) - 3600  # 1h overlap for safety
            print(f"[merge] existing {len(existing)} rows, refetch after "
                  f"{start_after}", flush=True)

    rows = asyncio.run(pull(a.symbol, a.granularity, start_after))
    for c in rows:
        ep = int(c["epoch"])
        existing[ep] = {"epoch": ep, "open": c["open"], "high": c["high"],
                        "low": c["low"], "close": c["close"]}
    epochs = sorted(existing)
    assert all(b > x for x, b in zip(epochs, epochs[1:])), "epochs not increasing"

    gaps = []
    for x, b in zip(epochs, epochs[1:]):
        if b - x > a.granularity * 5 and not weekend_span(x, b):
            gaps.append({"from": x, "to": b, "seconds": b - x})

    fname = f"{a.symbol}_{a.granularity}s.csv.gz"
    path = os.path.join(a.out, fname)
    h = hashlib.sha256()
    with open(path + ".tmp", "wb") as raw:
        with gzip.open(raw, "wt", newline="") as f:
            w = csv.writer(f)
            w.writerow(["epoch", "open", "high", "low", "close"])
            for ep in epochs:
                r = existing[ep]
                w.writerow([ep, r["open"], r["high"], r["low"], r["close"]])
    with open(path + ".tmp", "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    os.replace(path + ".tmp", path)  # never leave a half-written file

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
        "source": "public-ws",
        "last_checked_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "file": fname,
    }
    print("STATS " + json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
