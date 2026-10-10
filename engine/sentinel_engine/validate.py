"""Pack validator. Fast mode: checks 1-3,10 (pure static). Full mode: all 10 checks.
Prints machine-readable JSON report + human summary. Exit non-zero on any FAILURE."""
import argparse, base64, gzip, hashlib, json, sys, time
import numpy as np

SIZE_LIMIT = 25 * 1024 * 1024
MIN_STAKE_FLOOR = 0.35

def _r(checks, name, status, detail=""):
    checks.append({"check": name, "status": status, "detail": detail})

def validate_pack(pack: dict, raw_bytes: bytes, mode: str = "full") -> dict:
    checks = []
    full = mode == "full"

    # ---- 1. schema / types / checksum / ranges ----
    try:
        assert pack.get("schema_version") == 1, "schema_version must be 1"
        import re
        assert re.fullmatch(r"frx[A-Z]{6}", pack.get("symbol", "")), "symbol must match ^frx[A-Z]{6}$"
        assert isinstance(pack.get("pack_version"), int) and pack["pack_version"] >= 1
        assert len(raw_bytes) <= SIZE_LIMIT, "pack exceeds 25MB"
        from . import checksum
        assert checksum.verify_checksum(pack), "checksum_sha256 mismatch"
        risk = pack.get("risk", {})
        for k in ("stake_pct", "daily_loss_pct", "daily_target_pct"):
            if k in risk and risk[k]:
                assert 0 <= float(risk[k]) <= 1, f"risk.{k} out of range"
        dec = pack.get("decision", {})
        assert 0 <= float(dec.get("margin", 0)) <= 0.5
        assert 0 < float(dec.get("payout_assumed", 0.85)) < 5
        _r(checks, "schema", "pass", f"symbol={pack['symbol']} v{pack['pack_version']} {len(raw_bytes)//1024}KB checksum ok")
    except AssertionError as e:
        _r(checks, "schema", "fail", str(e))

    # ---- 2. engine compatibility ----
    try:
        from . import __version__
        from .dsl import SUPPORTED_OPS
        req = pack.get("min_engine_version", "1.0.0")
        assert tuple(map(int, req.split("."))) <= tuple(map(int, __version__.split("."))), f"needs engine {req} > {__version__}"
        bad = [n.get("op") for n in pack.get("features", {}).get("dsl", []) if n.get("op") not in SUPPORTED_OPS]
        assert not bad, f"unsupported DSL ops: {bad}"
        assert pack.get("model", {}).get("type") in ("lightgbm_text", "tree_json", "logreg_json")
        _r(checks, "engine_compat", "pass", f"engine {__version__} >= {req}")
    except AssertionError as e:
        _r(checks, "engine_compat", "fail", str(e))

    # ---- 3. static scan + module hashes ----
    try:
        from .static_scan import scan_module
        for m in pack.get("features", {}).get("custom_modules", []):
            raw = gzip.decompress(base64.b64decode(m["code_b64gz"]))
            assert hashlib.sha256(raw).hexdigest() == m["sha256"], f"module {m['name']} sha256 mismatch"
            findings = scan_module(m["code_b64gz"])
            assert not findings, f"module {m['name']}: {findings}"
        _r(checks, "static_scan", "pass", f"{len(pack.get('features',{}).get('custom_modules',[]))} custom modules clean")
    except AssertionError as e:
        _r(checks, "static_scan", "fail", str(e))

    # ---- 10. backtest consistency (fast + full) ----
    try:
        bt = pack.get("backtest", {})
        be = 1.0 / (1.0 + float(pack.get("decision", {}).get("payout_assumed", 0.85)))
        wr = float(bt.get("win_rate", 0.0))
        assert abs(float(bt.get("break_even_win_rate", be)) - be) < 0.01, "break_even mismatch"
        if bt.get("verdict") == "pass":
            assert wr > be + 0.005, f"verdict=pass but win_rate {wr:.4f} not above break-even {be:.4f} + margin"
            assert int(bt.get("oos_trades", 0)) >= 100, "too few OOS trades for a pass verdict"
        _r(checks, "backtest_consistency", "pass", f"wr={wr:.4f} be={be:.4f} verdict={bt.get('verdict')}")
        if bt.get("verdict") == "pass" and wr > 0.65:
            _r(checks, "plausibility", "warn", f"win_rate {wr:.1%} implausibly high for 15m forex binaries - probable leakage")
    except AssertionError as e:
        _r(checks, "backtest_consistency", "fail", str(e))

    if full:
        try:
            _full_checks(pack, checks)
        except Exception as e:
            _r(checks, "full_mode_error", "fail", f"{type(e).__name__}: {e}")

    verdict = "fail" if any(c["status"] == "fail" for c in checks) else \
              ("warn" if any(c["status"] == "warn" for c in checks) else "pass")
    return {"verdict": verdict, "mode": mode, "symbol": pack.get("symbol"), "checks": checks}

