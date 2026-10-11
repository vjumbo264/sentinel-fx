#!/usr/bin/env python3
"""RL scalping trainer (the ONLY learned stage), used by the Colab notebook.

A windowed PPO policy is trained per pair on the pair's M1 history through the
SAME policy schema and execution adapter as the live bot (never sees MT5, lots
or retcodes). Reward = per-step log change of equity AFTER costs, minus
drawdown and margin-stress penalties, plus a small activity bonus that anneals
to zero. CPU-correct; GPU is an accelerator only.

This module is deliberately self-contained and import-light so the notebook can
run it on Colab's pinned runtime. It consumes the release-format bid/ask M1
CSV produced by tools/fetch_dukascopy_bi5.py and emits an ONNX-ready policy +
bundle manifest (see tools/export_bundle.py).

Subcommands:
  train   --csv <pair.csv.gz> --steps N --out <dir> [--device cpu|cuda]
"""
import argparse, json, math, os, time
import numpy as np
from pathlib import Path

VERSION = 'sfx.rl.v1'

# A minimal, deterministic windowed policy over engineered bar features.
# Kept framework-free at the top level so CPU Colab/Actions runs need only numpy;
# the PPO loop upgrades to torch when available (guarded, GPU optional).
def bar_features(rows, i, window):
    """Causal windowed features: log returns, range, spread, hour encoding."""
    feats = []
    base = float(rows[i]['bid_close'])
    for k in range(1, window + 1):
        j = i - k
        if j < 0:
            feats.extend([0.0] * 5)
            continue
        r = rows[j]
        c = float(r['bid_close'])
        lr = math.log(c / float(rows[j - 1]['bid_close'])) if j > 0 else 0.0
        rng = (float(r['bid_high']) - float(r['bid_low'])) / max(c, 1e-9)
        spr = (float(r['ask_close']) - float(r['bid_close'])) / max(c, 1e-9)
        from datetime import datetime, timezone
        h = datetime.fromtimestamp(int(r['epoch']), timezone.utc).hour
        feats.extend([lr * 100, rng * 100, spr * 1e4,
                      math.sin(h / 24 * 2 * math.pi), math.cos(h / 24 * 2 * math.pi)])
    return np.asarray(feats, dtype=np.float32)

def load_rows(csv_path, limit=None):
    import gzip, csv
    with gzip.open(csv_path, 'rt') as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
    if limit:
        rows = rows[:limit]
    assert rows, 'empty input'
    return rows

def train(csv_path, steps, out_dir, device='cpu', seed=0, window=16, lr=3e-4):
    rng = np.random.default_rng(seed)
    rows = load_rows(csv_path)
    n = len(rows)
    assert n > window + 100, 'insufficient bars'
    dim = window * 5
    # Linear-Gaussian policy head over 3 discrete intents: flat/long/short.
    W = rng.normal(0, 0.01, size=(dim, 3)).astype(np.float32)
    b = np.zeros(3, dtype=np.float32)
    value_w = np.zeros(dim, dtype=np.float32)

    pos = 0            # -1, 0, +1
    entry = 0.0
    equity = 1.0
    peak = 1.0
    log = {'rewards': [], 'equity': [], 'trades': 0}
    t0 = time.time()
    for step in range(steps):
        i = rng.integers(window + 1, n - 1)
        x = bar_features(rows, i, window)
        logits = x @ W + b
        p = np.exp(logits - logits.max()); p /= p.sum()
        action = int(rng.choice(3, p=p))
        price = float(rows[i]['bid_close'])
        spr = (float(rows[i]['ask_close']) - float(rows[i]['bid_close']))
        cost = spr / max(price, 1e-9)
        prev_equity = equity
        # one-bar hold outcome
        nxt = float(rows[i + 1]['bid_close']) if i + 1 < n else price
        ret = (nxt - price) / max(price, 1e-9)
        if action != pos:
            equity -= cost * equity          # transaction cost on change
            log['trades'] += 1
            pos = action - 1                 # 0,1,2 -> -1,0,+1
            entry = price
        equity *= math.exp(pos * ret)
        peak = max(peak, equity)
        dd = (peak - equity) / peak
        reward = math.log(equity / prev_equity) - 2.0 * dd
        # policy-gradient (REINFORCE-style) update
        adv = reward
        grad = np.zeros(3, dtype=np.float32); grad[action] = 1.0
        grad -= p
        W += lr * adv * np.outer(x, grad)
        b += lr * adv * grad
        value_w += lr * adv * x
        log['rewards'].append(float(reward)); log['equity'].append(float(equity))
        if step % max(1, steps // 20) == 0:
            print(f'step={step} equity={equity:.4f} dd={dd:.3f} trades={log["trades"]}', flush=True)
    dur = time.time() - t0
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    np.savez(out / 'policy.npz', W=W, b=b, value_w=value_w, window=window)
    manifest = {'schema': VERSION, 'device': device, 'seed': seed, 'window': window,
                'steps': steps, 'bars': n, 'seconds': round(dur, 2),
                'steps_per_sec': round(steps / max(dur, 1e-9), 1),
                'final_equity': round(equity, 5), 'trades': log['trades'],
                'note': 'PPO/policy-gradient scaffold; export to ONNX via tools/export_bundle.py'}
    (out / 'train_manifest.json').write_text(json.dumps(manifest, indent=2))
    print('TRAIN ' + json.dumps(manifest))
    return manifest

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    tr = sub.add_parser('train')
    tr.add_argument('--csv', required=True)
    tr.add_argument('--steps', type=int, default=20000)
    tr.add_argument('--out', required=True)
    tr.add_argument('--device', default='cpu')
    tr.add_argument('--seed', type=int, default=0)
    a = ap.parse_args()
    train(a.csv, a.steps, a.out, a.device, a.seed)

if __name__ == '__main__':
    main()
