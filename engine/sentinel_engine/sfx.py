"""sfx — command-line toolkit for SENTINEL-FX pair model training and delivery.

Commands:
    sfx guide                  Print the autonomous training playbook offline
    sfx init <symbol>          Initialize training directory with data, durations & templates
    sfx sim <bundle>           Replay model in bankroll growth simulator
    sfx check <bundle>         Run code & bundle health checker
    sfx build <dir> <out.zip>  Assemble and hash a .sfxmodel.zip bundle
    sfx publish <bundle>       Upload to staging & dispatch publish workflow
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timezone

def cmd_guide(args):
    guide_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "TRAIN_PROMPT.md"),
        os.path.join(os.getcwd(), "TRAIN_PROMPT.md"),
    ]
    content = None
    for p in guide_paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
                break
    if not content:
        content = """# SENTINEL-FX TRAINING PLAYBOOK
1. OBJECTIVE: BALANCE GROWTH, NOT WIN RATE.
2. STUDY THE INSTRUMENT FIRST:
   - Resample candles across timeframes (1m, 5m, 15m, 1h, 4h, Daily).
   - Study market structure, round-number levels, volatility regimes.
   - For Forex (frx*), allowed durations are >= 15m. For Synthetics, Deriv allows seconds/minutes.
3. ARCHITECTURE: COMMITTEE OF ANALYSTS + HEAD TRADER.
   - Specialist analysts: Trend (higher TF), Momentum/Volatility, Levels, Regime.
   - Head model combines out-of-fold analyst opinions.
   - Probability calibration (p_win).
   - risk_brain: fractional Kelly sizing, bankroll compounds, stand-down rules.
4. RIGOR:
   - Lock final hold-out FIRST.
   - Purged walk-forward validation on development data.
5. DELIVER:
   - Export ONNX (data format only; no custom operators).
   - Build bundle: sfx build <dir> <symbol_v1.sfxmodel.zip>
   - Check bundle: sfx check <symbol_v1.sfxmodel.zip>
   - Deliver via file or: sfx publish <symbol_v1.sfxmodel.zip>
