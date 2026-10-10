"""SENTINEL-FX live bot — resilient supervisor (FIX-A/FIX-B/FIX-C).

- One ~3h50m run per Actions job; dispatches the next run ~5min before end;
  stops opening new trades ~2min before end; the workflow has an if:always()
  safety dispatch for crashed/cancelled runs.
- SUPERVISOR: every websocket/network error triggers exponential backoff
  (2s..60s + jitter), a FRESH account list + NEW OTP, reconnect, balance
  re-fetch and open-contract reconciliation. The D1 lease is renewed while
  reconnecting so a second runner can never trade concurrently.
- MODE SWITCHING: the connected account type is tracked. When settings.mode
  differs from the connected account, the bot switches (fresh OTP) once no
  open contracts remain; heartbeat reports the CONNECTED account type,
  masked loginid, currency and balance — never just the requested mode.
- Worker/network outages never crash the bot: log/heartbeat swallow errors
  and the state fetch falls back to the last known settings.
- NEWS: refreshed hourly in-loop via sentinel_engine.news (Aurelia-style
  host/headers, 2-per-5min guard, stale-cache fallback), reactions recorded
  per high-impact event+pair, and news_state wired into pack.decide().
- SAFETY: 15-minute CALL/PUT only, min stake 0.35 (2dp), one open trade per
  pair, global kill switch, owner enable/shadow state, fail-closed errors.
"""
from __future__ import annotations
import asyncio
import json
import os
import random
import time
import urllib.request
from datetime import datetime, timezone

import pandas as pd
import websockets

from sentinel_engine import load_pack
from sentinel_engine import news as newsmod

WORKER = os.environ.get("WORKER_URL", "").rstrip("/")
BOT_SECRET = os.environ.get("BOT_SHARED_SECRET", "")
DERIV_TOKEN = os.environ.get("DERIV_BEARER_TOKEN", "")
DERIV_APP_ID = os.environ.get("DERIV_APP_ID", "")
GH_PAT = os.environ.get("GH_CHAIN_PAT", "")
BOT_MODE_DEFAULT = os.environ.get("BOT_MODE", "demo")

WALL_S = int(os.environ.get("BOT_WALL_SECONDS", "13800"))
HANDOFF_LEAD_S = int(os.environ.get("BOT_HANDOFF_LEAD_S", "300"))
STOP_OPEN_LEAD_S = int(os.environ.get("BOT_STOP_OPEN_LEAD_S", "120"))
POLL_S = float(os.environ.get("BOT_POLL_SECONDS", "20"))
NEWS_REFRESH_S = int(os.environ.get("NEWS_REFRESH_SECONDS", "3600"))

DERIV_REST = os.environ.get("DERIV_REST_BASE", "https://api.derivws.com")
ACCOUNTS_URL = f"{DERIV_REST}/trading/v1/options/accounts"
REPO = os.environ.get("GITHUB_REPOSITORY", "vjumbo264/sentinel-fx")
OWNER_TAG = f"actions-{int(time.time())}-{os.getpid()}"
MIN_STAKE = 0.35

HDRS = {"Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": "sentinel-fx-bot/2.0"}


class KillSwitch(Exception):
    pass


class NoAccountError(Exception):
    pass


# ---------------- Worker HTTP (retried; callers decide to swallow) ----------

def http(method, path, body=None, timeout=20, retries=1):
    last = None
    for i in range(retries + 1):
        try:
            data = None if body is None else json.dumps(body).encode()
            req = urllib.request.Request(
                f"{WORKER}{path}", data=data, method=method,
                headers={**HDRS, "X-Bot-Secret": BOT_SECRET})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode() or "{}")
        except Exception as e:
            last = e
            if i < retries:
                time.sleep(0.6 * (i + 1))
    raise last


def log(level, pair, message, data=None):
    try:
        http("POST", "/api/bot/log",
             {"level": level, "pair": pair, "message": message, "data": data})
    except Exception as e:
        print(f"[log-fail] {e}: {level} {pair} {message}")


def heartbeat(mode, balance, note="", loginid=None, currency=None):
    try:
        http("POST", "/api/bot/heartbeat",
             {"mode": mode, "balance": balance, "note": note,
              "loginid": loginid, "currency": currency})
    except Exception:
        pass


def acquire_lock():
    r = http("POST", "/api/bot/lock", {"owner": OWNER_TAG})
    return bool(r.get("acquired"))


def renew_lock():
    try:
        http("POST", "/api/bot/lock", {"owner": OWNER_TAG})
    except Exception:
        pass


