#!/usr/bin/env python3
"""Resumable HistData M1 annual shards, with explicit bid-only ask assumptions."""
import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import sys
import time
import zipfile
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requests
from tools.release_utils import ROOT, REPO, GitHub, pair_key, upload_asset_with_overflow

PAIRS = 'EURUSD GBPUSD USDJPY USDCHF AUDUSD USDCAD NZDUSD EURGBP EURJPY GBPJPY AUDJPY EURAUD GBPAUD'.split()
COLUMNS = ['epoch'] + [f'{side}_{field}' for side in ('bid', 'ask') for field in ('open', 'high', 'low', 'close')]

class WallReached(Exception):
    pass

class PacedRequests:
    """Pace EACH underlying GET/POST (not just downloads); honor Retry-After."""
    def __init__(self, deadline):
        self.deadline, self.last = deadline, 0.0
        self.request = requests.sessions.Session.request

    def call(self, session, method, url, **kwargs):
        for attempt in range(6):
            if time.monotonic() >= self.deadline:
                raise WallReached()
            time.sleep(max(0, 2 - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            kwargs.setdefault('timeout', 90)
            # histdata's fixed POST Content-Length can be stale. requests recomputes it.
            headers = kwargs.get('headers', {})
            headers.pop('Content-Length', None)
            response = self.request(session, method, url, **kwargs)
            if response.status_code != 429:
                response.raise_for_status()
                return response
            value = response.headers.get('Retry-After', '2')
            try:
                delay = float(value)
            except ValueError:
                delay = max(0, parsedate_to_datetime(value).timestamp() - time.time())
            if time.monotonic() + delay >= self.deadline:
                raise WallReached()
            time.sleep(max(2, delay))
        raise RuntimeError('HistData rate limit retries exhausted')


def parse_zip(path, specs):
    # HistData timestamps use fixed EST without daylight-saving adjustment.
    est = timezone(timedelta(hours=-5))
    point = float(specs['point'])
    spread = float(specs['spread']) * point if specs.get('spread') is not None else 1.5 * point
    rows = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.lower().endswith('.csv'):
                continue
            with archive.open(name) as binary:
                for fields in csv.reader(io.TextIOWrapper(binary, encoding='utf-8-sig'), delimiter=';'):
                    if len(fields) < 5:
                        continue
                    dt = datetime.strptime(fields[0], '%Y%m%d %H%M%S').replace(tzinfo=est)
                    bids = [float(v) for v in fields[1:5]]
                    if min(bids) <= 0 or bids[1] < max(bids[0], bids[3]) or bids[2] > min(bids[0], bids[3]):
                        raise ValueError('invalid HistData OHLC row')
                    epoch = int(dt.timestamp())
                    rows[epoch] = [epoch] + bids + [v + spread for v in bids]
    return rows


def completed_pair(index, pair):
    entry = index.get(pair_key(index, pair), {})
    return bool(entry.get('bulk_complete'))


def run(pairs, dry_run=False):
    index = json.loads((ROOT / 'data/index.json').read_text())
    if dry_run:
        for pair in pairs:
            print(pair, 'SKIP completed bulk' if completed_pair(index, pair) else 'pending bulk years')
        return
    token = os.environ.get('GH_CHAIN_PAT') or os.environ.get('GH_TOKEN')
    if not token:
        raise RuntimeError('GH_CHAIN_PAT required')
    gh = GitHub(token)
    specs = json.loads((ROOT / 'data/symbols.json').read_text())['symbols']
    current = datetime.now(timezone.utc)
    deadline = time.monotonic() + int(os.environ.get('FETCH_WALL_SECONDS', '17100'))
    pacer = PacedRequests(deadline)
    from histdata import download_hist_data as dl
    from histdata.api import Platform as P, TimeFrame as TF
    cache = ROOT / 'data/forex_cache/histdata'
    cache.mkdir(parents=True, exist_ok=True)
    failures = []
    try:
        for pair in pairs:
            index = json.loads((ROOT / 'data/index.json').read_text())
            if completed_pair(index, pair):
                print(pair, 'SKIP completed bulk', flush=True)
                continue
            key = pair_key(index, pair)
            for year in range(2000, current.year + 1):
                if time.monotonic() >= deadline:
                    raise WallReached()
                entry = json.loads((ROOT / 'data/index.json').read_text()).get(key, {})
                if str(year) in entry.get('bulk_years', {}):
                    continue
                rows = {}
                try:
                    # Current year is provided as MONTHLY archives by histdata.
                    months = range(1, current.month) if year == current.year else [None]
                    if year == current.year and current.month == 1:
                        continue
                    for month in months:
                        def request(session, method, url, **kw):
                            return pacer.call(session, method, url, **kw)
                        with patch.object(requests.sessions.Session, 'request', request):
                            path = dl(year=str(year), month=str(month) if month else None,
                                      pair=pair.lower(), time_frame=TF.ONE_MINUTE,
                                      platform=P.GENERIC_ASCII, output_directory=str(cache), verbose=False)
                        rows.update(parse_zip(path, specs[pair]))
                    if not rows:
                        raise ValueError('empty archive')
                    text = io.StringIO()
                    writer = csv.writer(text); writer.writerow(COLUMNS)
                    writer.writerows(rows[e] for e in sorted(rows))
                    raw = gzip.compress(text.getvalue().encode(), mtime=0)
                    # Current partial year name is date-versioned to avoid replacing immutable history.
                    name = f'{pair}_{year}.csv.gz' if year < current.year else f'{pair}_{year}_through_{current.month-1:02d}.csv.gz'
                    tag = upload_asset_with_overflow(token, REPO, pair, name, raw)
                    epochs = sorted(rows)
                    meta = {'asset': name, 'release_tag': tag, 'rows': len(rows),
                            'first_epoch': epochs[0], 'last_epoch': epochs[-1],
                            'sha256': hashlib.sha256(raw).hexdigest()}
                    def merge(index):
                        entry = index.setdefault(key, {'symbol': key, 'granularity': 60})
                        entry.setdefault('bulk_years', {})[str(year)] = meta
                        entry['last_epoch'] = max(entry.get('last_epoch', 0), epochs[-1])
                        entry['first_epoch'] = min(entry.get('first_epoch', epochs[0]), epochs[0])
                        entry['rows'] = sum(v['rows'] for v in entry['bulk_years'].values())
                        entry['columns'] = COLUMNS
                        entry['source'] = 'histdata-bid-only-synthetic-ask'
                        entry['ask_assumption'] = 'spread registry points × point, else 1.5 × point; NOT measured spread'
                        return index
                    gh.commit_json('data/index.json', merge, f'Q3: checkpoint {pair} {year} verified annual shard [skip ci]')
                    print(pair, year, len(rows), tag, flush=True)
                except WallReached:
                    raise
                except Exception as exc:
                    failures.append(f'{pair} {year}: {exc}')
                    def record(index):
                        index.setdefault(key, {}).setdefault('bulk_unavailable', {})[str(year)] = {
                            'error': str(exc), 'checked_utc': current.isoformat(), 'status': 'unavailable_not_complete'}
                        return index
                    gh.commit_json('data/index.json', record, f'Q3: record unavailable {pair} {year} honestly [skip ci]')
            def finish(index):
                entry = index.setdefault(key, {})
                years = entry.get('bulk_years', {})
                entry['bulk_complete'] = all(str(y) in years for y in range(2000, current.year + 1))
                return index
            gh.commit_json('data/index.json', finish, f'Q3: checkpoint {pair} bulk status [skip ci]')
    except WallReached:
        gh.dispatch('histdata-bulk.yml', {'pairs': ','.join(pairs)})
        print('Wall reached: all successful years committed, successor dispatched')
        return
    if failures:
        raise RuntimeError('Some years unavailable; successful data committed. ' + '; '.join(failures[:5]))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pairs', default=','.join(PAIRS))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    pairs = [p.strip().upper() for p in args.pairs.split(',') if p.strip()]
    if any(p not in PAIRS for p in pairs):
        parser.error('unsupported target pair')
    run(pairs, args.dry_run)
