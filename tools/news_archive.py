#!/usr/bin/env python3
"""SENTINEL-FX news archive builder (NEWS task).

Fetches this week + next week from https://nfs.faireconomy.media/ (the host
that works in the owner's Aurelia bot), normalizes to UTC and UPSERTS into
news_archive.jsonl.gz. Old events are NEVER deleted; forecast revisions are
kept in forecast_history[] with timestamps (no hindsight bias).

Event schema: id, utc_time, currency, title, impact, forecast, previous,
actual (null unless a source provides it), source, first_seen_utc,
last_seen_utc, forecast_history[].

Usage: python tools/news_archive.py --archive out/news_archive.jsonl.gz \
           [--existing prev/news_archive.jsonl.gz]
Prints a final line "STATS {json}".
"""
from __future__ import annotations
import argparse
import gzip
import json
import os
from datetime import datetime, timezone

from sentinel_engine import news as newsmod


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_existing(path):
    events = {}
    if path and os.path.exists(path):
        with gzip.open(path, "rt") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                ev = json.loads(line)
                events[ev["id"]] = ev
    return events


def upsert(store, ev, ts):
    cur = store.get(ev["id"])
    if cur is None:
        store[ev["id"]] = {
            **ev, "actual": None, "source": "nfs.faireconomy.media",
            "first_seen_utc": ts, "last_seen_utc": ts,
            "forecast_history": ([{"utc": ts, "forecast": ev["forecast"],
                                   "previous": ev["previous"]}]
                                 if ev.get("forecast") or ev.get("previous")
                                 else []),
        }
        return "new"
    cur["last_seen_utc"] = ts
    if (ev.get("forecast") != cur.get("forecast")
            or ev.get("previous") != cur.get("previous")):
        cur["forecast_history"].append({
            "utc": ts, "forecast": ev.get("forecast"),
            "previous": ev.get("previous")})
        cur["forecast"] = ev.get("forecast")
        cur["previous"] = ev.get("previous")
        return "revised"
    return "kept"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", default="out/news_archive.jsonl.gz")
    ap.add_argument("--existing", default=None)
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.archive) or ".", exist_ok=True)

    store = load_existing(a.existing)
    n0 = len(store)
    ts = now_iso()

    raw = newsmod.fetch_calendar(newsmod.URL_THIS)      # 2-per-5min guard inside
    try:
        raw = raw + newsmod.fetch_calendar(newsmod.URL_NEXT)
    except RuntimeError as e:
        print(f"[news] next-week unavailable ({e}); continuing", flush=True)
    events = newsmod.normalize(raw)

    counts = {"new": 0, "revised": 0, "kept": 0}
    for ev in events:
        counts[upsert(store, ev, ts)] += 1

    tmp = a.archive + ".tmp"
    with gzip.open(tmp, "wt") as f:
        for ev in sorted(store.values(), key=lambda e: (e["utc_time"], e["id"])):
            f.write(json.dumps(ev, sort_keys=True) + "\n")
    os.replace(tmp, a.archive)  # never leave a half-written archive

    stats = {"events_total": len(store), "previously": n0, **counts,
             "run_utc": ts}
    print("STATS " + json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