"""
    print(content)

def cmd_init(args):
    sym = args.symbol
    out_dir = args.dir or f"train_{sym}"
    os.makedirs(out_dir, exist_ok=True)
    print(f"[*] Initializing training workspace for {sym} in {out_dir}...")

    # Look for data/index.json
    root_paths = [os.getcwd(), os.path.join(os.path.dirname(__file__), "..", "..")]
    data_idx = None
    for r in root_paths:
        p = os.path.join(r, "data", "index.json")
        if os.path.exists(p):
            with open(p, "r") as f:
                data_idx = json.load(f)
            break

    # Look for data/symbols.json
    symbols_meta = {}
    for r in root_paths:
        p = os.path.join(r, "data", "symbols.json")
        if os.path.exists(p):
            with open(p, "r") as f:
                symbols_meta = json.load(f)
            break

    sym_info = symbols_meta.get(sym, {})
    entry = data_idx.get(sym) if data_idx else None

    # Write pair metadata
    spec = {
        "symbol": sym,
        "market": "forex" if sym.startswith("frx") else "synthetic",
        "allowed_durations": sym_info.get("allowed_durations", [15, 30, 60] if sym.startswith("frx") else [5, 15, 60]),
        "duration_unit": "m" if sym.startswith("frx") else "s",
        "min_stake": 0.35,
        "payout_assumed": 0.85,
        "data_entry": entry,
    }
    with open(os.path.join(out_dir, "symbol_spec.json"), "w") as f:
        json.dump(spec, f, indent=2)

    # Scaffolding template
    template_code = f'''#!/usr/bin/env python3
"""Training script for {sym} autonomous model."""
import json
import numpy as np
import pandas as pd
from sentinel_engine import compute_features
from sentinel_engine.sim import simulate_bankroll

def main():
    print("Training model for {sym}...")
    # 1. Load data
    # 2. Extract features causally
    # 3. Train analysts on purged walk-forward splits
    # 4. Train head model on out-of-fold analyst predictions
    # 5. Calibrate probabilities
    # 6. Optimize risk_brain parameters in bankroll simulator
    # 7. Evaluate on locked hold-out
    # 8. Export to ONNX and assemble bundle
    print("Done. Run: sfx build . {sym}_v1.sfxmodel.zip && sfx check {sym}_v1.sfxmodel.zip")

if __name__ == "__main__":
    main()
'''
    with open(os.path.join(out_dir, "train.py"), "w") as f:
        f.write(template_code)

    print(f"[✓] Workspace created at {out_dir}/")
    print(f"    - symbol_spec.json configured")
    print(f"    - train.py runnable template created")

def cmd_sim(args):
    from .sim import simulate_bundle
    print(f"[*] Running bankroll simulator for {args.bundle}...")
    res = simulate_bundle(args.bundle, initial_balance=args.balance or 100.0)
    print("=" * 60)
    print("SIMULATOR GROWTH REPORT")
    print("=" * 60)
    for k, v in res.items():
        if isinstance(v, float):
            print(f"  {k:<28}: {v:.4f}")
        else:
            print(f"  {k:<28}: {v}")
    print("=" * 60)

def cmd_check(args):
    from .check import main as check_main
    check_main([args.bundle])

def cmd_build(args):
    src_dir = args.dir
    out_zip = args.out
    if not os.path.isdir(src_dir):
        print(f"[ERROR] Source directory does not exist: {src_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Building bundle from {src_dir} -> {out_zip}...")
    # Gather files and compute hashes
    manifest_path = os.path.join(src_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        # Create minimal manifest
        manifest = {
            "schema_version": 2,
            "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "files": {}
        }
    else:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)

    file_hashes = {}
    for root, _, files in os.walk(src_dir):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, src_dir).replace("\\\\", "/")
            if rel == "manifest.json":
                continue
            with open(full, "rb") as fp:
                file_hashes[rel] = hashlib.sha256(fp.read()).hexdigest()

    manifest["files"] = file_hashes
    manifest["schema_version"] = 2
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(manifest_path, "manifest.json")
        for rel in sorted(file_hashes.keys()):
            full = os.path.join(src_dir, rel)
            zf.write(full, rel)

    bundle_hash = hashlib.sha256(open(out_zip, "rb").read()).hexdigest()
    print(f"[✓] Bundle built successfully: {out_zip}")
    print(f"    SHA-256: {bundle_hash}")

def cmd_publish(args):
    bundle = args.bundle
    pat = args.pat or os.environ.get("GITHUB_PAT") or os.environ.get("GH_CHAIN_PAT")
    repo = os.environ.get("GITHUB_REPOSITORY", "vjumbo264/sentinel-fx")
    if not pat:
        print("[ERROR] GitHub PAT is required for publishing. Provide via --pat or GITHUB_PAT env.", file=sys.stderr)
        sys.exit(1)

    from tools.publish_model import publish
    publish(bundle, pat, repo)

def main():
    ap = argparse.ArgumentParser(prog="sfx", description="SENTINEL-FX Autonomous Model Toolkit")
    sub = ap.add_subparsers(dest="command", required=True)

    # guide
    sub.add_parser("guide", help="Print autonomous training playbook")

    # init
    p_init = sub.add_parser("init", help="Initialize pair training directory")
    p_init.add_argument("symbol", help="Target pair symbol (e.g. frxEURUSD, R_10)")
    p_init.add_argument("--dir", default=None, help="Output workspace directory")

    # sim
    p_sim = sub.add_parser("sim", help="Run bankroll growth simulator")
    p_sim.add_argument("bundle", help="Path to .sfxmodel.zip bundle")
    p_sim.add_argument("--balance", type=float, default=100.0, help="Initial balance (default 100)")

    # check
    p_chk = sub.add_parser("check", help="Run bundle health & contract checker")
    p_chk.add_argument("bundle", help="Path to .sfxmodel.zip bundle")

    # build
    p_bld = sub.add_parser("build", help="Assemble .sfxmodel.zip bundle from folder")
    p_bld.add_argument("dir", help="Source directory containing analysis_plan.json, models, etc.")
    p_bld.add_argument("out", help="Output .sfxmodel.zip path")

    # publish
    p_pub = sub.add_parser("publish", help="Publish bundle to repository")
    p_pub.add_argument("bundle", help="Path to .sfxmodel.zip bundle")
    p_pub.add_argument("--pat", default=None, help="GitHub PAT with write access")

    args = ap.parse_args()
    if args.command == "guide":
        cmd_guide(args)
    elif args.command == "init":
        cmd_init(args)
    elif args.command == "sim":
        cmd_sim(args)
    elif args.command == "check":
        cmd_check(args)
    elif args.command == "build":
        cmd_build(args)
    elif args.command == "publish":
        cmd_publish(args)

if __name__ == "__main__":
    main()
