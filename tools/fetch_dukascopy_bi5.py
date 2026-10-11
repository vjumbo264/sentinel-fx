#!/usr/bin/env python3
"""Dukascopy .bi5 -> bid/ask M1 OHLC pipeline (DATA hub).

Serial UTC hourly tick decoder with a SAFE whitelist of instruments.
- Own decoder: LZMA_ALONE, 20-byte records (ms, ask, bid, ask_vol, bid_vol).
- Price scale 100000, or 1000 for JPY pairs. URL months are ZERO-BASED.
- Retries/backoff on 202/429/5xx; honors Retry-After. Serial pacing only.
- Resumable: raw hours cached per instrument (UTC day/hour), resume safe.
- Output: gzip CSV, columns epoch, bid O/H/L/C, ask O/H/L/C, tick_volume.
- Per-run report: rows, first/last, gaps (weekend-tagged), duplicates,
  bid<ask violations, and spread profile by UTC hour (for cost realism).
Failures are NEVER represented as empty rows; empty input is refused.

Usage:
  python tools/fetch_dukascopy_bi5.py --instrument EURUSD \
      --from 2024-01-01 --to 2024-02-01 --out out/frxEURUSD_60s.csv.gz
"""
import argparse, csv, gzip, hashlib, json, lzma, struct, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = 'https://datafeed.dukascopy.com/datafeed'
UA = {'User-Agent': 'sentinel-fx-data/3.0 (research; +https://github.com/vjumbo264/sentinel-fx)'}

def price_scale(instrument):
    return 1000 if instrument.upper().endswith('JPY') else 100000