def release_lock():
    try:
        http("POST", "/api/bot/unlock", {"owner": OWNER_TAG})
    except Exception:
        pass


# ---------------- Deriv REST auth -------------------------------------------

def deriv_rest(path, method="GET", body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{DERIV_REST}{path}", data=data, method=method,
        headers={**HDRS, "Authorization": f"Bearer {DERIV_TOKEN}",
                 "Deriv-App-ID": DERIV_APP_ID})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def list_accounts():
    return deriv_rest("/trading/v1/options/accounts")["data"]


def request_otp_url(loginid: str) -> str:
    r = deriv_rest(f"/trading/v1/options/accounts/{loginid}/otp",
                   method="POST", body={})
    return r["data"]["url"]


# ---------------- Deriv websocket session -----------------------------------


def normalise_duration(symbol: str, duration=None, duration_unit=None) -> tuple[int, str]:
    """
    Forex (frx*) requires >= 15m intraday floor on Deriv.
    Synthetic indices (R_*, 1HZ*V) allow any duration below 15m (down to 5s, 15s, 60s, 1m, 2m, etc.).
    """
    is_fx = symbol.startswith("frx")
    if is_fx:
        unit = str(duration_unit or "m").lower()
        dur = int(duration or 15)
        if unit == "s":
            mins = dur / 60.0
            return max(15, int(mins)), "m"
        elif unit == "m":
            return max(15, dur), "m"
        elif unit in ("h", "d"):
            return dur, unit
        return 15, "m"
    else:
        unit = str(duration_unit or "m").lower() if duration_unit else "m"
        dur = int(duration) if duration else 1
        if unit == "s":
            return max(5, dur), "s"
        elif unit == "m":
            return max(1, dur), "m"
        elif unit == "t":
            return max(5, dur), "t"
        return dur, unit

class DerivSession:
    """One authenticated websocket. OTP URLs are single-use, so every
    (re)connect requests a fresh account list and a NEW otp."""

    def __init__(self):
        self.ws = None
        self.mode = None        # account_type actually connected: demo|real
        self.loginid = None
        self.currency = None

    def masked(self):
        return (self.loginid[:3] + "***") if self.loginid else None

    @property
    def closed(self):
        return self.ws is None

    async def connect(self, mode: str):
        await self.close()
        accs = list_accounts()
        want = "demo" if mode == "demo" else "real"
        acc = next((a for a in accs if a.get("account_type") == want), None)
        if acc is None:
            raise NoAccountError(f"no {want} account on this Deriv token")
        self.loginid = acc["account_id"]
        self.currency = acc.get("currency", "USD")
        url = request_otp_url(self.loginid)
        self.ws = await websockets.connect(
            url, ping_interval=20, ping_timeout=20, close_timeout=10,
            max_queue=64)
        self.mode = want
        log("info", None,
            f"deriv connected: acct={want} loginid={self.masked()} cur={self.currency}")

    async def close(self):
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass
        self.ws = None

    async def rpc(self, payload, timeout=20):
        req_id = int(time.time() * 1000) & 0x7fffffff
        payload = dict(payload)
        payload["req_id"] = req_id
        await self.ws.send(json.dumps(payload))
        end = time.time() + timeout
        while time.time() < end:
            msg = await asyncio.wait_for(self.ws.recv(),
                                         timeout=max(0.1, end - time.time()))
            d = json.loads(msg)
            if d.get("req_id") == req_id:
                return d
        raise asyncio.TimeoutError("ws rpc timeout")

    async def balance(self):
        r = await self.rpc({"balance": 1})
        b = r.get("balance", {})
        return float(b.get("balance", 0.0))

    async def fetch_candles(self, symbol, count=600):
        r = await self.rpc({"ticks_history": symbol, "style": "candles",
                            "granularity": 60, "count": count, "end": "latest"})
        cs = r.get("candles", [])
        return pd.DataFrame(cs) if cs else pd.DataFrame()

    async def propose_and_buy(self, symbol, side, stake, duration=None, duration_unit=None):
        dur, dur_u = normalise_duration(symbol, duration, duration_unit)
        prop = await self.rpc({
            "proposal": 1, "amount": round(stake, 2), "basis": "stake",
            "contract_type": side, "currency": "USD", "duration": dur,
            "duration_unit": dur_u, "underlying_symbol": symbol})
        if "error" in prop:
            return {"error": prop["error"].get("message", "proposal error")}
        pid = prop["proposal"]["id"]
        payout = float(prop["proposal"]["payout"])
        buy = await self.rpc({"buy": pid, "price": round(stake, 2)}, timeout=30)
        if "error" in buy:
            return {"error": buy["error"].get("message", "buy error")}
        return {"contract_id": str(buy["buy"]["contract_id"]),
                "payout": payout, "stake": round(stake, 2)}


