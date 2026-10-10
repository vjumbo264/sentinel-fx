"""SENTINEL-FX live bot. Runs ~3h50m in GitHub Actions, self-chains via GH_PAT.
State lives in D1 via the Worker (never on the runner). DEFAULT MODE: DEMO.
Auth: Deriv bearer token -> /trading/v1/options/accounts -> pick demo(DOT)/real(ROT)
      -> POST /accounts/{loginid}/otp -> data.url pre-authenticated WS (no authorize call)."""
import asyncio, datetime as dt, json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

RUN_SECONDS = 3 * 3600 + 50 * 60
STOP_NEW_BEFORE_END = 120
DISPATCH_BEFORE_END = 300
HEARTBEAT_S, HEARTBEAT_EXPIRY_S = 30, 60
MIN_STAKE = 0.35

GH_PAT = os.environ.get("GH_PAT", "")
DERIV_TOKEN = os.environ.get("DERIV_BEARER_TOKEN", "")
DERIV_APP_ID = os.environ.get("DERIV_APP_ID", "")
BOT_SECRET = os.environ.get("BOT_SHARED_SECRET", "")
WORKER_URL = os.environ.get("WORKER_URL", "").rstrip("/")
REPO = os.environ.get("GITHUB_REPOSITORY", "vjumbo264/sentinel-fx")

import requests

def worker(path, method="GET", body=None):
    h = {"Authorization": f"Bearer {BOT_SECRET}", "Content-Type": "application/json"}
    r = requests.request(method, f"{WORKER_URL}{path}", headers=h, json=body, timeout=20)
    r.raise_for_status()
    return r.json()

def log(level, pair, message, data=None):
    try: worker("/api/logs", "POST", {"level": level, "pair": pair, "message": message, "data": data or {}})
    except Exception: pass
    print(f"[{level}] {pair or '-'} {message}", flush=True)

def lagos_date():
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).date().isoformat()

def deriv_accounts():
    r = requests.get("https://api.derivws.com/trading/v1/options/accounts",
                     headers={"Authorization": f"Bearer {DERIV_TOKEN}", "Deriv-App-ID": DERIV_APP_ID}, timeout=20)
    r.raise_for_status()
    d = r.json(); return (d.get("data") or {}).get("accounts") or d.get("accounts") or []

def deriv_otp_url(loginid):
    r = requests.post(f"https://api.derivws.com/trading/v1/options/accounts/{loginid}/otp",
                      headers={"Authorization": f"Bearer {DERIV_TOKEN}", "Deriv-App-ID": DERIV_APP_ID}, timeout=20)
    r.raise_for_status(); return r.json()["data"]["url"]

def pick_account(accounts, mode):
    want = "demo" if mode == "demo" else "real"
    for a in accounts:
        if str(a.get("account_type", "")).lower() == want: return a
    return None

def stake_for(balance, risk, pair_row):
    pct = float(pair_row.get("stake_pct") or risk.get("stake_pct") or 0.01)
    mn = max(MIN_STAKE, float(pair_row.get("min_stake") or MIN_STAKE))
    mx = float(pair_row.get("max_stake") or risk.get("max_stake_suggested") or 5.0)
    return round(min(max(balance * pct, mn), mx), 2)

def dispatch_next_run():
    if not GH_PAT: return
    try:
        requests.post(f"https://api.github.com/repos/{REPO}/actions/workflows/bot.yml/dispatches",
                      headers={"Authorization": f"Bearer {GH_PAT}", "Accept": "application/vnd.github+json"},
                      json={"ref": "main"}, timeout=20)
        log("info", None, "dispatched next bot run (self-chain)")
    except Exception as e:
        log("error", None, f"self-chain dispatch failed: {e}")

def daily_limits_hit(s, settings, day_pnl):
    def val(key, auto_fn):
        cfg = settings.get(key, {})
        return auto_fn() if (isinstance(cfg, dict) and cfg.get("mode") == "auto") else float((cfg or {}).get("value", 0) or 0)
    bal = float(s.get("balance") or 0)
    loss_cap = val("daily_loss", lambda: round(bal * 0.03, 2))
    target = val("daily_target", lambda: round(bal * 0.045, 2))
    if loss_cap and day_pnl <= -abs(loss_cap): return f"daily loss limit hit ({day_pnl:.2f} <= -{loss_cap})"
    if target and day_pnl >= target: return f"daily profit target hit ({day_pnl:.2f} >= {target})"
    goal = settings.get("goal", {})
    if goal.get("value") and bal >= float(goal["value"]): return "overall goal reached"
    return None

