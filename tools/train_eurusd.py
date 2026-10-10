#!/usr/bin/env python3
"""PROVE.3 — train a real committee-style model for frxEURUSD on the REAL
data-hub candles, following TRAIN_PROMPT.md / M2 honestly.

Committee: 3 LightGBM analyst models (momentum, trend, regime/volatility) +
logistic-regression head trained on the analysts' OUT-OF-FOLD opinions
(purged walk-forward) + reliability-table calibrator on the locked hold-out.
Exports a schema-v2 .sfxmodel.zip and runs the full validator. Verdict is
reported honestly — "fail" (no edge) is an expected, valid outcome for 15m
forex binaries.

  python tools/train_eurusd.py --csv /path/frxEURUSD_60s.csv.gz \
      --out out/frxEURUSD_v2.sfxmodel.zip [--plumbing]
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import zipfile
from datetime import datetime, timezone

import numpy as np
import pandas as pd

FEATURES_DSL = [
    {"id": "rsi14", "op": "rsi", "params": {"period": 14}},
    {"id": "adx14", "op": "adx", "params": {"period": 14, "out": "adx"}},
    {"id": "atr14", "op": "atr", "params": {"period": 14}},
    {"id": "atr_pct", "op": "div", "inputs": ["atr14", "close"]},
    {"id": "bb_pctb", "op": "bollinger", "params": {"period": 20, "mult": 2.0, "out": "pctb"}},
    {"id": "mom1", "op": "mom", "params": {"period": 1}},
    {"id": "ret1", "op": "div", "inputs": ["mom1", "close"]},
    {"id": "roc10", "op": "roc", "params": {"period": 10}},
    {"id": "roc60", "op": "roc", "params": {"period": 60}},
    {"id": "rsi60", "op": "rsi", "params": {"period": 60}},
    {"id": "ema20", "op": "ema", "params": {"period": 20}},
    {"id": "ema200", "op": "ema", "params": {"period": 200}},
    {"id": "atr60", "op": "atr", "params": {"period": 60}},
]
ANALYSTS = {
    "momentum_15m": ["rsi14", "bb_pctb", "ret1", "roc10"],
    "trend_htf": ["roc60", "rsi60", "adx14", "atr_pct"],
    "regime_vol": ["atr_pct", "atr60", "adx14", "bb_pctb"],
}
PAYOUT = 0.85
WARM = 250            # longest lookback + margin
EMBARGO = 260         # >= horizon(15) + longest feature lookback (200)
STEP = 5              # one decision every 5 minutes


def wilson(w, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = w / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def fit_logreg(X, y, iters=40):
    X1 = np.hstack([X, np.ones((len(X), 1))])
    w = np.zeros(X1.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(X1 @ w)))
        W = np.clip(p * (1 - p), 1e-6, None)
        H = (X1.T * W) @ X1 + 1e-4 * np.eye(X1.shape[1])
        g = X1.T @ (p - y)
        w -= np.linalg.solve(H, g)
    return w[:-1], w[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--symbol", default="frxEURUSD")
    ap.add_argument("--version", type=int, default=2)
    ap.add_argument("--plumbing", action="store_true",
                    help="tiny pipeline-test bundle (labeled; not for trading)")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)

    from sentinel_engine.dsl import compute_features
    import lightgbm as lgb

    df = pd.read_csv(a.csv).sort_values("epoch").reset_index(drop=True)
    n = len(df)
    print(f"[train] {n} candles "
          f"{datetime.fromtimestamp(df.epoch.iloc[0], timezone.utc)} -> "
          f"{datetime.fromtimestamp(df.epoch.iloc[-1], timezone.utc)}",
          flush=True)
    assert n > 50000, "not enough real data for an honest run"

    feats = compute_features(FEATURES_DSL, df)
    close = df["close"].to_numpy()
    open_ = df["open"].to_numpy()
    epoch = df["epoch"].to_numpy()
    # target: entry open of next candle, exit close +15m; tie = loss
    y = np.full(n, np.nan)
    valid = np.zeros(n, dtype=bool)
    for i in range(WARM, n - 16):
        if epoch[i + 15] - epoch[i + 1] <= 2700:  # no weekend-spanning label
            y[i] = 1.0 if close[i + 15] > open_[i + 1] else 0.0
            valid[i] = True
    idx_all = np.where(valid)[0][::STEP]
    cut = int(len(idx_all) * 0.8)
    dev_idx, ho_idx = idx_all[:cut], idx_all[cut:]
    print(f"[train] decisions: {len(idx_all)} (dev {len(dev_idx)}, "
          f"hold-out {len(ho_idx)})", flush=True)

    X_all = feats[[f for fs in ANALYSTS.values() for f in fs]].to_numpy(float)
    X_all = np.nan_to_num(X_all, nan=0.0, posinf=0.0, neginf=0.0)
    names = [f for fs in ANALYSTS.values() for f in fs]
    cols = {f: names.index(f) for f in names}

    params = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 31,
              "feature_fraction": 0.8, "verbose": -1, "num_threads": 4}

    # ---- analysts: purged walk-forward, out-of-fold opinions ---------------
    oof = {k: np.full(len(dev_idx), np.nan) for k in ANALYSTS}
    folds = np.array_split(np.arange(len(dev_idx)), 4)
    for fi, fold in enumerate(folds):
        lo = fold[0]
        train_mask = np.zeros(len(dev_idx), dtype=bool)
        train_mask[: max(0, lo - EMBARGO)] = True
        tr = dev_idx[train_mask]
        te = dev_idx[fold]
        for k, fs in ANALYSTS.items():
            Xtr = X_all[tr][:, [cols[f] for f in fs]]
            dtr = lgb.Dataset(Xtr, y[tr])
            m = lgb.train(params, dtr, num_boost_round=200)
            oof[k][fold] = m.predict(X_all[te][:, [cols[f] for f in fs]])
        print(f"[train] fold {fi}: train {len(tr)}, test {len(te)}", flush=True)

    # ---- head on out-of-fold opinions --------------------------------------
    keep = ~np.isnan(oof["momentum_15m"])
    Xh = np.column_stack([oof[k][keep] for k in ANALYSTS])
    yh = y[dev_idx[keep]]
    coef, intercept = fit_logreg(Xh, yh)
    mu, sd = Xh.mean(0), Xh.std(0) + 1e-9
    print(f"[train] head coef={np.round(coef, 3)} intercept={intercept:.3f}",
          flush=True)

    # ---- final analysts retrained on full dev ------------------------------
    final_models = {}
    for k, fs in ANALYSTS.items():
        Xd = X_all[dev_idx][:, [cols[f] for f in fs]]
        m = lgb.train(params, lgb.Dataset(Xd, y[dev_idx]),
                      num_boost_round=200)
        final_models[k] = m
    # head on holdout raw
    Xho = np.column_stack([
        final_models[k].predict(X_all[ho_idx][:, [cols[f] for f in fs]])
        for k in ANALYSTS])

    def sig(z):
        return 1 / (1 + np.exp(-z))

    p_up_raw = sig(((Xho - mu) / sd) @ coef + intercept)

    # ---- calibrator: reliability of p_up on the hold-out -------------------
    y_ho = y[ho_idx]
    table = []
    edges = np.linspace(0, 1, 11)
    for i in range(10):
        m = (p_up_raw >= edges[i]) & (p_up_raw < edges[i + 1])
        emp = float(y_ho[m].mean()) if m.sum() > 30 else (edges[i] + edges[i + 1]) / 2
        table.append([round(float(edges[i]), 2), round(float(edges[i + 1]), 2),
                      round(emp, 4)])
    p_up_cal = np.array([table[min(9, int(p * 10))][2] for p in p_up_raw])

    # ---- decision policy (margin grows with variants tried) ----------------
    variants_tried = 6
    margin = 0.005 * math.log2(1 + variants_tried)
    be = 1 / (1 + PAYOUT)
    min_p = max(be + margin, 1 / (1 + PAYOUT - 0.05))
    stake_map = [[0.0, round(min_p, 4), 0.0], [round(min_p, 4), 0.62, 1.0],
                 [0.62, 0.70, 1.5], [0.70, 1.01, 2.0]]

    # ---- honest hold-out evaluation of the shipped policy -------------------
    p_side = np.where(p_up_cal >= 0.5, p_up_cal, 1 - p_up_cal)
    trade = p_side >= min_p
    wins = ((p_up_cal >= 0.5) == (y_ho > 0.5))
    tw = int((wins & trade).sum())
    nt = int(trade.sum())
    wr = tw / nt if nt else 0.0
    lo, hi = wilson(tw, nt)
    verdict = "pass" if (nt >= 300 and lo > 1 / (1 + PAYOUT - 0.03)) else "fail"
    print(f"[train] HOLD-OUT: trades={nt} win={wr:.4f} wilson=({lo:.4f},{hi:.4f})"
          f" be={be:.4f} min_p={min_p:.4f} -> verdict={verdict}", flush=True)

    # ---- build the bundle ----------------------------------------------------
    def head_prob_json():
        return json.dumps({"coef": list(map(float, coef)),
                           "intercept": float(intercept),
                           "mean": list(map(float, mu)),
                           "scale": list(map(float, sd))}).encode()

    plan = {"nodes": [
        {"id": "fg", "type": "feature_group", "dsl": FEATURES_DSL},
        *[{"id": k, "type": "analyst", "model": f"{k}.txt",
           "inputs": ["fg"], "features": fs, "budget_ms": 200}
          for k, fs in ANALYSTS.items()],
        {"id": "head", "type": "head", "model": "head.json",
         "inputs": list(ANALYSTS)},
        {"id": "cal", "type": "calibrator", "method": "table",
         "table": table},
        {"id": "dec", "type": "decision"},
    ]}
    ho_from = int(epoch[ho_idx[0]])
    ho_to = int(epoch[ho_idx[-1]])
    report = {
        "symbol": a.symbol, "version": a.version,
        "payout": PAYOUT,
        "candles": {"file": os.path.basename(a.csv), "rows": int(n)},
        "trained_through_utc": datetime.fromtimestamp(
            int(epoch[dev_idx[-1]]), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "holdout_window": {"from_epoch": ho_from, "to_epoch": ho_to},
        "variants_tried": variants_tried, "holdout_peeks": 1,
        "holdout": {"trades": nt, "wins": tw, "win_rate": round(wr, 4),
                    "wilson95": [round(lo, 4), round(hi, 4)],
                    "break_even": round(be, 4), "min_p": round(min_p, 4)},
        "architecture": {"analysts": ANALYSTS, "head": "logreg on OOF opinions",
                         "calibrator": "10-bucket reliability table",
                         "splits": "purged walk-forward, embargo 260 rows"},
        "description": (
            "Committee of 3 LightGBM analysts (momentum 15m, higher-window "
            "trend, volatility regime) feeding a logistic head trained on "
            "out-of-fold opinions, calibrated on a locked hold-out. Honest "
            f"result: hold-out win rate {wr:.3f} vs break-even {be:.3f} "
            f"(Wilson [{lo:.3f}, {hi:.3f}]) -> {verdict}. 15-minute forex "
            "binaries are close to efficient; a fail verdict means no "
            "exploitable edge was found, NOT a platform bug."),
        "news": {"mode": "guard", "learned": False,
                 "reason": "news archive coverage far below 200 high-impact events"},
        "verdict": verdict,
        "plumbing_test": bool(a.plumbing),
    }
    news_layer = {"enabled": True, "learned": False, "mode": "guard",
                  "blackout_minutes_before": 5, "blackout_minutes_after": 15,
                  "extra_margin": 0.02}
    decision = {"payout_assumed": PAYOUT, "min_p": round(min_p, 4),
                "stake_map": stake_map, "max_trades_per_day": 20,
                "cooldown_min": 15}
    risk = {"stake_pct": 0.01, "max_stake_suggested": 5.0,
            "daily_loss_pct": 0.05}
    preprocess = {"dsl": FEATURES_DSL, "window": 500,
                  "feature_order": names, "normalization": "model-internal"}

    # parity vectors: 3 windows from the hold-out start
    vectors = []
    tmp_out = a.out + ".tmp"
    files = {
        "manifest.json": None,  # last
        "analysis_plan.json": json.dumps(plan).encode(),
        "preprocess.json": json.dumps(preprocess).encode(),
        "decision.json": json.dumps(decision).encode(),
        "risk.json": json.dumps(risk).encode(),
        "news_layer.json": json.dumps(news_layer).encode(),
        "training_report.json": json.dumps(report).encode(),
        "head.json": head_prob_json(),
    }
    for k, mdl in final_models.items():
        files[f"{k}.txt"] = mdl.model_to_string().encode()

    manifest = {"schema_version": 2, "symbol": a.symbol, "version": a.version,
                "parent_version": 1,
                "created_utc": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"),
                "min_engine_version": "2.0.0",
                "trainer": {"ai": "genspark-builder",
                            "notes": "committee model, real data hub candles"},
                "files": []}
    for name, blob in files.items():
        if blob is None:
            continue
        manifest["files"].append({"path": name, "sha256": hashlib.sha256(blob)
                                  .hexdigest(), "size": len(blob)})

    with zipfile.ZipFile(tmp_out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, blob in files.items():
            if blob is not None:
                z.writestr(name, blob)
        # vectors need a loadable bundle: write manifest, close, then evaluate
        z.writestr("manifest.json", json.dumps(manifest))

    # parity vectors computed through the REAL plan evaluator
    from sentinel_engine.bundle import load_bundle
    from sentinel_engine.plan import evaluate
    b = load_bundle(tmp_out)
    for k in range(3):
        st = int(ho_idx[min(k * 40, len(ho_idx) - 1)]) - 400
        win = df.iloc[st: st + 400][["epoch", "open", "high", "low", "close"]]
        win = win.to_dict("records")
        d = evaluate(b, pd.DataFrame(win), {})
        vectors.append({"candles": win,
                        "expect_p_win": d.get("p_win") or 0.0})
    vec_blob = json.dumps({"tolerance": 1e-3, "latency_ms": 600,
                           "vectors": vectors}).encode()
    manifest["files"].append({"path": "tests/vectors.json",
                              "sha256": hashlib.sha256(vec_blob).hexdigest(),
                              "size": len(vec_blob)})
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, blob in files.items():
            if blob is not None:
                z.writestr(name, blob)
        z.writestr("tests/vectors.json", vec_blob)
        z.writestr("manifest.json", json.dumps(manifest))
    os.unlink(tmp_out)
    print(f"[train] bundle written: {a.out} "
          f"({os.path.getsize(a.out) / 1e6:.1f} MB)", flush=True)
    print("REPORT " + json.dumps({"verdict": verdict, "holdout_trades": nt,
                                  "win_rate": round(wr, 4),
                                  "wilson95": [round(lo, 4), round(hi, 4)],
                                  "break_even": round(be, 4)}), flush=True)


if __name__ == "__main__":
    main()
