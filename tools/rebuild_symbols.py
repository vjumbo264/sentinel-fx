#!/usr/bin/env python3
"""Rebuilds data/symbols.json from live MT5 broker connection.

Connects to MT5 terminal via RPyC bridge, queries all visible symbols,
filters exclusively for Forex and Synthetic indices, extracts contract size,
digits, volumes, spreads, swaps, and outputs formatted data/symbols.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

def categorize_symbol(name: str, path: str = "") -> str:
    n = name.upper()
    p = path.upper() if path else ""
    if any(k in n for k in ["VOLATILITY", "HZ", "BOOM", "CRASH", "STEP", "JUMP", "DEX", "DRIFT", "R_"]) or "SYNTHETIC" in p:
        return "synthetic"
    if any(k in n for k in ["EUR", "USD", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "FRX"]) or "FOREX" in p:
        return "forex"
    return "other"

def main():
    parser = argparse.ArgumentParser(description="Rebuild data/symbols.json from live MT5")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=18812)
    parser.add_argument("--out", default="data/symbols.json")
    args = parser.parse_args()

    import rpyc
    conn = rpyc.classic.connect(args.host, args.port)
    mt5 = conn.modules.MetaTrader5
    if not mt5.initialize():
        print(f"Failed to initialize MT5: {mt5.last_error()}", file=sys.stderr)
        sys.exit(1)

    symbols_raw = mt5.symbols_get() or []
    symbols_map = {}

    for s in symbols_raw:
        cat = categorize_symbol(s.name, getattr(s, "path", ""))
        if cat not in ("forex", "synthetic"):
            continue

        dukascopy_name = s.name if cat == "forex" else None
        # Clean Dukascopy name if needed
        if dukascopy_name and len(dukascopy_name) > 6:
            for clean_pair in ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY", "EURAUD", "AUDJPY", "EURCAD", "EURCHF"]:
                if clean_pair in dukascopy_name:
                    dukascopy_name = clean_pair
                    break

        entry = {
            "mt5_symbol": s.name,
            "dukascopy_symbol": dukascopy_name,
            "type": cat,
            "digits": int(s.digits),
            "contract_size": float(s.trade_contract_size),
            "volume_min": float(s.volume_min),
            "volume_max": float(s.volume_max),
            "volume_step": float(s.volume_step),
            "stops_level": int(s.trade_stops_level),
            "typical_spread_pts": int(s.spread),
            "swap_long": float(s.swap_long),
            "swap_short": float(s.swap_short),
            "trading_sessions": "24/7/365" if cat == "synthetic" else "Sun 21:05 - Fri 20:55 UTC",
            "margin_currency": getattr(s, "currency_margin", "USD"),
            "point": float(s.point)
        }
        symbols_map[s.name] = entry

    data = {
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "version": 2,
        "count": len(symbols_map),
        "symbols": symbols_map
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Rebuilt {args.out} with {len(symbols_map)} symbols ({sum(1 for s in symbols_map.values() if s['type']=='forex')} forex, {sum(1 for s in symbols_map.values() if s['type']=='synthetic')} synthetic).")

if __name__ == "__main__":
    main()
