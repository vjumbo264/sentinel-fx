#!/usr/bin/env python3
"""SENTINEL-FX model publisher — the AI credential route (PUBLISH task).

Uploads a .sfxmodel.zip into the `staging` release (asset replaced by name),
dispatches publish-model.yml, polls the run, and prints the validator result.

  python tools/publish_model.py <bundle.sfxmodel.zip> --symbol frxEURUSD \
      --version 2 --token <fine-grained PAT>

The PAT needs Contents:RW + Actions:RW on this ONE repository only.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import time
import urllib.request

REPO = "vjumbo264/sentinel-fx"


def api(token, method, path, body=None, raw=None, ctype="application/json"):
    url = ("https://uploads.github.com" if path.startswith("/up/")
           else "https://api.github.com") + path.replace("/up/", "/")
    data = raw if raw is not None else (None if body is None
                                        else json.dumps(body).encode())
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "Content-Type": ctype, "User-Agent": "sentinel-publish"})
    with urllib.request.urlopen(req, timeout=60) as r:
        t = r.read()
        return json.loads(t.decode()) if t else {}


def ensure_staging(token):
    try:
        return api(token, "GET", f"/repos/{REPO}/releases/tags/staging")
    except Exception:
        return api(token, "POST", f"/repos/{REPO}/releases",
                   {"tag_name": "staging", "name": "staging",
                    "body": "Staging area for model bundles. publish-model.yml "
                            "validates and moves them to models-0N."})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--version", type=int, required=True)
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    a = ap.parse_args()
    # Allow standard forex (EURUSD), frx-style, and synthetic index names
    if not re.match(r"^([A-Z]{6}|frx[A-Z]{6}|R_\d+|1HZ\d+V|Volatility[\w\s\(\)]+)$", a.symbol):
        sys.exit(f"bad symbol: {a.symbol}")
    if not a.token:
        sys.exit("no token (env GITHUB_TOKEN or --token)")

    clean_sym = a.symbol.replace(" ", "_").replace("(", "").replace(")", "")
    asset_name = f"{clean_sym}_v{a.version}.sfxmodel.zip"
    print(f"[1/4] staging upload: {asset_name}")
    rel = ensure_staging(a.token)
    rel_id = rel["id"]
    for asst in rel.get("assets", []):
        if asst["name"] == asset_name:
            api(a.token, "DELETE", f"/repos/{REPO}/releases/assets/{asst['id']}")
    api(a.token, "POST",
        f"/up/repos/{REPO}/releases/{rel_id}/assets?name={asset_name}",
        raw=open(a.bundle, "rb").read(), ctype="application/zip")

    print("[2/4] dispatch publish-model.yml")
    api(a.token, "POST",
        f"/repos/{REPO}/actions/workflows/publish-model.yml/dispatches",
        {"ref": "main", "inputs": {"symbol": a.symbol, "version": str(a.version)}})

    print("[3/4] polling run ...")
    rid = None
    for _ in range(240):  # up to ~20 min
        time.sleep(5)
        runs = api(a.token, "GET",
                   f"/repos/{REPO}/actions/workflows/publish-model.yml/runs?per_page=1"
                   )["workflow_runs"]
        if runs and runs[0]["status"] == "completed":
            rid = runs[0]["id"]
            conclusion = runs[0]["conclusion"]
            break
    else:
        sys.exit("timed out waiting for the publish run")

    print(f"[4/4] run {rid} -> {conclusion}")
    try:
        log = urllib.request.urlopen(urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/actions/runs/{rid}/logs",
            headers={"Authorization": f"Bearer {a.token}"}), timeout=60).read().decode()
        for line in log.splitlines():
            if "VALIDATOR" in line or "verdict" in line.lower():
                print("   ", line[:300])
    except Exception as e:
        print("   (log fetch failed:", e, ")")
    sys.exit(0 if conclusion == "success" else 1)


if __name__ == "__main__":
    main()
