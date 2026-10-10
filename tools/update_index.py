#!/usr/bin/env python3
"""Merge one pair's STATS line into a data/index.json fragment (DATA task).

Usage: python tools/update_index.py --stats-file fetch.log --release data-01
Writes data/fragment_<symbol>_<gran>.json for the finalize job to merge.
"""
import argparse
import json
import os
import re

ap = argparse.ArgumentParser()
ap.add_argument("--stats-file", required=True)
ap.add_argument("--release", required=True)
ap.add_argument("--out-dir", default="data/fragments")
a = ap.parse_args()

stats = None
for line in open(a.stats_file):
    if line.startswith("STATS "):
        stats = json.loads(line[6:])
assert stats, "no STATS line found in fetch log"

sym = stats["symbol"]
entry = {
    "release_tag": a.release,
    "asset": stats["file"],
    "rows": stats["rows"],
    "first_epoch": stats["first_epoch"],
    "last_epoch": stats["last_epoch"],
    "sha256": stats["sha256"],
    "last_checked_utc": stats["last_checked_utc"],
    "source": stats["source"],
}
os.makedirs(a.out_dir, exist_ok=True)
out = os.path.join(a.out_dir, f"{sym}_{stats['granularity']}.json")
json.dump({sym: entry}, open(out, "w"), indent=1)
print("fragment written:", out, json.dumps(entry)[:200])
