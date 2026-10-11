#!/usr/bin/env python3
"""Build test fixtures for v2 bundle checker and run parity / rejection suite."""
import hashlib
import json
import os
import sys
import zipfile

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures")
os.makedirs(FIXTURES_DIR, exist_ok=True)

def make_clean_bundle(out_path):
    plan = {
        "schema_version": 2,
        "symbol": "EURUSD",
        "market": "forex",
        "nodes": [
            {
                "id": "features",
                "type": "feature_group",
                "dsl": [
                    {"id": "rsi_14", "op": "rsi", "params": {"period": 14}}
                ]
            },
            {
                "id": "cfd_policy",
                "type": "policy",
                "inputs": ["features"],
                "action": "BUY",
                "side": "BUY",
                "volume": 0.01,
                "sl": 1.0500,
                "tp": 1.0600,
                "confidence": 0.65
            }
        ]
    }
    
    preprocess = {
        "features": ["return_1", "return_5"],
        "lookback_bars": 30
    }
    
    risk_brain = {
        "symbol": "EURUSD",
        "digits": 5,
        "contract_size": 100000.0,
        "volume_min": 0.01,
        "volume_step": 0.01,
        "default_sl_pts": 50
    }

    candles = [
        {"epoch": 1700000000 + i * 60, "open": 1.0500 + i * 0.0001, "high": 1.0505 + i * 0.0001, "low": 1.0495 + i * 0.0001, "close": 1.0502 + i * 0.0001}
        for i in range(60)
    ]
    
    vectors = {
        "tolerance": 1e-3,
        "latency_ms": 600.0,
        "vectors": [
            {
                "inputs": candles,
                "context": {"minutes_to_news": 9999, "news_state": "clear"},
                "expected": {
                    "action": "BUY",
                    "side": "BUY",
                    "p_win": 0.65
                }
            }
        ]
    }

    files = {
        "analysis_plan.json": json.dumps(plan, indent=2).encode(),
        "preprocess.json": json.dumps(preprocess, indent=2).encode(),
        "risk_brain.json": json.dumps(risk_brain, indent=2).encode(),
        "tests/vectors.json": json.dumps(vectors, indent=2).encode(),
    }

    file_hashes = {}
    for fn, data in files.items():
        file_hashes[fn] = hashlib.sha256(data).hexdigest()

    manifest = {
        "schema_version": 2,
        "symbol": "R_10",
        "version": 1,
        "created_utc": "2026-10-10T12:00:00Z",
        "files": file_hashes
    }
    files["manifest.json"] = json.dumps(manifest, indent=2).encode()

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fn, data in files.items():
            zf.writestr(fn, data)

def make_bad_bundle(out_path, bad_type):
    # Base clean files
    plan = {
        "schema_version": 2,
        "symbol": "R_10",
        "market": "synthetic",
        "nodes": [{"id": "n1", "type": "analyst", "outputs": ["p_up"]}]
    }
    manifest = {
        "schema_version": 2,
        "symbol": "R_10",
        "files": {}
    }
    files = {
        "analysis_plan.json": json.dumps(plan).encode(),
    }

    if bad_type == "missing_file":
        manifest["files"] = {
            "analysis_plan.json": hashlib.sha256(files["analysis_plan.json"]).hexdigest(),
            "missing_model.onnx": "0" * 64,
        }
        files["manifest.json"] = json.dumps(manifest).encode()

    elif bad_type == "wrong_hash":
        manifest["files"] = {
            "analysis_plan.json": "f" * 64, # Wrong hash
        }
        files["manifest.json"] = json.dumps(manifest).encode()

    elif bad_type == "pickled_model":
        files["weights.pkl"] = b"cos\nsystem\n(S'echo pwned'\ntR."
        manifest["files"] = {
            "analysis_plan.json": hashlib.sha256(files["analysis_plan.json"]).hexdigest(),
            "weights.pkl": hashlib.sha256(files["weights.pkl"]).hexdigest(),
        }
        files["manifest.json"] = json.dumps(manifest).encode()

    elif bad_type == "missing_node":
        plan["nodes"] = [{"id": "bad_node", "type": "analyst", "model": "non_existent.onnx"}]
        files["analysis_plan.json"] = json.dumps(plan).encode()
        manifest["files"] = {
            "analysis_plan.json": hashlib.sha256(files["analysis_plan.json"]).hexdigest(),
        }
        files["manifest.json"] = json.dumps(manifest).encode()

    elif bad_type == "parity_mismatch":
        vectors = {
            "tolerance": 1e-4,
            "vectors": [
                {
                    "inputs": [{"epoch": 1700000000 + i * 60, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05} for i in range(40)],
                    "expected": {"action": "trade", "side": "PUT", "p_win": 0.999}  # Impossibly high to force mismatch
                }
            ]
        }
        files["tests/vectors.json"] = json.dumps(vectors).encode()
        manifest["files"] = {
            "analysis_plan.json": hashlib.sha256(files["analysis_plan.json"]).hexdigest(),
            "tests/vectors.json": hashlib.sha256(files["tests/vectors.json"]).hexdigest(),
        }
        files["manifest.json"] = json.dumps(manifest).encode()

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fn, data in files.items():
            zf.writestr(fn, data)

def main():
    print("[*] Generating v2 bundle test fixtures...")
    clean_p = os.path.join(FIXTURES_DIR, "clean_v2.sfxmodel.zip")
    make_clean_bundle(clean_p)
    print(f"  [+] Created {clean_p}")

    bad_types = ["missing_file", "wrong_hash", "pickled_model", "missing_node", "parity_mismatch"]
    for bt in bad_types:
        bp = os.path.join(FIXTURES_DIR, f"bad_{bt}.sfxmodel.zip")
        make_bad_bundle(bp, bt)
        print(f"  [+] Created {bp}")

    print("[✓] All test fixtures created successfully.")

if __name__ == "__main__":
    main()
