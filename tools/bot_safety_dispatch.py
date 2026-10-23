#!/usr/bin/env python3
"""
tools/bot_safety_dispatch.py
============================
Circuit-breaker and cool-down safety handler for bot.yml (L8).
- Distinguishes code/auth errors vs GitHub/platform/cancellation failures.
- Growing cool-downs: 30 min (1800s), 2 h (7200s), 6 h (21600s), then every 6 h (21600s).
- Halts after 3 consecutive code failures with the real error reported to the Home page.
- Posts critical log alerts to the Worker and prevents duplicate live bot dispatches.
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

COOLDOWNS = [1800, 7200, 21600]  # 30m, 2h, 6h (and 6h thereafter)
TRANSIENT_HINTS = (
    "timed out", "timeout", "connectionreset", "connection aborted",
    "temporary failure", "502 bad gateway", "503 service unavailable",
    "504 gateway timeout", "network is unreachable", "name or service not known",
)


def extract_error(crash_log_path: str, job_status: str, mt5_outcome: str, bot_outcome: str) -> str:
    if os.path.exists(crash_log_path):
        try:
            with open(crash_log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = [ln.strip() for ln in f.read().splitlines() if ln.strip()]
            for ln in reversed(lines):
                if any(k in ln for k in ("Error:", "Exception:", "AssertionError", "CRITICAL", "FAIL CLOSED", "retcode")):
                    return ln[-350:]
            if lines:
                return lines[-1][-350:]
        except Exception:
            pass
    if job_status in ("cancelled", "timed_out"):
        return f"GitHub Actions runner {job_status}"
    if mt5_outcome == "failure":
        return "MT5 Linux container setup failed before bot start"
    if bot_outcome in ("skipped", ""):
        return "Workflow step failed prior to bot execution"
    return "Bot exited with non-zero status"


def classify_failure(job_status: str, mt5_outcome: str, bot_outcome: str, error_msg: str) -> str:
    low = error_msg.lower()
    if job_status in ("cancelled", "timed_out"):
        return "platform"
    if os.environ.get("FORCE_FAILURE_CLASS") in ("code", "platform"):
        return os.environ["FORCE_FAILURE_CLASS"]
    if bot_outcome in ("skipped", "") or mt5_outcome == "failure":
        # Setup/container/runner failure before bot.main unless explicit auth error
        if "authorization failed" in low or "invalid account" in low:
            return "code"
        return "platform"
    if any(h in low for h in TRANSIENT_HINTS) and not any(
        c in low for c in ("syntaxerror", "importerror", "assertionerror", "valueerror", "typeerror", "keyerror")
    ):
        return "platform"
    return "code"


def get_worker_json(worker_url: str, secret: str, path: str) -> dict:
    if not worker_url or not secret:
        return {}
    req = urllib.request.Request(
        worker_url.rstrip("/") + path,
        headers={"X-Bot-Secret": secret, "Accept": "application/json", "User-Agent": "sentinel-bot-safety/2.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"Notice: GET {path} returned: {e}")
        return {}


def notify_worker(worker_url: str, secret: str, path: str, payload: dict):
    if not worker_url or not secret:
        return
    req = urllib.request.Request(
        worker_url.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "X-Bot-Secret": secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "sentinel-bot-safety/2.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read()
    except Exception as e:
        print(f"Notice: POST {path} returned: {e}")


def has_other_active_bot_run(repo: str, token: str, current_run_id: int) -> bool:
    if not token:
        return False
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/workflows/bot.yml/runs?per_page=15",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "sentinel-bot-safety/2.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            runs = json.loads(r.read().decode("utf-8")).get("workflow_runs", [])
        return any(int(x.get("id", 0)) != current_run_id and x.get("status") != "completed" for x in runs)
    except Exception as e:
        print(f"Warning checking active runs: {e}")
        return False


def dispatch_workflow(repo: str, token: str, mode: str) -> bool:
    if not token:
        return False
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/workflows/bot.yml/dispatches",
        data=json.dumps({"ref": "main", "inputs": {"mode": mode}}).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "sentinel-bot-safety/2.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            ok = r.status in (200, 204)
            print("Replacement run dispatched successfully." if ok else f"Dispatch status {r.status}")
            return ok
    except Exception as e:
        print(f"Failed to dispatch workflow: {e}")
        return False


def main() -> int:
    token = os.environ.get("GH_TOKEN_FOR_CHAIN") or os.environ.get("GH_CHAIN_PAT") or os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "vjumbo264/sentinel-fx")
    worker_url = os.environ.get("WORKER_URL", "https://sentinel-fx-worker.vjumbo264.workers.dev")
    bot_secret = os.environ.get("BOT_SHARED_SECRET", "")
    mode = os.environ.get("DISPATCH_MODE", "demo")
    job_status = os.environ.get("JOB_STATUS", "failure").lower()
    mt5_outcome = os.environ.get("MT5_START_OUTCOME", "")
    bot_outcome = os.environ.get("BOT_RUN_OUTCOME", "")
    run_id = int(os.environ.get("GITHUB_RUN_ID", "0") or 0)
    crash_log = os.environ.get("CRASH_LOG_PATH", "crash.log")

    sess = get_worker_json(worker_url, bot_secret, "/api/bot/session")
    settings = sess.get("settings", {})
    prev = settings.get("bot_recovery") or {}
    now = datetime.now(timezone.utc)

    if job_status == "success":
        print("Normal completion; bot handles its own handover/exit.")
        if prev.get("status") in ("recovering", "code_failure_halted"):
            notify_worker(worker_url, bot_secret, "/api/bot/settings", {
                "bot_recovery": {
                    "status": "recovered",
                    "recovered_at_utc": now.isoformat(),
                    "consecutive_code_failures": 0,
                    "consecutive_platform_failures": 0,
                    "note": "Bot chain healthy and executing",
                }
            })
        return 0

    if settings.get("power") is False or settings.get("halt") is True:
        print("Bot power is OFF or emergency halt is active; skipping auto-recovery.")
        return 0

    err_msg = extract_error(crash_log, job_status, mt5_outcome, bot_outcome)
    kind = classify_failure(job_status, mt5_outcome, bot_outcome, err_msg)
    code_fails = int(prev.get("consecutive_code_failures", 0))
    plat_fails = int(prev.get("consecutive_platform_failures", 0))

    if kind == "code":
        code_fails += 1
        attempt = code_fails
    else:
        plat_fails += 1
        attempt = plat_fails

    print(f"Failure classified as {kind} (code_fails={code_fails}, plat_fails={plat_fails}): {err_msg}")

    if kind == "code" and code_fails >= 3:
        msg = f"CIRCUIT BREAKER: Halted after {code_fails} consecutive code errors: {err_msg}"
        print(f"CRITICAL: {msg}")
        notify_worker(worker_url, bot_secret, "/api/bot/log", {
            "level": "critical",
            "pair": "*",
            "message": msg,
        })
        notify_worker(worker_url, bot_secret, "/api/bot/settings", {
            "bot_recovery": {
                "status": "code_failure_halted",
                "kind": "code",
                "error": err_msg,
                "consecutive_code_failures": code_fails,
                "consecutive_platform_failures": plat_fails,
                "halted_at_utc": now.isoformat(),
            }
        })
        return 0

    delay = COOLDOWNS[min(attempt - 1, len(COOLDOWNS) - 1)]
    override = os.environ.get("SAFETY_DISPATCH_DELAY_OVERRIDE")
    if override is not None:
        try:
            delay = int(override)
        except ValueError:
            pass

    next_try_utc = (now + timedelta(seconds=delay)).isoformat()
    crit_msg = f"Bot {kind} failure (attempt {attempt}, cooldown {delay}s, next try {next_try_utc}): {err_msg}"
    notify_worker(worker_url, bot_secret, "/api/bot/log", {
        "level": "critical",
        "pair": "*",
        "message": crit_msg,
    })
    notify_worker(worker_url, bot_secret, "/api/bot/settings", {
        "bot_recovery": {
            "status": "recovering",
            "kind": kind,
            "attempt": attempt,
            "consecutive_code_failures": code_fails,
            "consecutive_platform_failures": plat_fails,
            "next_try_utc": next_try_utc,
            "reason": err_msg,
            "delay_seconds": delay,
        }
    })

    if delay <= 120 and os.environ.get("NO_DISPATCH") != "1":
        if delay > 0:
            time.sleep(delay)
        if not has_other_active_bot_run(repo, token, run_id):
            dispatch_workflow(repo, token, mode)
        else:
            print("Another bot.yml run is already active; skipping duplicate dispatch.")
    else:
        print(f"Cooldown {delay}s recorded (next_try_utc={next_try_utc}); scheduled backup runner will resume after cooldown.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
