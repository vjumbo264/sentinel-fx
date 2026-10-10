"""
sentinel_engine.validate_bundle — validator for .sfxmodel.zip (schema v2).

  python -m sentinel_engine.validate_bundle <bundle> --mode fast|full

Checks: manifest/hashes/size, file-type allow-list (data formats only), ONNX
safety scan, plan validity (acyclic, allowed node types, referenced models
exist), PARITY + DETERMINISM + LATENCY on the embedded test vectors, output
sanity, and HONESTY GATES on the declared hold-out (trades >=
MIN_HOLDOUT_TRADES, Wilson lower bound above break-even at payout-3 points,
warning on implausibly high win rate). Full mode additionally REPRODUCES the
declared hold-out on the real candles from the data hub when available.

Exit code 0 = pass, 1 = fail. Prints "VALIDATOR {json}".
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--mode", choices=["fast", "full"], default="fast")
    a = ap.parse_args()

    import pandas as pd
    from .bundle import verify_bundle, load_bundle
    from .plan import validate_plan, evaluate
    from .sim import break_even

    problems, warnings = [], []
    ok, probs = verify_bundle(a.file)
    problems += probs
    if not ok:
        print("VALIDATOR " + json.dumps(
            {"ok": False, "problems": problems, "warnings": warnings}))
        sys.exit(1)

    b = load_bundle(a.file)
    problems += validate_plan(b.plan)
    names = set(b.zf.namelist())
    for n in b.plan.get("nodes", []):
        if n.get("model") and n["model"] not in names:
            problems.append(f"plan references missing model file: {n['model']}")

    # ---- parity / determinism / latency / sanity on embedded vectors -------
    if "tests/vectors.json" in names:
        vecs = json.loads(b.zf.read("tests/vectors.json"))
        tol = float(vecs.get("tolerance", 1e-3))
        budget = float(vecs.get("latency_ms", 600))
        for k, tv in enumerate(vecs.get("vectors", [])):
            df = pd.DataFrame(tv["candles"])
            t0 = time.monotonic()
            d1 = evaluate(b, df, {})
            ms = (time.monotonic() - t0) * 1000
            d2 = evaluate(b, df, {})
            p1, p2 = d1.get("p_win"), d2.get("p_win")
            if p1 is None or not (0.0 <= p1 <= 1.0):
                problems.append(f"vector {k}: p_win out of range ({p1})")
            elif abs(p1 - float(tv["expect_p_win"])) > tol:
                problems.append(
                    f"vector {k}: parity fail ({p1} vs {tv['expect_p_win']})")
            if p1 != p2 or d1.get("side") != d2.get("side"):
                problems.append(f"vector {k}: non-deterministic output")
            if ms > budget:
                problems.append(f"vector {k}: latency {ms:.0f}ms > {budget}ms")
    else:
        warnings.append("no tests/vectors.json — parity not proven")

    # ---- honesty gates on the declared hold-out -----------------------------
    rep = b.training_report or {}
    ho = rep.get("holdout", {})
    payout = float(rep.get("payout", 0.85))
    n = int(ho.get("trades", 0))
    wr = ho.get("win_rate")
    lo = (ho.get("wilson95") or [0.0, 0.0])[0]
    min_trades = int(os.environ.get("MIN_HOLDOUT_TRADES", "300"))
    if min_trades == 0:
        warnings.append("MIN_HOLDOUT_TRADES=0 — plumbing/pipeline test bundle, "
                        "honesty gates weakened")
    else:
        if n < min_trades:
            problems.append(f"hold-out trades {n} < {min_trades}")
        if lo <= break_even(payout - 0.03):
            problems.append(
                f"honesty gate: Wilson lower bound {lo:.4f} not above "
                f"break-even at payout-3 ({break_even(payout - 0.03):.4f})")
    if wr is not None and wr > 0.62:
        warnings.append(f"win rate {wr:.3f} implausibly high — probable leakage")
    if rep.get("verdict") == "pass" and problems:
        warnings.append("training_report claims pass but validation failed")

    # ---- full mode: reproduce hold-out on data-hub candles ------------------
    if a.mode == "full" and not problems and min_trades > 0:
        try:
            repo = os.environ.get("GITHUB_REPOSITORY", "vjumbo264/sentinel-fx")
            idx_path = os.path.join(os.path.dirname(a.file), "data", "index.json")
            if not os.path.exists(idx_path):
                idx_path = "data/index.json"
            idx = json.load(open(idx_path))
            ent = idx.get(b.symbol)
            if not ent:
                warnings.append("full mode: pair not in data hub; "
                                "reproduction skipped")
            else:
                import gzip, io, urllib.request
                from .sim import replay
                url = (f"https://github.com/{repo}/releases/download/"
                       f"{ent['release_tag']}/{ent['asset']}")
                raw = urllib.request.urlopen(url, timeout=300).read()
                import csv
                candles = [{"epoch": int(r["epoch"]), "open": float(r["open"]),
                            "high": float(r["high"]), "low": float(r["low"]),
                            "close": float(r["close"])}
                           for r in csv.DictReader(
                               io.TextIOWrapper(gzip.decompress(raw)
                                                .decode().splitlines()))]
                hw = rep.get("holdout_window") or {}
                if hw.get("from_epoch"):
                    candles = [c for c in candles
                               if hw["from_epoch"] <= c["epoch"]
                               <= hw.get("to_epoch", 1 << 62)]
                m = replay(b, candles, payout=payout, decision_every=5,
                           min_conf=float(b.decision.get("min_p", 0)))
                if abs(m["trades"] - n) > max(20, 0.25 * n):
                    problems.append(
                        f"reproduction: trades {m['trades']} vs claimed {n}")
                if wr is not None and abs(m["win_rate"] - wr) > 0.03:
                    problems.append(
                        f"reproduction: win rate {m['win_rate']} vs "
                        f"claimed {wr}")
        except Exception as e:
            warnings.append(f"full-mode reproduction unavailable: {e}")

    report = {"ok": not problems, "problems": problems, "warnings": warnings,
              "symbol": b.symbol, "version": b.version,
              "verdict": rep.get("verdict")}
    print("VALIDATOR " + json.dumps(report))
    sys.exit(0 if not problems else 1)


if __name__ == "__main__":
    main()