def _full_checks(pack, checks):
    import pandas as pd
    from .dsl import compute_features
    from .models import load_model
    from .rules import validate_rules

    tests = pack.get("tests", {})
    candles = json.loads(gzip.decompress(base64.b64decode(tests["candles_b64gz"])).decode())
    assert len(candles) >= 50, "embedded test candles too small"

    # 4. causality: features at cut indices identical between full and truncated series
    full_f = compute_features(pack["features"]["dsl"], candles)
    cuts = [int(len(candles) * f) for f in (0.4, 0.55, 0.7, 0.85)]
    for c in cuts:
        trunc = compute_features(pack["features"]["dsl"], candles[:c + 1])
        a, b = full_f.iloc[c], trunc.iloc[-1]
        both = pd.concat([a, b], axis=1).dropna()
        if len(both) and not np.allclose(both.iloc[:, 0], both.iloc[:, 1], atol=1e-9, equal_nan=True):
            bad = both[~np.isclose(both.iloc[:, 0], both.iloc[:, 1], atol=1e-9)].index.tolist()
            raise AssertionError(f"causality: features {bad} differ at cut {c} (future leakage)")
    _r(checks, "causality", "pass", f"{len(cuts)} truncation cuts, features identical")

    # 5. reproducibility on embedded test vectors
    model = load_model(pack["model"])
    idxs = tests.get("check_indices", [])
    exp_f, exp_p = tests.get("expected_features", {}), tests.get("expected_probs", [])
    tol = float(tests.get("tolerance", 1e-6))
    if idxs and exp_f:
        for i, exp in zip(idxs, exp_f):
            for k, v in exp.items():
                got = full_f.iloc[i].get(k)
                assert got is not None and abs(float(got) - float(v)) <= tol, f"feature {k}[{i}] {got} != expected {v}"
    probs = []
    for i in idxs:
        row = {f: float(full_f.iloc[i].get(f, 0.0)) for f in model.features}
        probs.append(model.predict_proba(row))
    if exp_p:
        assert len(exp_p) == len(probs) and all(abs(a - b) <= tol for a, b in zip(probs, exp_p)), "probs mismatch"
    _r(checks, "reproducibility", "pass", f"{len(idxs)} test vectors within tolerance {tol}")

    # 6. determinism
    f2 = compute_features(pack["features"]["dsl"], candles)
    assert full_f.equals(f2), "feature computation is not deterministic"
    _r(checks, "determinism", "pass", "two runs identical")

    # 7. sandbox run for custom code (fail closed)
    mods = pack.get("features", {}).get("custom_modules", [])
    if mods:
        from .sandbox import run_custom_module, SandboxUnavailable
        try:
            for m in mods:
                out = run_custom_module(m["name"], m["code_b64gz"], candles[:100])
                assert len(out) > 0
            _r(checks, "sandbox", "pass", f"{len(mods)} modules ran in sandbox")
        except SandboxUnavailable as e:
            _r(checks, "sandbox", "fail", f"FAIL-CLOSED: {e}")
    else:
        _r(checks, "sandbox", "pass", "no custom code (DSL-only)")

    # 8. performance
    t0 = time.perf_counter()
    for i in idxs[:1] or [len(candles) - 1]:
        row = {f: float(full_f.iloc[i].get(f, 0.0)) for f in model.features}
        model.predict_proba(row)
    lat = time.perf_counter() - t0
    assert lat < 2.0, f"inference latency {lat:.2f}s >= 2s"
    _r(checks, "performance", "pass", f"inference {lat*1000:.1f}ms")

    # 9. output sanity + rule/news parse
    assert all(0.0 <= p <= 1.0 for p in probs) and not any(np.isnan(probs)), "probs out of [0,1] or NaN"
    if len(set(round(p, 9) for p in probs)) <= 1 and len(probs) > 1:
        raise AssertionError("model output is constant")
    validate_rules(pack.get("rules", {}) or {})
    _r(checks, "output_sanity", "pass", "probs in range, non-constant, rules parse")

def main(argv=None):
    ap = argparse.ArgumentParser(prog="validate_pack")
    ap.add_argument("file"); ap.add_argument("--mode", choices=["fast", "full"], default="full")
    a = ap.parse_args(argv)
    raw = open(a.file, "rb").read()
    try:
        pack = json.loads(raw)
    except json.JSONDecodeError as e:
        report = {"verdict": "fail", "checks": [{"check": "parse", "status": "fail", "detail": str(e)}]}
        print(json.dumps(report, indent=1)); print("\nVERDICT: FAIL (not valid JSON)"); sys.exit(2)
    report = validate_pack(pack, raw, mode=a.mode)
    print(json.dumps(report, indent=1))
    print(f"\nVERDICT: {report['verdict'].upper()}")
    for c in report["checks"]:
        print(f"  [{c['status'].upper():4}] {c['check']}: {c['detail']}")
    sys.exit(0 if report["verdict"] in ("pass", "warn") else 1)

if __name__ == "__main__":
    main()
