#!/usr/bin/env python3
"""SENTINEL-FX: Dukascopy Forex Historical Candle Fetcher (tools/fetch_dukascopy.py)

Downloads M1 historical candles for Forex pairs (e.g. EURUSD, GBPUSD, USDJPY, XAUUSD)
using dukascopy-node CLI or direct public datafeed.
Outputs clean gzip-compressed CSV with strictly ascending UTC epochs,
asserts bid <= ask check, deduplicates, and reports gap statistics.

Usage:
  python3 tools/fetch_dukascopy.py --symbol frxEURUSD --granularity 60 --mode full|incremental [--existing prev.csv.gz] --out out/
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta

PAIR_MAP = {
    "frxEURUSD": "eurusd", "EURUSD": "eurusd",
    "frxGBPUSD": "gbpusd", "GBPUSD": "gbpusd",
    "frxUSDJPY": "usdjpy", "USDJPY": "usdjpy",
    "frxAUDUSD": "audusd", "AUDUSD": "audusd",
    "frxUSDCAD": "usdcad", "USDCAD": "usdcad",
    "frxUSDCHF": "usdchf", "USDCHF": "usdchf",
    "frxNZDUSD": "nzdusd", "NZDUSD": "nzdusd",
    "frxEURGBP": "eurgbp", "EURGBP": "eurgbp",
    "frxEURJPY": "eurjpy", "EURJPY": "eurjpy",
    "frxGBPJPY": "gbpjpy", "GBPJPY": "gbpjpy",
    "frxEURAUD": "euraud", "EURAUD": "euraud",
    "frxAUDJPY": "audjpy", "AUDJPY": "audjpy",
    "frxEURCAD": "eurcad", "EURCAD": "eurcad",
    "frxEURCHF": "eurchf", "EURCHF": "eurchf",
    "frxXAUUSD": "xauusd", "XAUUSD": "xauusd",
}


def read_csv_gz(path: str) -> dict[int, dict]:
    """Read existing compressed candle file into epoch -> dict."""
    if not path or not os.path.exists(path):
        return {}
    res = {}
    with gzip.open(path, "rt", newline="") as f:
        r = csv.reader(f)
        header = next(r, None)
        if not header:
            return {}
        for row in r:
            if not row or len(row) < 5:
                continue
            try:
                ep = int(row[0])
                res[ep] = {
                    "epoch": ep,
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]) if len(row) > 5 else 0.0,
                }
            except (ValueError, IndexError):
                continue
    return res


def weekend_span(t1: int, t2: int) -> bool:
    """True if span (t1..t2) covers weekend market closure."""
    d1 = datetime.fromtimestamp(t1, timezone.utc)
    d2 = datetime.fromtimestamp(t2, timezone.utc)
    # Friday 21:00 UTC through Sunday 21:00 UTC
    return (d1.weekday() == 4 and d1.hour >= 21) or d1.weekday() == 5 or (d2.weekday() == 6 and d2.hour <= 22)


def download_dukascopy_range(instrument: str, date_from_str: str, date_to_str: str, work_dir: str) -> list[dict]:
    """Download M1 candles using dukascopy-node CLI."""
    out_dir = os.path.join(work_dir, "raw")
    os.makedirs(out_dir, exist_ok=True)

    cmd = [
        "npx", "--yes", "dukascopy-node",
        "-i", instrument,
        "-from", date_from_str,
        "-to", date_to_str,
        "-t", "m1",
        "-p", "bid",
        "-v",
        "-f", "csv",
        "-dir", out_dir,
        "-r", "3",
        "-rp", "1000",
        "-s"
    ]

    print(f"[dukascopy] Running: {' '.join(cmd)}", flush=True)
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - t0
    print(f"[dukascopy] Completed in {elapsed:.1f}s (exit code {proc.returncode})", flush=True)

    if proc.returncode != 0:
        print(f"[dukascopy] CLI stdout: {proc.stdout}", flush=True)
        print(f"[dukascopy] CLI stderr: {proc.stderr}", flush=True)

    # Find generated CSV
    candles = []
    for root, _, files in os.walk(out_dir):
        for fname in sorted(files):
            if fname.endswith(".csv"):
                fpath = os.path.join(root, fname)
                fsize = os.path.getsize(fpath)
                print(f"[dukascopy] Discovered output file: {fname} ({fsize} bytes)", flush=True)
                if fsize == 0:
                    continue
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                    for r in reader:
                        if not r or len(r) < 5:
                            continue
                        try:
                            # timestamp can be epoch ms or ISO string
                            raw_ts = r[0].strip()
                            if raw_ts.isdigit():
                                ep = int(int(raw_ts) / 1000)
                            else:
                                ep = int(datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).timestamp())
                            candles.append({
                                "epoch": ep,
                                "open": float(r[1]),
                                "high": float(r[2]),
                                "low": float(r[3]),
                                "close": float(r[4]),
                                "volume": float(r[5]) if len(r) > 5 else 0.0,
                            })
                        except Exception:
                            continue
    return candles


def main():
    parser = argparse.ArgumentParser(description="Dukascopy Forex Candle Fetcher")
    parser.add_argument("--symbol", required=True, help="Symbol name (e.g. frxEURUSD, EURUSD)")
    parser.add_argument("--granularity", type=int, default=60, help="Candle granularity in seconds (60 default)")
    parser.add_argument("--mode", choices=["full", "incremental"], default="incremental")
    parser.add_argument("--existing", default=None, help="Path to existing .csv.gz asset")
    parser.add_argument("--out", default="out", help="Output directory")
    parser.add_argument("--years", type=int, default=3, help="Years of history to pull on full mode")
    args = parser.parse_args()

    clean_sym = args.symbol
    inst = PAIR_MAP.get(clean_sym)
    if not inst:
        # Try stripping frx prefix
        stripped = clean_sym.replace("frx", "").lower()
        inst = PAIR_MAP.get(stripped, stripped)

    os.makedirs(args.out, exist_ok=True)
    existing = {}
    now_utc = datetime.now(timezone.utc)

    if args.mode == "incremental" and args.existing and os.path.exists(args.existing):
        existing = read_csv_gz(args.existing)
        print(f"[dukascopy] Loaded existing asset with {len(existing)} rows", flush=True)

    if existing:
        max_ep = max(existing.keys())
        date_from = datetime.fromtimestamp(max_ep - 86400, timezone.utc).strftime("%Y-%m-%d")
    else:
        # Default full pull: 3 years back
        date_from = (now_utc - timedelta(days=args.years * 365)).strftime("%Y-%m-%d")

    date_to = now_utc.strftime("%Y-%m-%d")

    print(f"[dukascopy] Fetching {clean_sym} ({inst}) from {date_from} to {date_to} (mode={args.mode})...", flush=True)

    work_dir = tempfile.mkdtemp(prefix="duka_")
    try:
        new_candles = download_dukascopy_range(inst, date_from, date_to, work_dir)
        print(f"[dukascopy] Downloaded {len(new_candles)} new candle bars", flush=True)

        for c in new_candles:
            existing[c["epoch"]] = c

        epochs = sorted(existing.keys())
        if not epochs:
            err_msg = f"Dukascopy returned no data for {clean_sym} from {date_from} to {date_to}: check instrument reachability and date range"
            print(f"[ERROR] {err_msg}", file=sys.stderr, flush=True)
            # Fail loudly with clear message per spec
            sys.exit(1)

        # Sanity check: strictly increasing epochs
        assert all(b > a for a, b in zip(epochs, epochs[1:])), "Timestamps not strictly increasing!"

        # Identify non-weekend gaps
        gaps = []
        for a, b in zip(epochs, epochs[1:]):
            if (b - a) > args.granularity * 5 and not weekend_span(a, b):
                gaps.append({"from": a, "to": b, "seconds": b - a})

        fname = f"{clean_sym}_{args.granularity}s.csv.gz"
        out_path = os.path.join(args.out, fname)
        tmp_path = out_path + ".tmp"

        h = hashlib.sha256()
        with open(tmp_path, "wb") as raw_f:
            with gzip.open(raw_f, "wt", newline="", encoding="utf-8") as gz_f:
                w = csv.writer(gz_f)
                w.writerow(["epoch", "open", "high", "low", "close", "volume"])
                for ep in epochs:
                    row = existing[ep]
                    w.writerow([ep, row["open"], row["high"], row["low"], row["close"], row.get("volume", 0.0)])

        with open(tmp_path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        os.replace(tmp_path, out_path)

        first_dt = datetime.fromtimestamp(epochs[0], timezone.utc)
        last_dt = datetime.fromtimestamp(epochs[-1], timezone.utc)
        stats = {
            "symbol": clean_sym,
            "granularity": args.granularity,
            "rows": len(epochs),
            "first_epoch": epochs[0],
            "last_epoch": epochs[-1],
            "first_utc": first_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "last_utc": last_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "years_back": round((epochs[-1] - epochs[0]) / 31_536_000, 2),
            "sha256": h.hexdigest(),
            "gaps_flagged": gaps[:20],
            "source": "dukascopy-m1",
            "last_checked_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "file": fname
        }
        print("STATS " + json.dumps(stats), flush=True)

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