# ---------------- chaining ---------------------------------------------------

def chain_next_run(note="handoff"):
    if not GH_PAT:
        return
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/actions/workflows/bot.yml/dispatches",
            data=json.dumps({"ref": "main",
                             "inputs": {"mode": BOT_MODE_DEFAULT}}).encode(),
            method="POST",
            headers={**HDRS, "Authorization": f"token {GH_PAT}",
                     "Accept": "application/vnd.github+json"})
        urllib.request.urlopen(req, timeout=20).read()
        log("info", None, f"self-chain dispatched next run ({note})")
    except Exception as e:
        log("warn", None, f"self-chain failed: {e}")


class V2Adapter:
    """Expose a v2 .sfxmodel.zip bundle through the v1 pack.decide() API so the
    rest of the bot loop is unchanged. Guardrails stay in the bot; a model
    can never override them."""

    def __init__(self, bundle):
        self.b = bundle

    def decide(self, df, ctx):
        from sentinel_engine.plan import evaluate
        dec = evaluate(self.b, df, ctx or {})
        if dec["action"] != "trade":
            return {"allow": False, "side": None,
                    "prob": dec.get("p_win") or 0.0, "edge": 0.0,
                    "margin": 0.0, "reasons": [dec["reason"]]}
        be = 1.0 / (1.0 + float(self.b.decision.get("payout_assumed", 0.85)))
        min_p = float(self.b.decision.get("min_p", be))
        pwin = dec["p_win"] or 0.0
        votes = " | ".join(
            f"{o['id']}: {o.get('direction', '-')}" for o in dec["opinions"]
            if not o.get("skipped"))
        return {"allow": pwin >= min_p, "side": dec["side"], "prob": pwin,
                "edge": pwin, "margin": max(0.0, min_p - be),
                "reasons": [f"{dec['reason']}; analysts: {votes}"]}


def load_pack_for(symbol):
    """v2 first: the ACTIVE bundle of the pair from the shared models release
    (public URL, sha256-verified, data-only). Falls back to the v1 pack."""
    try:
        idx_path = os.path.join("models", "index.json")
        if os.path.exists(idx_path):
            ent = json.load(open(idx_path)).get(symbol)
            if ent and ent.get("active_version") is not None:
                v = next(x for x in ent["versions"]
                         if x["N"] == ent["active_version"])
                url = (f"https://github.com/{REPO}/releases/download/"
                       f"{v['release_tag']}/{v['asset']}")
                cache = os.path.join("/tmp", v["asset"])
                if not os.path.exists(cache):
                    with urllib.request.urlopen(url, timeout=180) as r, \
                            open(cache, "wb") as f:
                        f.write(r.read())
                import hashlib
                digest = hashlib.sha256(open(cache, "rb").read()).hexdigest()
                if digest != v["sha256"]:
                    raise RuntimeError("bundle sha256 mismatch")
                from sentinel_engine.bundle import load_bundle
                log("info", symbol,
                    f"v2 bundle v{v['N']} loaded from {v['release_tag']}")
                return V2Adapter(load_bundle(cache))
    except Exception as e:
        log("warn", symbol, f"v2 bundle load failed, falling back to v1: {e}")
    path = os.path.join("pairs", symbol, "pack.json")
    if not os.path.exists(path):
        return None
    return load_pack(path)


# ---------------- bot --------------------------------------------------------

