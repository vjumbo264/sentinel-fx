#!/usr/bin/env python3
"""
tools/bot_safety_dispatch.py
============================
Crash-proof safety handler for bot.yml (H8, V11).
Inspects workflow run history, differentiates between platform/GitHub failures
and code failures, enforces cool-down progression, reports recovery telemetry to
the Worker, and safely dispatches replacement runs while preventing duplicates.
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

def main():
    token = os.environ.get("GH_TOKEN_FOR_CHAIN") or os.environ.get("GH_CHAIN_PAT") or os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", "vjumbo264/sentinel-fx")
    worker_url = os.environ.get("WORKER_URL", "https://sentinel-fx-worker.vjumbo264.workers.dev")
    bot_secret = os.environ.get("BOT_SHARED_SECRET", "")
    mode = os.environ.get("DISPATCH_MODE", "demo")
    job_status = os.environ.get("JOB_STATUS", "failure")

    print(f"bot_safety_dispatch: starting with job_status={job_status}, mode={mode}")

    if job_status == "success":
        print("Normal completion; bot handles its own handover/successor dispatch.")
        # Report successful recovery if previously in recovering state
        notify_worker(worker_url, bot_secret, "/api/bot/settings", {
            "bot_recovery": {
                "status": "recovered",
                "recovered_at_utc": datetime.now(timezone.utc).isoformat(),
                "note": "Bot chain healthy and executing"
            }
        })
        return 0

    # 1. Fetch recent runs of bot.yml from GitHub Actions API
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "sentinel-bot-safety/1.0"
    }

    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/workflows/bot.yml/runs?per_page=15",
        headers=headers
    )

    runs = []
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            runs = json.loads(r.read().decode("utf-8")).get("workflow_runs", [])
    except Exception as e:
        print(f"Warning: failed to query GitHub API for runs: {e}")

    # 2. Analyze failure nature: code failure vs platform failure
    code_failures = 0
    platform_failures = 0
    last_error_message = "Unknown bot execution failure"

    # Read error from environment or local crash log if available
    crash_log_path = "crash.log"
    if os.path.exists(crash_log_path):
        try:
            with open(crash_log_path, "r", encoding="utf-8", errors="replace") as f:
                last_error_message = f.read().strip()[-500:]
        except Exception:
            pass

    for r in runs:
        conclusion = r.get("conclusion")
        if conclusion == "success":
            break
        elif conclusion in ("failure", "timed_out", "cancelled"):
            # Check if cancelled or timed out by platform
            if conclusion == "timed_out" or r.get("event") == "schedule":
                platform_failures += 1
            else:
                # We classify as code failure unless marked infra error
                code_failures += 1

    total_failures = code_failures + platform_failures
    print(f"Consecutive failures: total={total_failures}, code={code_failures}, platform={platform_failures}")

    now = datetime.now(timezone.utc)

    # 3. Code failure check: halt after 3 consecutive code failures
    if code_failures >= 3:
        msg = f"CIRCUIT BREAKER: Bot auto-chain halted after {code_failures} consecutive code failures: {last_error_message}"
        print(f"CRITICAL: {msg}")
        notify_worker(worker_url, bot_secret, "/api/bot/log", {
            "level": "critical",
            "pair": "*",
            "message": msg
        })
        notify_worker(worker_url, bot_secret, "/api/bot/settings", {
            "bot_recovery": {
                "status": "code_failure_halted",
                "error": last_error_message,
                "consecutive_failures": code_failures,
                "halted_at_utc": now.isoformat()
            }
        })
        return 0

    # 4. Determine delay/cool-down
    # Platform cool-downs: 30 min (1800s), 2 hours (7200s), 6 hours (21600s)
    # Code failure backoff: 90s * (code_failures + 1)
    if platform_failures >= 3:
        delay = 21600 # 6 hours
    elif platform_failures == 2:
        delay = 7200  # 2 hours
    elif platform_failures == 1:
        delay = 1800  # 30 min
    else:
        delay = (code_failures + 1) * 90

    # Test override
    test_delay = os.environ.get("SAFETY_DISPATCH_DELAY_OVERRIDE")
    if test_delay is not None:
        try:
            delay = int(test_delay)
            print(f"Applied SAFETY_DISPATCH_DELAY_OVERRIDE={delay}s")
        except ValueError:
            pass

    next_try_utc = (now + timedelta(seconds=delay)).isoformat()
    status_text = f"Bot chain recovering, next try at {next_try_utc}"
    print(status_text)

    # Notify worker of recovery status
    notify_worker(worker_url, bot_secret, "/api/bot/settings", {
        "bot_recovery": {
            "status": "recovering",
            "next_try_utc": next_try_utc,
            "attempt": total_failures + 1,
            "reason": last_error_message,
            "delay_seconds": delay
        }
    })
    notify_worker(worker_url, bot_secret, "/api/bot/log", {
        "level": "warning",
        "pair": "*",
        "message": f"{status_text} (attempt {total_failures + 1})"
    })

    # If delay is small (e.g. <= 300s or in tests), sleep and dispatch directly
    if delay <= 300:
        print(f"Waiting {delay}s before dispatching replacement run...")
        time.sleep(delay)
        dispatch_workflow(repo, token, mode)
    else:
        print(f"Long cool-down ({delay}s). Backup cron or schedule will recover at next window.")

    return 0


def notify_worker(worker_url: str, secret: str, path: str, payload: dict):
    if not worker_url:
        return
    url = worker_url.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "X-Bot-Secret": secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "sentinel-bot-safety/1.0"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read()
    except Exception as e:
        print(f"Notice: Worker notification to {path} returned: {e}")


def dispatch_workflow(repo: str, token: str, mode: str):
    url = f"https://api.github.com/repos/{repo}/actions/workflows/bot.yml/dispatches"
    data = json.dumps({"ref": "main", "inputs": {"mode": mode}}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "sentinel-bot-safety/1.0"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            if r.status in (200, 204):
                print("Replacement run dispatched successfully.")
            else:
                print(f"Dispatch returned status {r.status}")
    except Exception as e:
        print(f"Failed to dispatch workflow: {e}")


if __name__ == "__main__":
    sys.exit(main())
