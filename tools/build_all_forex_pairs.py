#!/usr/bin/env python3
"""Batch process all 14 target forex pairs into multi-year M1 datasets with annual shards.
"""

import sys
import time
from pathlib import Path
from tools.fetch_forex_history import fetch_and_build_pair

TARGET_PAIRS = [
    'USDJPY',
    'GBPUSD',
    'AUDUSD',
    'USDCAD',
    'USDCHF',
    'NZDUSD',
    'EURGBP',
    'EURJPY',
    'GBPJPY',
    'EURAUD',
    'AUDJPY',
    'EURCAD',
    'EURCHF',
]

YEARS = ['2021', '2022', '2023', '2024']


def main():
    out_dir = Path('data/forex_cache')
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f'Starting batch multi-year forex data generation for {len(TARGET_PAIRS)} pairs...')
    results = {}
    for p in TARGET_PAIRS:
        t0 = time.time()
        try:
            full_path, report = fetch_and_build_pair(p, YEARS, out_dir)
            results[p] = {
                'status': 'OK',
                'rows': report['rows'],
                'first_utc': report['first_utc'],
                'last_utc': report['last_utc'],
                'elapsed': round(time.time() - t0, 1),
            }
            print(f'Done {p}: {results[p]}')
        except Exception as e:
            print(f'ERROR on {p}: {e}')
            results[p] = {'status': 'FAIL', 'error': str(e)}
        time.sleep(1.0)

    print('\n=== ALL PAIRS COMPLETED ===')
    for p, r in results.items():
        print(f'{p}: {r}')


if __name__ == '__main__':
    main()
