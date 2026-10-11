"""Test parity between engine indicator library and indicator lab primitives.
Verifies byte-for-byte / float parity on real forex release candles.
"""

import gzip
import csv
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from sentinel_engine import indicators as ind
from tools.indicator_lab import _ema, _sma, _rsi, _atr, _roc, _stddev, compile_dsl

@pytest.fixture(scope="module")
def real_candles():
    p = Path("data/forex_cache/frxEURUSD_2021_60s.csv.gz")
    if not p.exists():
        # Fallback to any available cached shard
        cand = list(Path("data/forex_cache").glob("*_2021_60s.csv.gz"))
        assert cand, "Real forex shard required for parity test"
        p = cand[0]
        
    with gzip.open(p, "rt") as f:
        rdr = csv.DictReader(f)
        rows = []
        for i, r in enumerate(rdr):
            if i >= 1000:
                break
            rows.append({
                "epoch": int(r["epoch"]),
                "open": float(r.get("bid_open", r.get("open"))),
                "high": float(r.get("bid_high", r.get("high"))),
                "low": float(r.get("bid_low", r.get("low"))),
                "close": float(r.get("bid_close", r.get("close"))),
                "tick_volume": int(float(r.get("tick_volume", 1)))
            })
    return pd.DataFrame(rows)

def test_sma_parity(real_candles):
    c = real_candles["close"].to_numpy()
    period = 14
    s_lab = _sma(c, period)
    s_eng = ind.sma(real_candles["close"], period).to_numpy()
    # compare valid non-nan region
    valid = ~np.isnan(s_lab)
    np.testing.assert_allclose(s_lab[valid], s_eng[valid], rtol=1e-5, atol=1e-5)

def test_ema_parity(real_candles):
    c = real_candles["close"].to_numpy()
    period = 20
    e_lab = _ema(c, period)
    e_eng = ind.ema(real_candles["close"], period).to_numpy()
    np.testing.assert_allclose(e_lab[period:], e_eng[period:], rtol=1e-4, atol=1e-4)

def test_rsi_parity(real_candles):
    c = real_candles["close"].to_numpy()
    period = 14
    r_lab = _rsi(c, period)
    r_eng = ind.rsi(real_candles["close"], period).to_numpy()
    np.testing.assert_allclose(r_lab[period * 2:], r_eng[period * 2:], rtol=1e-3, atol=1e-2)

def test_atr_parity(real_candles):
    h = real_candles["high"].to_numpy()
    l = real_candles["low"].to_numpy()
    c = real_candles["close"].to_numpy()
    period = 14
    a_lab = _atr(h, l, c, period)
    a_eng = ind.atr(real_candles["high"], real_candles["low"], real_candles["close"], period).to_numpy()
    np.testing.assert_allclose(a_lab[period * 2:], a_eng[period * 2:], rtol=1e-3, atol=1e-4)

def test_indicator_lab_walk_forward_execution(real_candles):
    c = real_candles["close"].to_numpy()
    h = real_candles["high"].to_numpy()
    l = real_candles["low"].to_numpy()
    # grammar expression evaluation
    node = {'prim': 'rsi', 'n': 14}
    fn = compile_dsl(node)
    sig = fn(h, l, c)
    assert len(sig) == len(c)
    assert np.isfinite(sig[28:]).all()