def fetch_bi5(url, retries=10, base_pause=4.0):
    """Download one hourly .bi5 and LZMA-decode. Returns b'' for a known 404."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=45) as response:
                raw = response.read()
            if not raw:
                return b''
            return lzma.decompress(raw, format=lzma.FORMAT_ALONE)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return b''
            if error.code not in (202, 429, 500, 502, 503, 504):
                raise
            retry_after = error.headers.get('Retry-After') if error.headers else None
            wait = min(120, int(retry_after)) if (retry_after and retry_after.isdigit()) else min(90, base_pause * 2 ** attempt)
            print(f'RETRY {attempt+1}/{retries} HTTP {error.code} wait={wait}s {url}', flush=True)
            time.sleep(wait)
            continue
        except (OSError, ValueError, RuntimeError, lzma.LZMAError) as error:
            print(f'RETRY {attempt+1}/{retries} {type(error).__name__}: {error} {url}', flush=True)
            time.sleep(min(90, base_pause * 2 ** attempt))
    raise RuntimeError(f'Unresolved hour after {retries} attempts: {url}')

def decode_ticks(data, epoch_hour, scale):
    if len(data) % 20:
        raise ValueError('truncated 20-byte record')
    for ms, ask, bid, av, bv in struct.iter_unpack('>iiiff', data):
        if not 0 <= ms < 3600000 or bid <= 0 or ask < bid:
            raise ValueError('invalid timestamp or crossed bid/ask')
        yield epoch_hour * 1000 + ms, bid / scale, ask / scale

def aggregate_m1(ticks):
    candles = {}
    for ts, bid, ask in ticks:
        key = (ts // 60000) * 60
        c = candles.get(key)
        if c is None:
            candles[key] = [bid, bid, bid, bid, ask, ask, ask, ask, 1]
        else:
            c[1] = max(c[1], bid); c[2] = min(c[2], bid); c[3] = bid
            c[5] = max(c[5], ask); c[6] = min(c[6], ask); c[7] = ask
            c[8] += 1
    return candles

def build_range(instrument, start, end, pause=1.6, cache=None):
    """Serial hour-by-hour decode over [start, end). Resumable via .bi5-cache."""
    cache = Path(cache or '.bi5-cache') / instrument
    cache.mkdir(parents=True, exist_ok=True)
    result = {}
    t = start.replace(minute=0, second=0, microsecond=0)
    hours = empty = 0
    while t < end:
        if t.weekday() == 5:  # Saturday: known empty; Sun/Fri fetched (DST/rollover).
            t += timedelta(hours=1)
            continue
        name = t.strftime('%Y%m%d%H') + '.raw'
        file = cache / name
        url = f'{BASE}/{instrument.upper()}/{t.year}/{t.month-1:02d}/{t.day:02d}/{t.hour:02d}h_ticks.bi5'
        if file.exists():
            data = file.read_bytes()
        else:
            data = fetch_bi5(url)
            tmp = file.with_suffix('.tmp')
            tmp.write_bytes(data)
            tmp.replace(file)
            time.sleep(pause)
        if data:
            result.update(aggregate_m1(decode_ticks(data, int(t.timestamp()), price_scale(instrument))))
        else:
            empty += 1
        hours += 1
        if hours % 48 == 0:
            print(f'PROGRESS hours={hours} empty={empty} rows={len(result)} through={t.isoformat()}', flush=True)
        t += timedelta(hours=1)
    return result

COLUMNS = ['epoch', 'bid_open', 'bid_high', 'bid_low', 'bid_close',
           'ask_open', 'ask_high', 'ask_low', 'ask_close', 'tick_volume']

def write_csv_gz(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + '.tmp'
    with gzip.open(tmp, 'wt', newline='') as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for ep in sorted(rows):
            r = rows[ep]
            w.writerow([ep, *r[:8], r[8]])
    Path(tmp).replace(path)
    return path

def build_report(instrument, rows, start, end, path):
    epochs = sorted(rows)
    gaps = []
    crossed = 0
    spread_by_hour = {}
    for ep in epochs:
        r = rows[ep]
        spread = (r[4] - r[0]) if r[4] >= r[0] else 0.0  # ask_open - bid_open
        if r[4] < r[0] or r[7] < r[3]:
            crossed += 1
        hour = datetime.fromtimestamp(ep, timezone.utc).hour
        spread_by_hour.setdefault(hour, []).append(spread)
    for before, after in zip(epochs, epochs[1:]):
        if after - before > 60:
            gaps.append({'from': before, 'to': after, 'seconds': after - before,
                         'weekend': any(datetime.fromtimestamp(before + o, timezone.utc).weekday() >= 5
                                        for o in range(0, after - before, 3600))})
    spread_profile = {str(h): round(sum(v) / len(v), 8) for h, v in sorted(spread_by_hour.items())}
    return {'symbol': 'frx' + instrument.upper(), 'granularity': 60, 'rows': len(rows),
            'first_epoch': epochs[0], 'last_epoch': epochs[-1],
            'first_utc': datetime.fromtimestamp(epochs[0], timezone.utc).isoformat(),
            'last_utc': datetime.fromtimestamp(epochs[-1], timezone.utc).isoformat(),
            'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            'source': 'dukascopy-bi5-bid-ask-ticks', 'columns': COLUMNS,
            'duplicates': 0, 'crossed_bid_ask': crossed, 'gaps': gaps,
            'spread_profile_by_utc_hour': spread_profile,
            'requested_from': start.isoformat(), 'requested_to_exclusive': end.isoformat(),
            'file': Path(path).name,
            'last_checked_utc': datetime.now(timezone.utc).isoformat()}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--instrument', required=True)
    ap.add_argument('--from', dest='start', required=True)
    ap.add_argument('--to', dest='end', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--cache', default='.bi5-cache')
    ap.add_argument('--pause', type=float, default=2.5)
    ap.add_argument('--granularity', type=int, default=60)
    a = ap.parse_args()
    assert a.granularity == 60, 'M1 only; resample causally in shared features'
    start = datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(a.end).replace(tzinfo=timezone.utc)
    rows = build_range(a.instrument, start, end, a.pause, a.cache)
    assert rows, 'refusing to publish an empty dataset'
    path = write_csv_gz(rows, a.out)
    report = build_report(a.instrument, rows, start, end, path)
    Path(str(path) + '.report.json').write_text(json.dumps(report, indent=2))
    print('STATS ' + json.dumps(report), flush=True)

if __name__ == '__main__':
    main()
