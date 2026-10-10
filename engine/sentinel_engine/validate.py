"""
sentinel_engine.validate
========================
Pair-pack validator. Modes:
  fast: checks 1-3 + 10 (pure schema/static; runs anywhere)
  full: all checks (needs numpy/pandas/lightgbm per pack model type; sandbox
        for custom code, fails closed if isolation unavailable)
Prints a machine-readable JSON report + human summary; exit non-zero on failure.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
import time

import numpy as np
import pandas as pd

from .dsl import ENGINE_VERSION, compute_features, validate_dsl
from .models import load_model
from .news import pair_currencies
from .pack import (MAX_PACK_BYTES, SYMBOL_RE, Pack, decode_b64gz, pack_checksum,
                   test_candles)
from . import rules as _rules
from . import sandbox as _sandbox

MIN_STAKE_FLOOR = 0.35
MIN_OOS_TRADES = 60
IMPLAUSIBLE_WIN_RATE = 0.65
BANNED_TOKENS = ["os", "sys", "subprocess", "socket", "open", "eval", "exec",
                 "__import__", "ctypes", "importlib", "urllib", "requests",
                 "shutil", "pathlib", "builtins", "globals", "locals",
                 "getattr", "setattr", "delattr", "compile", "input",
                 "breakpoint", "exit", "quit", "help", "vars", "dir"]
ALLOWED_IMPORTS = {"numpy", "pandas", "math", "scipy", "np", "pd"}


def _ver_tuple(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


class Report:
    def __init__(self, mode: str):
        self.mode = mode
        self.checks: list[dict] = []

    def add(self, name: str, status: str, detail: str = ""):
        assert status in ("pass", "fail", "warn", "skip")
        self.checks.append({"check": name, "status": status, "detail": detail})

    @property
    def ok(self) -> bool:
        return all(c["status"] != "fail" for c in self.checks)

    def to_json(self) -> str:
        return json.dumps({"mode": self.mode, "ok": self.ok, "checks": self.checks},
                          indent=1)


def validate(path: str, mode: str = "full") -> Report:
    rep = Report(mode)
    raw_bytes = open(path, "rb").read()
    if len(raw_bytes) > MAX_PACK_BYTES:
        rep.add("size", "fail", f"{len(raw_bytes)} bytes > {MAX_PACK_BYTES}")
        return rep
    rep.add("size", "pass", f"{len(raw_bytes)} bytes")
    try:
        pack = json.loads(raw_bytes.decode("utf8"))
    except Exception as e:
        rep.add("schema", "fail", f"invalid JSON: {e}")
        return rep

    # ---- 1. schema / types / ranges / checksum
    try:
        _check_schema(pack, rep)
    except Exception as e:
        rep.add("schema", "fail", f"exception: {e}")
        return rep

    # checksum
    try:
        if pack.get("checksum_sha256") == pack_checksum(pack):
            rep.add("checksum", "pass")
        else:
            rep.add("checksum", "fail", "checksum_sha256 does not match canonical body")
    except Exception as e:
        rep.add("checksum", "fail", f"checksum error: {e}")

    # ---- 2. engine compatibility
    try:
        _check_engine_compat(pack, rep)
    except Exception as e:
        rep.add("engine_compat", "fail", f"exception: {e}")

    # ---- 3. custom-module static scan + sha256
    try:
        _check_custom_static(pack, rep)
    except Exception as e:
        rep.add("custom_static", "fail", f"exception: {e}")

    # ---- 10. backtest consistency (fast-mode safe)
    try:
        _check_backtest(pack, rep)
    except Exception as e:
        rep.add("backtest_consistency", "fail", f"exception: {e}")

    if mode == "fast":
        return rep

    # ===== full mode =====
    candles = test_candles(pack)
    if not candles:
        rep.add("test_vectors", "fail", "tests.candles_b64gz missing/empty")
        return rep
    df = pd.DataFrame(candles)
    for col in ("epoch", "open", "high", "low", "close"):
        if col not in df.columns:
            rep.add("test_vectors", "fail", f"test candles missing column {col}")
            return rep

    # ---- 4. causality / no-leakage
    try:
        _check_causality(pack, df, rep)
    except Exception as e:
        rep.add("causality", "fail", f"exception: {e}")

    # ---- 5. reproducibility
    try:
        _check_repro(pack, df, rep)
    except Exception as e:
        rep.add("reproducibility", "fail", f"exception: {e}")

    # ---- 6. determinism
    try:
        _check_determinism(pack, df, rep)
    except Exception as e:
        rep.add("determinism", "fail", f"exception: {e}")

    # ---- 7. sandbox run for custom code
    try:
        _check_sandbox(pack, df, rep)
    except Exception as e:
        rep.add("sandbox_run", "fail", f"exception: {e}")

    # ---- 8. performance
    try:
        _check_perf(pack, df, rep)
    except Exception as e:
        rep.add("performance", "fail", f"exception: {e}")

    # ---- 9. output sanity
    try:
        _check_sanity(pack, df, rep)
    except Exception as e:
        rep.add("output_sanity", "fail", f"exception: {e}")

    return rep


# ------------------------------------------------------------------ checks
def _check_schema(pack: dict, rep: Report):
    req = ["schema_version", "symbol", "pack_version", "created_utc",
           "min_engine_version", "features", "model", "rules", "decision",
           "risk", "backtest", "tests", "checksum_sha256"]
    missing = [k for k in req if k not in pack]
    if missing:
        rep.add("schema", "fail", f"missing keys {missing}")
        return
    if not re.match(SYMBOL_RE, pack.get("symbol", "")):
        rep.add("schema", "fail", f"symbol '{pack.get('symbol')}' fails {SYMBOL_RE}")
        return
    if int(pack.get("schema_version", 0)) != 1:
        rep.add("schema", "fail", "schema_version must be 1")
        return
    if int(pack.get("pack_version", 0)) < 1:
        rep.add("schema", "fail", "pack_version must be >= 1")
        return
    risk = pack.get("risk", {})
    sp = float(risk.get("stake_pct", 0))
    if not (0 < sp <= 0.10):
        rep.add("schema", "fail", f"stake_pct {sp} out of (0, 0.10]")
        return
    dec = pack.get("decision", {})
    pa = float(dec.get("payout_assumed", 0))
    if not (0.5 <= pa <= 1.0):
        rep.add("schema", "fail", f"payout_assumed {pa} out of [0.5, 1.0]")
        return
    if float(dec.get("margin", 0)) < 0:
        rep.add("schema", "fail", "margin must be >= 0")
        return
    sym = str(pack.get("symbol", ""))
    is_fx = sym.startswith("frx")
    h_min = int(dec.get("horizon_min", 0) or 0)
    dur = int(dec.get("duration", 0) or 0)
    if is_fx:
        if h_min != 15 and dur != 15:
            rep.add("schema", "fail", "horizon_min must be 15 for forex (Deriv forex minimum)")
    else:
        h_sec = int(dec.get("horizon_sec", 0) or 0)
        dur_u = dec.get("duration_unit", "m")
        total_s = h_sec or (h_min * 60) or (dur * 60 if dur_u == "m" else dur)
        if total_s < 5:
            rep.add("schema", "fail", "synthetic duration must be at least 5 seconds")
        return
    if float(risk.get("max_stake_suggested", 0)) < MIN_STAKE_FLOOR:
        rep.add("schema", "fail", f"max_stake_suggest below {MIN_STAKE_FLOOR}")
        return
    rep.add("schema", "pass")


def _check_engine_compat(pack: dict, rep: Report):
    if _ver_tuple(pack.get("min_engine_version", "999")) > _ver_tuple(ENGINE_VERSION):
        rep.add("engine_compat", "fail",
                f"needs engine >= {pack['min_engine_version']}, have {ENGINE_VERSION}")
        return
    problems = validate_dsl(pack.get("features", {}).get("dsl", []))
    if problems:
        rep.add("engine_compat", "fail", "; ".join(problems[:8]))
        return
    if pack["model"].get("type") not in ("lightgbm_text", "tree_json", "logreg_json"):
        rep.add("engine_compat", "fail", f"unknown model type {pack['model'].get('type')}")
        return
    in_feats = pack["model"].get("input_features", [])
    dsl_ids = {n.get("id") for n in pack.get("features", {}).get("dsl", [])}
    custom_cols = set()
    for m in pack.get("features", {}).get("custom_modules", []):
        # custom outputs are prefixed "<name>__"; we can't know names statically,
        # so require input features not in DSL to carry that prefix pattern
        custom_cols.add(m.get("name", "") + "__")
    missing = [f for f in in_feats
               if f not in dsl_ids and not any(f.startswith(p) for p in custom_cols)]
    if missing:
        rep.add("engine_compat", "fail", f"model inputs not produced by DSL/custom: {missing}")
        return
    rep.add("engine_compat", "pass")


def _check_custom_static(pack: dict, rep: Report):
    mods = pack.get("features", {}).get("custom_modules", [])
    if not mods:
        rep.add("custom_static", "pass", "no custom code")
        return
    for m in mods:
        try:
            code = decode_b64gz(m["code_b64gz"]).decode("utf8")
        except Exception as e:
            rep.add("custom_static", "fail", f"{m.get('name')}: decode error {e}")
            return
        if hashlib.sha256(code.encode("utf8")).hexdigest() != m.get("sha256"):
            rep.add("custom_static", "fail", f"{m.get('name')}: sha256 mismatch")
            return
        if len(code.encode()) > 64 * 1024:
            rep.add("custom_static", "fail", f"{m.get('name')}: exceeds 64KB module cap")
            return
        for tok in BANNED_TOKENS:
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(tok)}(?![A-Za-z0-9_])", code):
                rep.add("custom_static", "fail",
                        f"{m.get('name')}: banned token '{tok}' in source")
                return
        for mline in re.finditer(r"^\s*(?:import|from)\s+([A-Za-z0-9_.]+)", code, re.M):
            root = mline.group(1).split(".")[0]
            if root not in ALLOWED_IMPORTS:
                rep.add("custom_static", "fail",
                        f"{m.get('name')}: non-whitelisted import '{mline.group(1)}'")
                return
        if not re.search(r"def\s+compute\s*\(", code):
            rep.add("custom_static", "fail", f"{m.get('name')}: no compute() entrypoint")
            return
    rep.add("custom_static", "pass", f"{len(mods)} module(s) clean")


def _check_backtest(pack: dict, rep: Report):
    bt = pack.get("backtest", {})
    payout = float(pack.get("decision", {}).get("payout_assumed", 0.85))
    be = 1.0 / (1.0 + payout)
    wr = float(bt.get("win_rate", 0.0))
    n = int(bt.get("oos_trades", 0))
    verdict = bt.get("verdict", "")
    if abs(float(bt.get("break_even_win_rate", 0)) - be) > 0.01:
        rep.add("backtest_consistency", "fail",
                f"break_even_win_rate {bt.get('break_even_win_rate')} != 1/(1+{payout})={be:.4f}")
        return
    if n < MIN_OOS_TRADES:
        rep.add("backtest_consistency", "fail", f"oos_trades {n} < {MIN_OOS_TRADES}")
        return
    expected = "pass" if wr > be + float(pack.get("decision", {}).get("margin", 0)) else "fail"
    if verdict != expected:
        rep.add("backtest_consistency", "fail",
                f"verdict '{verdict}' inconsistent with wr={wr:.4f} vs be={be:.4f}")
        return
    if float(bt.get("max_drawdown_pct", 100)) > 50:
        rep.add("backtest_consistency", "fail", "max_drawdown_pct > 50")
        return
    if wr > IMPLAUSIBLE_WIN_RATE:
        rep.add("backtest_consistency", "warn",
                f"win rate {wr:.3f} implausibly high for 15m forex binaries — probable leakage")
    else:
        rep.add("backtest_consistency", "pass",
                f"wr={wr:.4f} vs be={be:.4f}, n={n}, verdict={verdict}")


def _feats_and_probs(pack: dict, df: pd.DataFrame):
    p = Pack(pack)
    feats = p.compute_features(df)
    probs = p.predict_proba(feats)
    return feats, probs


def _check_causality(pack: dict, df: pd.DataFrame, rep: Report):
    n = len(df)
    if n < 120:
        rep.add("causality", "fail", "need >= 120 test candles")
        return
    full = Pack(pack).compute_features(df)
    cuts = [int(n * f) for f in (0.4, 0.55, 0.7, 0.85)]
    bad = []
    for c in cuts:
        part = Pack(pack).compute_features(df.iloc[:c])
        a = full.iloc[c - 1]
        b = part.iloc[-1]
        for col in full.columns:
            va, vb = a[col], b[col]
            if pd.isna(va) and pd.isna(vb):
                continue
            if not np.isclose(va, vb, rtol=0, atol=1e-9, equal_nan=True):
                bad.append(f"{col}@{c}")
                break
    if bad:
        rep.add("causality", "fail", f"non-causal features at cuts: {bad[:5]}")
    else:
        rep.add("causality", "pass", f"verified at cuts {cuts}")


def _check_repro(pack: dict, df: pd.DataFrame, rep: Report):
    tests = pack.get("tests", {})
    tol = float(tests.get("tolerance", 1e-6))
    feats, probs = _feats_and_probs(pack, df)
    idxs = tests.get("check_indices", [])
    expf = tests.get("expected_features", {})
    expp = tests.get("expected_probs", [])
    if not idxs or not expf or not expp:
        rep.add("reproducibility", "fail", "missing check_indices/expected_features/expected_probs")
        return
    for i in idxs:
        for name, val in expf.get(str(i), {}).items():
            got = float(feats[name].iloc[i])
            if not np.isclose(got, float(val), rtol=0, atol=tol, equal_nan=True):
                rep.add("reproducibility", "fail",
                        f"feature {name}@{i}: got {got} expected {val}")
                return
    for j, i in enumerate(idxs):
        got = float(probs[i])
        if not np.isclose(got, float(expp[j]), rtol=0, atol=tol):
            rep.add("reproducibility", "fail",
                    f"prob@{i}: got {got} expected {expp[j]}")
            return
    rep.add("reproducibility", "pass", f"{len(idxs)} indices reproduced within {tol}")


def _check_determinism(pack: dict, df: pd.DataFrame, rep: Report):
    _, p1 = _feats_and_probs(pack, df)
    _, p2 = _feats_and_probs(pack, df)
    if np.allclose(p1, p2, rtol=0, atol=0):
        rep.add("determinism", "pass")
    else:
        rep.add("determinism", "fail", "two runs differ")


def _check_sandbox(pack: dict, df: pd.DataFrame, rep: Report):
    mods = pack.get("features", {}).get("custom_modules", [])
    if not mods:
        rep.add("sandbox_run", "skip", "no custom code")
        return
    if not _sandbox.sandbox_available():
        rep.add("sandbox_run", "fail",
                "sandbox isolation unavailable (fail closed): cannot verify custom code")
        return
    candles = df[["epoch", "open", "high", "low", "close"]].tail(300).to_dict("records")
    for m in mods:
        code = decode_b64gz(m["code_b64gz"]).decode("utf8")
        res = _sandbox.run_module(code, candles, m.get("params", {}), cpu_s=15, wall_s=25)
        if not res.get("ok"):
            rep.add("sandbox_run", "fail", f"{m['name']}: {res.get('error')}")
            return
    rep.add("sandbox_run", "pass", f"{len(mods)} module(s) ran clean in isolated sandbox")


def _check_perf(pack: dict, df: pd.DataFrame, rep: Report):
    p = Pack(pack)
    t0 = time.perf_counter()
    feats = p.compute_features(df.tail(500))
    p.predict_proba(feats)
    dt = time.perf_counter() - t0
    if dt > 2.0:
        rep.add("performance", "fail", f"single inference {dt:.2f}s > 2s")
    else:
        rep.add("performance", "pass", f"{dt*1000:.0f} ms")


def _check_sanity(pack: dict, df: pd.DataFrame, rep: Report):
    _, probs = _feats_and_probs(pack, df)
    if not np.isfinite(probs).all():
        rep.add("output_sanity", "fail", "NaN/inf probabilities")
        return
    if probs.min() < 0 or probs.max() > 1:
        rep.add("output_sanity", "fail", f"probs outside [0,1]: [{probs.min()}, {probs.max()}]")
        return
    if float(probs.std()) < 1e-9:
        rep.add("output_sanity", "fail", "constant probabilities")
        return
    rp = _rules.validate_rules(pack.get("rules", {}))
    if rp:
        rep.add("output_sanity", "fail", "rule tree: " + "; ".join(rp[:5]))
        return
    rep.add("output_sanity", "pass",
            f"prob range [{probs.min():.3f}, {probs.max():.3f}]")


def main(argv=None):
    ap = argparse.ArgumentParser(description="SENTINEL-FX pair-pack validator")
    ap.add_argument("pack")
    ap.add_argument("--mode", choices=["fast", "full"], default="full")
    args = ap.parse_args(argv)
    rep = validate(args.pack, args.mode)
    print(rep.to_json())
    print()
    for c in rep.checks:
        icon = {"pass": "PASS", "fail": "FAIL", "warn": "WARN", "skip": "SKIP"}[c["status"]]
        line = f"[{icon}] {c['check']}"
        if c["detail"]:
            line += f" — {c['detail']}"
        print(line)
    print(f"\nOverall: {'PASS' if rep.ok else 'FAIL'} ({rep.mode} mode)")
    sys.exit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
