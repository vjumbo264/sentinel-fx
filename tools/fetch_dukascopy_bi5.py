#!/usr/bin/env python3
"""SENTINEL-FX: Dukascopy .bi5 raw-tick fetcher + M1 candle builder.

Bypasses the throttled `dukascopy-node` CLI (which fires hundreds of parallel
requests and gets HTTP 202/429/503) by downloading the raw hourly tick files
serially with a browser User-Agent and exponential backoff, then decoding the
LZMA-compressed 20-byte records and aggregating ticks into candles.

File layout (zero-based month in URL):
  https://datafeed.dukascopy.com/datafeed/<PAIR>/<YEAR>/<MM>/<DD>/<HH>h_ticks.bi5

Record format (big-endian, 20 bytes):
  >iiiii  -> ms_offset_in_hour, ask_i, bid_i, ask_vol(f32), bid_vol(f32)
Price scale: 100000 for FX majors, 1000 for JPY pairs.
"""
from __future__ import annotations

import argparse
import gzip
import io
import lzma
import struct
import sys
import time
from datetime import datetime, timezone, timedelta

import urllib.request

BASE = "https://datafeed.dukascopy.com/datafeed"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


def price_scale(instrument: str) -> int:
    return 1000 if instrument.lower().endswith("jpy") else 100000


def hour_urls(instrument: str, start: datetime, end: datetime):
    """Yield (epoch_hour, url) for every hour in [start, end)."""
    t = start.replace(minute=0, second=0, microsecond=0)
    while t < end:
        # zero-based month per Dukascopy convention
        url = f"{BASE}/{instrument.upper()}/{t.year}/{t.month - 1:02d}/{t.day:02d}/{t.hour:02d}h_ticks.bi5"
        yield int(t.timestamp()), url
        t += timedelta(hours=1)


def fetch_bi5(url: str, retries: int = 6, base_pause: float = 1.5):
    """Download + decompress one hourly bi5 file. Returns decompressed bytes or None."""
    pause = base_pause
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            raw = urllib.request.urlopen(req, timeout=20).read()
            if not raw:
                return b""  # empty hour (no ticks)
            try:
                return lzma.decompress(raw, format=lzma.FORMAT_ALONE)
            except lzma.LZMAError:
                return lzma.decompress(raw)  # some files carry a container header
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None  # hour legitimately absent (weekend / holiday)
            if e.code in (202, 429, 500, 502, 503):
                time.sleep(pause + (0.5 * attempt))
                pause = min(pause * 2, 30)
                continue
            raise
        except Exception:
            time.sleep(pause)
            pause = min(pause * 2, 30)
    return None


def decode_ticks(data: bytes, epoch_hour: int, scale: int):
    """Decode 20-byte records -> (epoch_ms, bid, ask)."""
    out = []
    n = len(data) - (len(data) % 20)
    for off in range(0, n, 20):
        ms, ask_i, bid_i, _av, _bv = struct.unpack(">iiiff", data[off:off + 20])
        ts = epoch_hour * 1000 + ms
        out.append((ts, bid_i / scale, ask_i / scale))
    return out


def aggregate_m1(ticks, scale: int):
    """Aggregate (epoch_ms, bid, ask) ticks into M1 candles keyed by epoch second."""
    candles = {}
    for ts, bid, ask in ticks:
        minute = ts // 60000  # epoch minute
        mid = round((bid + ask) / 2.0, 6)
        c = candles.get(minute)
        if c is None:
            candles[minute] = [mid, mid, mid, mid, 1]  # o h l c ticks
        else:
            if mid > c[1]:
                c[1] = mid
            if mid < c[2]:
                c[2] = mid
            c[3] = mid
            c[4] += 1
    return candles


def build_range(instrument: str, start: datetime, end: datetime, pause: float = 0.25):
    """Serial download of all hourly files in range; returns {epoch_sec: ohlc}."""
    scale = price_scale(instrument)
    all_candles = {}
    hours = list(hour_urls(instrument, start, end))
    total = len(hours)
    got = miss = err = 0
    for i, (epoch_hour, url) in enumerate(hours):
        data = fetch_bi5(url)
        if data is None:
            miss += 1
        elif data == b"":
            miss += 1
        else:
            got += 1
            ticks = decode_ticks(data, epoch_hour, scale)
            for minute, ohlc in aggregate_m1(ticks, scale).items():
                all_candles[minute * 60] = ohlc
        if pause:
            time.sleep(pause)
        if (i + 1) % 200 == 0:
            print(f"[bi5] {i+1}/{total} hours | ok={got} empty={miss} err={err} | candles={len(all_candles)}", flush=True)
    print(f"[bi5] DONE {total} hours | ok={got} empty={miss} | m1_candles={len(all_candles)}", flush=True)
    return all_candles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instrument", required=True)          # e.g. EURUSD
    ap.add_argument("--from", dest="date_from", required=True)  # YYYY-MM-DD
    ap.add_argument("--to", dest="date_to", required=True)      # YYYY-MM-DD
    ap.add_argument("--granularity", type=int, default=60)
    ap.add_argument("--out", required=True)                  # csv path (plain or .gz)
    ap.add_argument("--pause", type=float, default=0.25)
    a = ap.parse_args()

    start = datetime.strptime(a.date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(a.date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)

    candles = build_range(a.instrument, start, end, pause=a.pause)
    if not candles:
        print("ERROR: no candles decoded", file=sys.stderr)
        sys.exit(1)

    epochs = sorted(candles)
    opener = gzip.open if a.out.endswith(".gz") else open
    mode = "wt" if a.out.endswith(".gz") else "w"
    with opener(a.out, mode, newline="") as f:
        f.write("epoch,open,high,low,close,volume\n")
        for ep in epochs:
            o, h, l, c, n = candles[ep]
            f.write(f"{ep},{o},{h},{l},{c},{n}\n")
    print(f"[bi5] wrote {len(epochs)} candles -> {a.out} "
          f"({datetime.fromtimestamp(epochs[0],timezone.utc).date()} -> "
          f"{datetime.fromtimestamp(epochs[-1],timezone.utc).date()})", flush=True)


if __name__ == "__main__":
    main()