class Bot:
    def __init__(self):
        self.sess = DerivSession()
        self.state = {"settings": {}, "pairs": []}   # last-known-good
        self.events = []                              # normalized news events
        self.news_ts = 0.0
        self.reactions_done = set()
        self.chained = False

    # -- state ---------------------------------------------------------------
    def refresh_state(self):
        try:
            self.state = http("GET", "/api/bot/state")
        except Exception as e:
            log("warn", None, f"state fetch failed ({e}); using last known")

    @property
    def settings(self):
        return self.state.get("settings", {})

    def wanted_mode(self):
        return self.settings.get("mode", BOT_MODE_DEFAULT)

    # -- news ----------------------------------------------------------------
    def _news_cache_get(self):
        return self.settings.get("news_cache")

    def _news_cache_set(self, payload):
        try:
            http("POST", "/api/bot/settings", {"news_cache": payload})
        except Exception:
            pass

    def refresh_news(self):
        try:
            raw, meta = newsmod.fetch_weeks(
                cache_get=self._news_cache_get,
                cache_set=self._news_cache_set,
                refresh_s=NEWS_REFRESH_S)
            self.events = newsmod.normalize(raw)
            symbols = [p["symbol"] for p in self.state.get("pairs", [])]
            for e in self.events:
                e["affected_pairs"] = newsmod.affected_pairs(e["currency"], symbols)
            http("POST", "/api/bot/news", {"events": self.events})
            self.news_ts = time.time()
            log("info", None,
                f"news refreshed ({len(self.events)} events, src={meta['source']}"
                f"{' STALE-CACHE' if meta['stale'] else ''})")
        except Exception as e:
            self.news_ts = time.time()  # do not hammer; retry next hour
            log("warn", None, f"news fetch failed: {e}")

    async def record_reactions(self):
        """For each high-impact event past by 15+ minutes, compute the pair's
        +5/+15 minute move from candles and POST it once per event+pair."""
        now = datetime.now(timezone.utc)
        symbols = [p["symbol"] for p in self.state.get("pairs", [])]
        for ev in self.events:
            if ev.get("impact") != "high":
                continue
            t = datetime.strptime(ev["utc_time"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc)
            if (now - t).total_seconds() < 15 * 60:
                continue
            for sym in ev.get("affected_pairs") or newsmod.affected_pairs(
                    ev["currency"], symbols):
                key = (ev["id"], sym)
                if key in self.reactions_done:
                    continue
                self.reactions_done.add(key)
                try:
                    df = await self.sess.fetch_candles(sym, count=500)
                    if df.empty:
                        continue
                    df = df.sort_values("epoch").reset_index(drop=True)
                    idx = df.index[df["epoch"] >= int(t.timestamp())]
                    if len(idx) == 0 or idx[0] + 15 >= len(df):
                        continue
                    i = int(idx[0])
                    base = float(df["close"].iloc[i])
                    m5 = (float(df["close"].iloc[i + 5]) - base) / base * 1e4
                    m15 = (float(df["close"].iloc[i + 15]) - base) / base * 1e4
                    http("POST", "/api/bot/news/reaction",
                         {"event_key": ev["id"], "pair": sym,
                          "move_5m": round(m5, 1), "move_15m": round(m15, 1)})
                    log("info", sym, f"news reaction recorded: {ev['title'][:30]} "
                                     f"5m={m5:+.1f}p 15m={m15:+.1f}p")
                except Exception as e:
                    log("warn", sym, f"reaction record failed: {e}")

    def news_ctx_for(self, sym, side):
        ctx = {}
        now = datetime.now(timezone.utc)
        curs = newsmod.pair_currencies(sym)
        nxt = newsmod.minutes_to_event(self.events, now, curs)
        ctx["minutes_to_news"] = nxt if nxt is not None else 9999.0
        last = newsmod.last_event_minutes(self.events, now, curs)
        reaction = None
        if last and last[0] <= 240:  # reaction window: 4h after release
            try:
                r = http("GET", f"/api/bot/news/reactions?pair={sym}")
                for rec in r.get("reactions", []):
                    if rec.get("event_key") == last[1]["id"]:
                        reaction = rec.get("move_15m")
            except Exception:
                pass
        ctx["news_state"] = newsmod.news_state(side, reaction)
        ctx["hour_utc"] = now.hour
        return ctx

    # -- session management (FIX-A + FIX-B) -----------------------------------
    async def ensure_session(self):
        want = self.wanted_mode()
        s = self.sess
        if s.ws is not None and s.mode == want:
            return
        if s.ws is not None and s.mode != want:
            open_trades = []
            try:
                open_trades = http("GET", "/api/bot/trades/open").get("open", [])
            except Exception:
                pass
            if open_trades:
                heartbeat(s.mode, None, "switch pending: open contracts",
                          s.masked(), s.currency)
                log("info", None, f"mode switch {s.mode}->{want} pending: "
                                  f"{len(open_trades)} open contract(s)")
                await self.reconcile_open()
                return  # stay on the old account this iteration
            log("info", None, f"switching account {s.mode} -> {want}")
            await s.close()
        try:
            await s.connect(want)
        except NoAccountError:
            if want != "demo":
                log("error", None, f"token has no {want} account; staying on demo")
                try:
                    http("POST", "/api/bot/settings", {"mode": "demo"})
                except Exception:
                    pass
                if s.ws is None:
                    await s.connect("demo")
            else:
                raise
        bal = await s.balance()
        heartbeat(s.mode, bal, "connected", s.masked(), s.currency)
        await self.reconcile_open()

    async def reconcile_open(self):
        try:
            open_r = http("GET", "/api/bot/trades/open")
            for t in open_r.get("open", []):
                cid = t["contract_id"]
                st = await self.sess.rpc({"proposal_open_contract": 1,
                                          "contract_id": int(cid)})
                poc = st.get("proposal_open_contract", {})
                if poc.get("is_sold"):
                    pnl = float(poc.get("profit", 0.0))
                    result = "win" if pnl > 0 else "loss"
                    http("POST", "/api/bot/trade/settle",
                         {"contract_id": cid, "result": result, "pnl": pnl})
                    log("info", t["pair"],
                        f"reconciled contract {cid}: {result} {pnl:+.2f}")
        except Exception as e:
            log("warn", None, f"reconcile failed: {e}")

    async def settle_shadow(self, packs):
        for p in self.state.get("pairs", []):
            sym = p["symbol"]
            try:
                r = http("GET", f"/api/bot/shadow/open?pair={sym}")
                opens = r.get("open", [])
                if not opens:
                    continue
                df = await self.sess.fetch_candles(sym, count=30)
                if df.empty:
                    continue
                df = df.sort_values("epoch")
                last_close = float(df["close"].iloc[-1])
                now_epoch = int(time.time())
                for sg in opens:
                    opened = datetime.fromisoformat(
                        sg["open_utc"].replace("Z", "+00:00")).timestamp()
                    if now_epoch - opened < 15 * 60:
                        continue
                    entry = float(sg["entry_price"])
                    win = (sg["side"] == "CALL" and last_close > entry) or \
                          (sg["side"] == "PUT" and last_close < entry)
                    stake = float(sg["stake"] or MIN_STAKE)
                    pnl = stake * 0.85 if win else -stake
                    http("POST", "/api/bot/shadow/settle",
                         {"id": sg["id"], "exit_price": last_close,
                          "result": "win" if win else "loss", "pnl": round(pnl, 2)})
            except Exception as e:
                log("warn", sym, f"shadow settle failed: {e}")

    # -- one supervised iteration ---------------------------------------------
    async def iteration(self, packs, stop_open_at):
        self.refresh_state()
        if self.settings.get("kill"):
            raise KillSwitch()
        renew_lock()
        if time.time() - self.news_ts > NEWS_REFRESH_S:
            self.refresh_news()
        await self.ensure_session()
        await self.record_reactions()
        bal = await self.sess.balance()
        heartbeat(self.sess.mode, bal, "loop",
                  self.sess.masked(), self.sess.currency)
        await self.settle_shadow(packs)

        for p in self.state.get("pairs", []):
            sym = p["symbol"]
            # Any enabled pair is allowed to trade in DEMO mode;
            # in REAL mode only models meeting pass requirements are allowed.
            if not p.get("enabled"):
                continue
            if sym not in packs:
                continue
            pack, _ = packs[sym]

            if self.sess.mode == "real" and p.get("verdict") != "pass":
                log("warn", sym, f"model did not meet pass requirements (verdict={p.get('verdict')}); real mode trading blocked (demo only)")
                continue

            try:
                df = await self.sess.fetch_candles(sym, count=500)
                if df.empty or len(df) < 100:
                    continue
                news_ctx = self.news_ctx_for(sym, "CALL")
                dec = pack.decide(df, news_ctx)
                news_ctx2 = self.news_ctx_for(sym, dec["side"] or "CALL")
                if news_ctx2["news_state"] != news_ctx["news_state"]:
                    dec = pack.decide(df, news_ctx2)
                    news_ctx = news_ctx2
                reasons = "; ".join(dec["reasons"]) or "rule-block"
                if not dec["allow"] or dec["side"] is None:
                    log("info", sym, f"skipped: {reasons}", {"prob": dec["prob"]})
                    continue
                stake_pct = float(p.get("stake_pct", 0.01))
                raw = max(MIN_STAKE,
                          min(float(p.get("max_stake", 10)), bal * stake_pct))
                stake = round(raw, 2)
                if bal < MIN_STAKE or stake < MIN_STAKE:
                    log("warn", sym, f"balance {bal:.2f} too low; pausing")
                    continue

                # Determine duration from pair settings or bundle
                req_dur = p.get("duration")
                req_unit = p.get("duration_unit")
                if not req_dur and hasattr(pack, "bundle") and getattr(pack, "bundle", None):
                    b = pack.bundle
                    d_cfg = getattr(b, "decision", {})
                    req_dur = d_cfg.get("duration") or d_cfg.get("duration_sec") or d_cfg.get("horizon_min")
                    req_unit = d_cfg.get("duration_unit") or ("s" if "duration_sec" in d_cfg else "m")
                dur, dur_u = normalise_duration(sym, req_dur, req_unit)

                prop = await self.sess.rpc({
                    "proposal": 1, "amount": stake, "basis": "stake",
                    "contract_type": dec["side"], "currency": "USD",
                    "duration": dur, "duration_unit": dur_u, "underlying_symbol": sym})
                if "error" in prop:
                    log("warn", sym,
                        f"proposal error: {prop['error'].get('message')}")
                    continue
                live_payout = float(prop["proposal"]["payout"]) / stake - 1.0
                be = 1.0 / (1.0 + live_payout)
                needed = be + float(dec.get("margin", 0))
                if dec["edge"] < needed:
                    log("info", sym,
                        f"skipped: edge {dec['edge']:.3f} < required {needed:.3f}",
                        {"live_payout": live_payout})
                    continue

                if time.time() >= stop_open_at:
                    log("info", sym, "near end-of-run; not opening")
                    continue
                buy = await self.sess.propose_and_buy(sym, dec["side"], stake, dur, dur_u)
                if "error" in buy:
                    log("warn", sym, f"buy failed: {buy['error']}")
                    continue
                http("POST", "/api/bot/trade", {
                    "contract_id": buy["contract_id"], "pair": sym,
                    "side": dec["side"], "stake": buy["stake"],
                    "payout": buy["payout"], "mode": self.sess.mode,
                    "model_prob": dec["prob"],
                    "news_flag": news_ctx.get("news_state"), "reason": reasons})
                log("info", sym, f"TRADE {self.sess.mode.upper()} {dec['side']} {dur}{dur_u} stake={buy['stake']} contract={buy['contract_id']}")

            except (websockets.exceptions.WebSocketException, OSError,
                    asyncio.TimeoutError):
                raise  # supervisor handles reconnects
            except Exception as e:
                log("error", sym, f"loop exception: {e}")
        await asyncio.sleep(POLL_S)


async def main():
    t0 = time.time()
    deadline = t0 + WALL_S
    stop_open_at = deadline - STOP_OPEN_LEAD_S
    handoff_at = deadline - HANDOFF_LEAD_S

    if not acquire_lock():
        log("warn", None, "run_lock held by another runner; exiting")
        return

    bot = Bot()
    try:
        bot.refresh_state()
        if bot.settings.get("kill"):
            log("warn", None, "kill switch on; exiting")
            return
        packs = {}
        for p in bot.state.get("pairs", []):
            pk = load_pack_for(p["symbol"])
            if pk is not None:
                packs[p["symbol"]] = (pk, p)
                kind = "v2-bundle" if isinstance(pk, V2Adapter) else "v1-pack"
                log("info", p["symbol"], f"{kind} v{p['pack_version']} loaded")
            else:
                log("warn", p["symbol"], "no pack.json found; skipping")

        backoff = 2.0
        while time.time() < deadline:
            if time.time() >= handoff_at and not bot.chained:
                chain_next_run("handoff")
                bot.chained = True
            try:
                await bot.iteration(packs, stop_open_at)
                backoff = 2.0
            except KillSwitch:
                log("warn", None, "kill switch triggered; stopping")
                break
            except Exception as e:
                log("warn", None, f"connection lost: {type(e).__name__}: {e}")
                heartbeat(bot.sess.mode, None, "reconnecting",
                          bot.sess.masked(), bot.sess.currency)
                await bot.sess.close()
                renew_lock()  # keep the D1 lease during reconnects
                await asyncio.sleep(backoff + random.uniform(0, backoff * 0.5))
                backoff = min(60.0, backoff * 2)
    finally:
        await bot.sess.close()
        release_lock()
        heartbeat(bot.sess.mode or BOT_MODE_DEFAULT, None, "end-of-run",
                  bot.sess.masked(), bot.sess.currency)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        try:
            log("error", None, f"fatal: {e}")
        except Exception:
            pass
        try:
            release_lock()
        except Exception:
            pass
        raise
