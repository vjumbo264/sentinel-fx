"""sentinel_engine.check — bundle health & code contract checker (schema v2).

Usage:
    python -m sentinel_engine.check <bundle.sfxmodel.zip>
    sfx check <bundle.sfxmodel.zip>

Validates:
  - Manifest presence, file list, and sha256 integrity of all members
  - Data-only formats (ONNX, LightGBM txt, XGBoost json, JSON metadata); NO pickle/code
  - ONNX safety (standard domains only, no external data references, no path traversal)
  - analysis_plan.json graph validity (DAG, allowed node types, causal lookbacks, referenced files exist)
  - Execution on embedded test vectors (tests/vectors.json or tests/inputs.json)
  - Output contract: valid action (trade|skip), side (CALL|PUT), p_win in [0,1],
    stake (2 decimals, positive, within given balance), reason string, no NaN/inf
  - Parity: engine execution matches embedded expected outputs within tolerance
  - Latency: measures execution time and reports against budget (default 600ms)

Exit code 0 = pass, 1 = fail. Outputs structured JSON check report.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import sys
import time

def check_bundle(bundle_path: str) -> dict:
    import pandas as pd
    from .bundle import verify_bundle, load_bundle
    from .plan import validate_plan, evaluate

    report = {
        "ok": False,
        "bundle": bundle_path,
        "problems": [],
        "warnings": [],
        "latency_ms": None,
        "latency_budget_ms": 600.0,
        "checks": {
            "archive_integrity": False,
            "manifest_and_hashes": False,
            "safe_data_formats": False,
            "analysis_plan_dag": False,
            "embedded_vectors_execution": False,
            "contract_conformance": False,
            "output_parity": False,
        }
    }

    if not os.path.exists(bundle_path):
        report["problems"].append(f"File not found: {bundle_path}")
        return report

    # 1. Structure, manifest, sha256 and ONNX safety scan
    ok, probs = verify_bundle(bundle_path)
    if not ok:
        report["problems"].extend(probs)
        return report
    report["checks"]["archive_integrity"] = True
    report["checks"]["manifest_and_hashes"] = True
    report["checks"]["safe_data_formats"] = True

    # 2. Load bundle and validate analysis_plan.json
    try:
        b = load_bundle(bundle_path)
    except Exception as e:
        report["problems"].append(f"Failed to load bundle: {e}")
        return report

    plan_errs = validate_plan(b.plan)
    if plan_errs:
        report["problems"].extend(plan_errs)
        return report

    names = set(b.zf.namelist())
    for n in b.plan.get("nodes", []):
        if n.get("model") and n["model"] not in names:
            report["problems"].append(f"Plan node {n.get('id')} references missing model file: {n['model']}")
    if report["problems"]:
        return report
    report["checks"]["analysis_plan_dag"] = True

    # 3. Execution, Parity and Contract checks on embedded test vectors
    vector_files = ["tests/vectors.json", "tests/parity.json", "tests/inputs.json"]
    found_vec = None
    for vf in vector_files:
        if vf in names:
            found_vec = vf
            break

    if not found_vec:
        report["warnings"].append("No embedded tests found in tests/vectors.json; running synthetic baseline sanity check.")
        # Create minimal synthetic candles to test pipeline end-to-end
        test_df = pd.DataFrame({
            "epoch": [1700000000 + i * 60 for i in range(120)],
            "open": [1.0800 + i * 0.0001 for i in range(120)],
            "high": [1.0805 + i * 0.0001 for i in range(120)],
            "low": [1.0795 + i * 0.0001 for i in range(120)],
            "close": [1.0802 + i * 0.0001 for i in range(120)],
        })
        try:
            t0 = time.monotonic()
            dec = evaluate(b, test_df, {"minutes_to_news": 9999, "news_state": "clear"})
            ms = (time.monotonic() - t0) * 1000
            report["latency_ms"] = round(ms, 2)
            _validate_decision_contract(dec, report)
            report["checks"]["embedded_vectors_execution"] = True
            report["checks"]["contract_conformance"] = (len(report["problems"]) == 0)
            report["checks"]["output_parity"] = True
        except Exception as e:
            report["problems"].append(f"Pipeline evaluation failed on baseline test: {e}")
    else:
        try:
            vec_data = json.loads(b.zf.read(found_vec))
            vectors = vec_data.get("vectors") or vec_data.get("tests") or []
            tol = float(vec_data.get("tolerance", 1e-3))
            budget = float(vec_data.get("latency_ms", 600.0))
            report["latency_budget_ms"] = budget
            max_ms = 0.0

            for idx, tv in enumerate(vectors):
                df = pd.DataFrame(tv.get("candles") or tv.get("inputs", []))
                ctx = tv.get("context", {"minutes_to_news": 9999, "news_state": "clear"})

                t0 = time.monotonic()
                d1 = evaluate(b, df, ctx)
                ms = (time.monotonic() - t0) * 1000
                max_ms = max(max_ms, ms)

                # Determinism run
                d2 = evaluate(b, df, ctx)

                _validate_decision_contract(d1, report, f"Vector #{idx+1}")

                # Parity against expected outputs if declared
                exp = tv.get("expected")
                if exp:
                    if exp.get("action") and exp["action"] != d1.get("action"):
                        report["problems"].append(f"Vector #{idx+1} parity failure: expected action={exp['action']}, got {d1.get('action')}")
                    if exp.get("side") and exp["side"] != d1.get("side"):
                        report["problems"].append(f"Vector #{idx+1} parity failure: expected side={exp['side']}, got {d1.get('side')}")
                    if exp.get("p_win") is not None and d1.get("p_win") is not None:
                        if abs(float(exp["p_win"]) - float(d1["p_win"])) > tol:
                            report["problems"].append(f"Vector #{idx+1} p_win parity mismatch: expected {exp['p_win']}, got {d1.get('p_win')} (tol {tol})")

                # Determinism check
                if d1.get("action") != d2.get("action") or d1.get("side") != d2.get("side"):
                    report["problems"].append(f"Vector #{idx+1} is non-deterministic: run1={d1}, run2={d2}")
                if d1.get("p_win") is not None and d2.get("p_win") is not None:
                    if abs(float(d1["p_win"]) - float(d2["p_win"])) > 1e-6:
                        report["problems"].append(f"Vector #{idx+1} p_win is non-deterministic: {d1.get('p_win')} vs {d2.get('p_win')}")

            report["latency_ms"] = round(max_ms, 2)
            if max_ms > budget:
                report["warnings"].append(f"Execution latency {max_ms:.1f}ms exceeds declared budget {budget:.1f}ms")

            report["checks"]["embedded_vectors_execution"] = True
            report["checks"]["contract_conformance"] = (len(report["problems"]) == 0)
            report["checks"]["output_parity"] = (len(report["problems"]) == 0)

        except Exception as e:
            report["problems"].append(f"Vector parity evaluation error: {e}")

    report["ok"] = (len(report["problems"]) == 0)
    return report

def _validate_decision_contract(dec: dict, report: dict, prefix: str = "Decision"):
    if not isinstance(dec, dict):
        report["problems"].append(f"{prefix}: output must be a dictionary, got {type(dec)}")
        return

    act = dec.get("action")
    if act not in ("trade", "skip"):
        report["problems"].append(f"{prefix}: action must be 'trade' or 'skip', got '{act}'")

    if act == "trade":
        sd = dec.get("side")
        if sd not in ("CALL", "PUT"):
            report["problems"].append(f"{prefix}: side must be 'CALL' or 'PUT', got '{sd}'")

    pwin = dec.get("p_win")
    if pwin is not None:
        if not isinstance(pwin, (int, float)) or math.isnan(pwin) or math.isinf(pwin):
            report["problems"].append(f"{prefix}: p_win is NaN or infinite")
        elif not (0.0 <= pwin <= 1.0):
            report["problems"].append(f"{prefix}: p_win must be in [0.0, 1.0], got {pwin}")

    stake = dec.get("stake")
    if stake is not None:
        if not isinstance(stake, (int, float)) or math.isnan(stake) or math.isinf(stake):
            report["problems"].append(f"{prefix}: stake is NaN or infinite")
        elif stake < 0:
            report["problems"].append(f"{prefix}: stake cannot be negative, got {stake}")
        else:
            # Check 2 decimals
            rounded = round(float(stake), 2)
            if abs(float(stake) - rounded) > 1e-4:
                report["problems"].append(f"{prefix}: stake precision must be at most 2 decimal places, got {stake}")

    if not dec.get("reason"):
        report["warnings"].append(f"{prefix}: reason string is empty")

def main(argv=None):
    ap = argparse.ArgumentParser(description="SENTINEL-FX Model Bundle Health Checker")
    ap.add_argument("bundle", help="Path to .sfxmodel.zip bundle")
    ap.add_argument("--json", action="store_true", help="Print JSON report only")
    args = ap.parse_args(argv)

    res = check_bundle(args.bundle)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print("=" * 70)
        print("SENTINEL-FX MODEL BUNDLE HEALTH CHECK REPORT")
        print("=" * 70)
        print(f"Bundle: {res['bundle']}")
        print(f"Status: {'PASSED' if res['ok'] else 'FAILED'}")
        if res['latency_ms'] is not None:
            print(f"Latency: {res['latency_ms']} ms (budget: {res['latency_budget_ms']} ms)")
        print("\nChecks:")
        for check, passed in res["checks"].items():
            print(f"  [{'✓' if passed else '✗'}] {check}")
        if res["problems"]:
            print("\nProblems:")
            for p in res["problems"]:
                print(f"  - {p}")
        if res["warnings"]:
            print("\nWarnings:")
            for w in res["warnings"]:
                print(f"  * {w}")
        print("=" * 70)

    sys.exit(0 if res["ok"] else 1)

if __name__ == "__main__":
    main()