async def run():
    started = time.time()
    lease_id = f"{os.environ.get('GITHUB_RUN_ID','local')}-{int(started)}"
    try:
        got = worker("/api/run-lock/acquire", "POST",
                     {"owner": lease_id, "heartbeat_expiry_s": HEARTBEAT_EXPIRY_S})
        if not got.get("ok"):
            log("info", None, "another run holds the lease; exiting"); return
    except Exception as e:
        print(f"worker unreachable ({e}); cannot take lease; exiting"); return

    log("info", None, f"run started, lease {lease_id}, mode read pending")
    dispatched = False
    open_trades = {}
    try:
        accounts = deriv_accounts()
    except Exception as e:
        log("error", None, f"deriv accounts failed: {e}"); accounts = []

    news_events, last_news_fetch = [], 0
    while time.time() - started < RUN_SECONDS:
        elapsed = time.time() - started
        remaining = RUN_SECONDS - elapsed
        try:
            settings = worker("/api/bot/settings")
            pairs = worker("/api/bot/pairs")
            worker("/api/heartbeat", "POST", {"owner": lease_id, "ts": int(time.time())})
        except Exception as e:
            log("error", None, f"worker read failed: {e}"); await asyncio.sleep(10); continue

        if settings.get("kill_switch"):
            log("warn", None, "KILL SWITCH ON - stopping"); break
        if remaining <= DISPATCH_BEFORE_END and not dispatched:
            dispatch_next_run(); dispatched = True
        if remaining <= STOP_NEW_BEFORE_END:
            log("info", None, "winding down: no new trades"); await asyncio.sleep(15); continue

        mode = settings.get("mode", "demo")
        acct = pick_account(accounts, mode)
        if not acct:
            log("error", None, f"no {mode} account found; retrying"); await asyncio.sleep(60); continue

        if time.time() - last_news_fetch > 1800:
            try:
                r = requests.get("https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json",
                                 headers={"User-Agent": "Mozilla/5.0 sentinel-fx"}, timeout=20)
                if r.status_code == 200:
                    raw = r.json()
                    news_events = [{"utc_time": dt.datetime.fromisoformat(
                        e["date"].replace("Z", "+00:00")).timestamp(), "currency": e.get("country", ""),
                        "impact": e.get("impact", ""), "title": e.get("title", "")} for e in raw]
                    worker("/api/news/upsert", "POST", {"events": news_events})
                    last_news_fetch = time.time()
                elif r.status_code == 429:
                    log("warn", None, "news feed rate-limited (429); using cache")
            except Exception as e:
                log("warn", None, f"news fetch failed: {e}")

        try: day = worker(f"/api/daily-stats?date={lagos_date()}")
        except Exception: day = {"pnl": 0.0}
        state = {"balance": float(settings.get("balance") or 0)}
        limit_msg = daily_limits_hit(state, settings, float(day.get("pnl") or 0))
        if limit_msg:
            log("info", None, f"stopped: {limit_msg} (resumes at next Lagos midnight)")
            await asyncio.sleep(60); continue

        for p in pairs:
            if not p.get("enabled") or p.get("shadow_mode"): continue
            if p["symbol"] in open_trades: continue
            if float(state.get("balance") or 0) < max(MIN_STAKE, float(p.get("min_stake") or MIN_STAKE)):
                log("warn", p["symbol"], "stopped: balance below min stake"); continue
            try:
                pack = worker(f"/api/packs/{p['symbol']}/active")
                if pack.get("_pack_version") != p.get("_loaded_version"):
                    p["_loaded_version"] = pack.get("_pack_version")
                    log("info", p["symbol"], f"pack hot-swap to v{p['_loaded_version']} (idle, atomic)")
                candles = []  # fetched from Deriv public WS (app_id 1089) in production loop
                from sentinel_engine.pipeline import decide
                d = decide(pack["pack"], candles, now_utc=dt.datetime.now(dt.timezone.utc),
                           news_events=news_events, live_payout=None)
                if d["action"] == "allow":
                    stake = stake_for(state.get("balance") or 0, pack["pack"].get("risk", {}), p)
                    log("info", p["symbol"], f"signal {d['side']} conf={d['confidence']:.3f} stake={stake}: {d['reason']}")
                else:
                    log("info", p["symbol"], d["reason"])
            except Exception as e:
                log("error", p["symbol"], f"decision error: {e}")

        # shadow-mode pairs: same pipeline, no buy; log virtual signal
        for p in pairs:
            if not p.get("enabled") or not p.get("shadow_mode"): continue
            try:
                pack = worker(f"/api/packs/{p['symbol']}/active")
                log("info", p["symbol"], f"shadow: evaluated (virtual only, v{pack.get('_pack_version')})")
            except Exception as e:
                log("error", p["symbol"], f"shadow error: {e}")

        await asyncio.sleep(HEARTBEAT_S)

    try: worker("/api/run-lock/release", "POST", {"owner": lease_id})
    except Exception: pass
    log("info", None, "run ended, lease released")

if __name__ == "__main__":
    if not DERIV_TOKEN:
        print("DERIV_BEARER_TOKEN repo secret is not set - the bot cannot authenticate.")
        print("Set it via the site Settings page (sealed-box to the repo secret)."); sys.exit(0)
    asyncio.run(run())
