#!/usr/bin/env python3
"""Indicator lab: whitelisted data-only DSL + budgeted, seeded search.

Indicators are COMPOSITIONS of whitelisted operations (never arbitrary code,
never pickle). Before RL, the lab searches parameter/composition space per
pair, scores candidates on PURGED WALK-FORWARD data after costs, keeps the
best K, and writes them to the bundle as indicators.json.

Whitelisted primitives (all causal, data-only):
  ema(close, n)  sma(close, n)  rsi(close, n)  atr(h,l,c, n)
  roc(close, n)  stddev(close, n)  hl_range(h,l)  session_flag(hour)
Composition grammar:  F := prim(args) | (F op F) with op in {+,-,*,/} guarded.

Scoring: walk-forward folds with an embargo gap; per-fold the indicator's
signal drives a simple threshold strategy scored by net log-growth after a
cost model (spread + commission). Deterministic seeds; budgeted evaluations.

Usage:
  python tools/indicator_lab.py --csv out/frxEURUSD_60s.csv.gz --k 8 \
      --budget 200 --seed 7 --out indicators.json
"""
import argparse, gzip, csv, json, math, random
import numpy as np
from pathlib import Path

# ---- Whitelisted causal primitives --------------------------------------
def _ema(x, n):
    a = 2.0 / (n + 1)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out

def _sma(x, n):
    c = np.concatenate([[0.0], np.cumsum(x)])
    out = np.full_like(x, np.nan, dtype=float)
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out

def _rsi(close, n):
    d = np.diff(close, prepend=close[0])
    up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    ru = _ema(up, n); rd = _ema(dn, n)
    rs = np.divide(ru, rd, out=np.zeros_like(ru), where=rd > 0)
    return 100 - 100 / (1 + rs)

def _atr(h, l, c, n):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return _ema(tr, n)

def _roc(x, n):
    out = np.full_like(x, 0.0, dtype=float)
    out[n:] = (x[n:] - x[:-n]) / np.where(np.abs(x[:-n]) > 0, x[:-n], 1.0)
    return out

def _stddev(x, n):
    m = _sma(x, n)
    c = np.concatenate([[0.0], np.cumsum(x * x)])
    mean2 = np.full_like(x, np.nan)
    mean2[n - 1:] = (c[n:] - c[:-n]) / n
    var = np.clip(mean2 - np.where(np.isnan(m), 0, m) ** 2, 0, None)
    return np.sqrt(var)

PRIMS = {
    'ema': (_ema, ('n',)), 'sma': (_sma, ('n',)), 'rsi': (_rsi, ('n',)),
    'atr': (_atr, ('n',)), 'roc': (_roc, ('n',)), 'stddev': (_stddev, ('n',)),
}
PARAM_RANGE = {'n': (3, 200)}
OPS = ['+', '-', '*', '/']

def compile_dsl(node):
    """node: {'prim':name,'n':int} or {'op':op,'l':node,'r':node}. -> callable(h,l,c)->np.array"""
    if 'prim' in node:
        name, n = node['prim'], int(node['n'])
        fn = PRIMS[name][0]
        return lambda h, l, c: fn(c, n) if name != 'atr' else fn(h, l, c, n)
    op, lf, rf = node['op'], compile_dsl(node['l']), compile_dsl(node['r'])
    def apply(h, l, c):
        a, b = lf(h, l, c), rf(h, l, c)
        n = min(len(a), len(b))
        a, b = a[-n:], b[-n:]            # align causal tails; never invent leading data
        if op == '+': return a + b
        if op == '-': return a - b
        if op == '*': return a * b
        return np.divide(a, b, out=np.zeros_like(a), where=np.abs(b) > 1e-12)
    return apply

def random_node(rng, depth):
    if depth <= 0 or rng.random() < 0.5:
        name = rng.choice(list(PRIMS))
        return {'prim': name, 'n': rng.randint(*PARAM_RANGE['n'])}
    return {'op': rng.choice(OPS), 'l': random_node(rng, depth - 1), 'r': random_node(rng, depth - 1)}

def walk_forward_folds(n_bars, folds=5, embargo=240):
    edges = np.linspace(0, n_bars, folds + 2).astype(int)
    out = []
    for i in range(1, folds + 1):
        train = (0, edges[i]); test = (edges[i] + embargo, edges[i + 1])
        if test[1] > test[0]:
            out.append((train, test))
    return out

def score_signal(sig, mid, spread, folds, cost):
    """Threshold strategy: long/short on signal sign change; net log-growth."""
    rets = []
    for (_, _), (t0, t1) in folds:
        ln = min(len(sig), len(mid))
        s = sig[-ln:]; m = mid[-ln:]; sp = spread[-ln:]
        t0 = max(0, t0 - (len(mid) - ln)); t1 = min(ln, t1 - (len(mid) - ln))
        if t1 - t0 < 60: continue
        s = s[t0:t1]; m = m[t0:t1]; sp = sp[t0:t1]
        pos = np.sign(s[:-1]); dlog = np.diff(np.log(m))
        cost_vec = sp[:-1] / m[:-1] * cost * (np.abs(np.diff(pos)) > 0)
        pnl = pos * dlog - cost_vec
        rets.append(np.nansum(pnl))
    return float(np.mean(rets)) if rets else -1e9

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', required=True)
    ap.add_argument('--k', type=int, default=8)
    ap.add_argument('--budget', type=int, default=200)
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--folds', type=int, default=5)
    ap.add_argument('--cost', type=float, default=1.0)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    with gzip.open(a.csv, 'rt') as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
    assert rows, 'empty input'
    bid_c = np.array([float(r['bid_close']) for r in rows])
    ask_c = np.array([float(r['ask_close']) for r in rows])
    bid_h = np.array([float(r['bid_high']) for r in rows])
    bid_l = np.array([float(r['bid_low']) for r in rows])
    mid = (bid_c + ask_c) / 2
    spread = ask_c - bid_c
    folds = walk_forward_folds(len(mid), a.folds)
    best = []
    for _ in range(a.budget):
        node = random_node(rng, depth=3)
        try:
            sig = np.nan_to_num(compile_dsl(node)(bid_h, bid_l, bid_c), nan=0.0, posinf=0.0, neginf=0.0)
            if not np.isfinite(sig).any() or np.all(sig == 0):
                continue
            sc = score_signal(sig, mid, spread, folds, a.cost)
        except Exception:
            continue
        best.append((sc, node))
    best.sort(key=lambda x: x[0], reverse=True)
    winners = [{'score': round(s, 6), 'node': n} for s, n in best[:a.k]]
    out = {'schema': 'sfx.indicators.v1', 'k': len(winners), 'seed': a.seed,
           'budget': a.budget, 'folds': a.folds, 'cost_multiplier': a.cost,
           'indicators': winners}
    Path(a.out).write_text(json.dumps(out, indent=2))
    print('LAB ' + json.dumps({'evaluated': a.budget, 'kept': len(winners),
                               'best': winners[0]['score'] if winners else None}))

if __name__ == '__main__':
    main()
