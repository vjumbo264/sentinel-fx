"""
sentinel_engine.news
====================
ForexFactory weekly calendar helpers + news features.

Fetch strategy mirrors the owner's KNOWN-WORKING Aurelia bot
(github.com/motionssalt/aurelia calendar.js):
  * primary host  https://nfs.faireconomy.media/ff_calendar_thisweek.json
    (and ff_calendar_nextweek.json); the cdn-nfs host is only a fallback.
  * headers: Accept-only FIRST, then a browser User-Agent if that fails.
  * at most 2 requests per 5 minutes, refresh at most hourly (enforced here).
  * response validated as a list of {title, country, date, ...} objects.

The caller may pass cache_get()/cache_set(payload) callables so a stale
cached calendar is used when a refresh fails; the REAL exception text and
HTTP status are always included in the raised error message.

Schema (verified): list of {"title","country","date","impact","forecast",
"previous"} where `country` is actually the CURRENCY code (USD, EUR, ...)
and `date` is an ISO8601 string carrying a US/Eastern offset.
"""
from __future__ import annotations
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

URL_THIS = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
URL_NEXT = "https://nfs.faireconomy.media/ff_calendar_nextweek.json"
URL_THIS_CDN = "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json"
URL_NEXT_CDN = "https://cdn-nfs.faireconomy.media/ff_calendar_nextweek.json"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126 Safari/537.36")

_REQUEST_TS: list[float] = []  # rate-limit guard bookkeeping (max 2 per 300 s)


def _rate_take(max_per_300s: int) -> None:
    now = time.time()
    _REQUEST_TS[:] = [t for t in _REQUEST_TS if now - t < 300]
    if len(_REQUEST_TS) >= max_per_300s:
        raise RuntimeError("news fetch failed: local rate-limit guard "
                           f"({max_per_300s} requests per 5 minutes)")
    _REQUEST_TS.append(now)


def _validate_shape(data) -> list[dict]:
    if not isinstance(data, list):
        raise RuntimeError(f"news fetch failed: unexpected schema "
                           f"(expected array, got {type(data).__name__})")
    valid = [ev for ev in data if isinstance(ev, dict)
             and isinstance(ev.get("title"), str)
             and isinstance(ev.get("country"), str)
             and isinstance(ev.get("date"), str)]
    if data and not valid:
        raise RuntimeError("news fetch failed: schema mismatch - no valid events")
    return valid


def fetch_calendar(url: str = URL_THIS, timeout: int = 30,
                   max_per_300s: int = 2) -> list[dict]:
    """Fetch one weekly calendar file. Accept-only first (Aurelia), then a
    browser UA. Errors always carry the real status/exception text."""
    _rate_take(max_per_300s)
    last = "no attempt made"
    for headers in ({"Accept": "application/json"},
                    {"Accept": "application/json", "User-Agent": UA}):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf8"))
            return _validate_shape(data)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} {e.reason} from {url}"
            if e.code == 429:
                break  # rate-limited: retrying with another UA will not help
        except Exception as e:  # network / json errors
            last = f"{type(e).__name__}: {e} (url={url})"
    raise RuntimeError(f"news fetch failed: {last}")


def fetch_weeks(cache_get=None, cache_set=None, refresh_s: int = 3600,
                timeout: int = 30) -> tuple[list[dict], dict]:
    """Fetch this week + next week (next week may legitimately be empty).

    cache_get() -> {"fetched_utc": iso, "events": [...] } | None
    cache_set(payload) persists the fresh copy.
    Returns (raw_events, meta) where meta = {fetched_utc, stale, source, error}.
    On refresh failure with a cache present, returns the STALE cache and the
    real error text in meta["error"]. With no cache the exception propagates.
    """
    now = datetime.now(timezone.utc)
    cached = cache_get() if cache_get else None
    if cached and cached.get("fetched_utc"):
        try:
            age = (now - datetime.fromisoformat(
                cached["fetched_utc"].replace("Z", "+00:00"))).total_seconds()
        except Exception:
            age = refresh_s + 1
        if age < refresh_s:
            return cached.get("events", []), {
                "fetched_utc": cached["fetched_utc"], "stale": False,
                "source": "cache", "error": None}

    error = None
    try:
        events = fetch_calendar(URL_THIS, timeout=timeout)
        try:
            events = events + fetch_calendar(URL_NEXT, timeout=timeout)
        except RuntimeError:
            pass  # next-week file is optional / often empty
        payload = {"fetched_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "events": events}
        if cache_set:
            cache_set(payload)
        return events, {"fetched_utc": payload["fetched_utc"], "stale": False,
                        "source": URL_THIS, "error": None}
    except RuntimeError as e:
        error = str(e)
        # last resort: the cdn-nfs mirror
        try:
            events = fetch_calendar(URL_THIS_CDN, timeout=timeout)
            payload = {"fetched_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "events": events}
            if cache_set:
                cache_set(payload)
            return events, {"fetched_utc": payload["fetched_utc"],
                            "stale": False, "source": URL_THIS_CDN,
                            "error": None}
        except RuntimeError as e2:
            error = f"{error} | cdn fallback: {e2}"

    if cached:
        return cached.get("events", []), {
            "fetched_utc": cached.get("fetched_utc"), "stale": True,
            "source": "stale-cache", "error": error}
    raise RuntimeError(error)


def normalize(events: list[dict]) -> list[dict]:
    """Return list of {id, utc_time (ISO Z), currency, title, impact, forecast, previous}."""
    out = []
    for ev in events:
        d = ev.get("date")
        if not d:
            continue
        dt = datetime.fromisoformat(d.replace("Z", "+00:00")).astimezone(timezone.utc)
        cur = (ev.get("country") or "").upper()
        out.append({
            "id": f"{cur}|{dt.strftime('%Y%m%dT%H%M')}Z|{ev.get('title','')[:40]}",
            "utc_time": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "currency": cur,
            "title": ev.get("title", ""),
            "impact": (ev.get("impact") or "").lower(),
            "forecast": ev.get("forecast", ""),
            "previous": ev.get("previous", ""),
        })
    return out


def affected_pairs(currency: str, symbols: list[str]) -> list[str]:
    """A USD event affects every pair containing USD."""
    cur = currency.upper()
    return [s for s in symbols if cur in s.upper()]


def minutes_to_event(events: list[dict], now_utc: datetime, currencies: set[str],
                     impacts=("high",)) -> float | None:
    """Minutes from now to the next matching event for given currencies."""
    best = None
    for ev in events:
        if ev["currency"] not in currencies or ev["impact"] not in impacts:
            continue
        t = datetime.strptime(ev["utc_time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        m = (t - now_utc).total_seconds() / 60.0
        if m >= 0 and (best is None or m < best):
            best = m
    return best


def last_event_minutes(events: list[dict], now_utc: datetime, currencies: set[str],
                       impacts=("high",)) -> tuple[float, dict] | None:
    """(minutes since, event) of the most recent matching past event."""
    best = None
    for ev in events:
        if ev["currency"] not in currencies or ev["impact"] not in impacts:
            continue
        t = datetime.strptime(ev["utc_time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        m = (now_utc - t).total_seconds() / 60.0
        if m >= 0 and (best is None or m < best[0]):
            best = (m, ev)
    return best


def pair_currencies(symbol: str) -> set[str]:
    """frxEURUSD -> {EUR, USD}"""
    s = symbol.replace("frx", "").upper()
    return {s[:3], s[3:6]}


def event_affects(event: dict, symbol: str) -> bool:
    return (event.get("currency") or "").upper() in pair_currencies(symbol)


def news_state(signal_side: str, reaction: float | None) -> str:
    """reaction = signed +15m price move of the pair after the last high-impact
    event (positive = up). 'for' if it agrees with the signal direction."""
    if reaction is None:
        return "none"
    if signal_side == "CALL":
        return "for" if reaction > 0 else "against"
    return "for" if reaction < 0 else "against"


# ---------------- archive helpers (NEWS task) --------------------------------

def _ev_ts(ev: dict) -> datetime:
    return datetime.strptime(ev["utc_time"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc)


def news_as_known_at(events: list[dict], t: datetime) -> list[dict]:
    """Point-in-time view: only events first seen at/before t, with forecast
    revisions after t stripped (no hindsight bias in simulation)."""
    out = []
    for ev in events:
        fs = ev.get("first_seen_utc")
        if fs and fs > t.strftime("%Y-%m-%dT%H:%M:%SZ"):
            continue
        hist = [h for h in ev.get("forecast_history", [])
                if h.get("utc", "") <= t.strftime("%Y-%m-%dT%H:%M:%SZ")]
        e = dict(ev)
        if hist:
            e["forecast"] = hist[-1].get("forecast")
            e["previous"] = hist[-1].get("previous")
        e.pop("forecast_history", None)
        out.append(e)
    return out


def upcoming(events: list[dict], t: datetime, currencies: set[str],
             impacts=("high", "medium")) -> list[dict]:
    """Future events for the given currencies, soonest first."""
    out = [ev for ev in events
           if ev.get("currency") in currencies
           and ev.get("impact", "") in impacts
           and _ev_ts(ev) >= t]
    return sorted(out, key=_ev_ts)


def recent(events: list[dict], t: datetime, currencies: set[str],
           window_min: int = 120, impacts=("high", "medium")) -> list[dict]:
    """Events within window_min BEFORE t (most recent last)."""
    lo = t.timestamp() - window_min * 60
    out = [ev for ev in events
           if ev.get("currency") in currencies
           and ev.get("impact", "") in impacts
           and lo <= _ev_ts(ev).timestamp() <= t.timestamp()]
    return sorted(out, key=_ev_ts)


def reaction_stats(candles: list[dict], events: list[dict], symbol: str,
                   horizons=(5, 15, 30)) -> dict:
    """Price move (in pips of price, x1e4) at +h minutes after each event that
    affects `symbol`, grouped by (title, impact, currency). candles: sorted
    list of {epoch, open, high, low, close}."""
    epochs = [int(c["epoch"]) for c in candles]
    import bisect
    groups: dict[tuple, dict] = {}
    for ev in events:
        if not event_affects(ev, symbol):
            continue
        t0 = int(_ev_ts(ev).timestamp())
        i = bisect.bisect_left(epochs, t0)
        if i >= len(epochs):
            continue
        base = float(candles[i]["close"])
        if base == 0:
            continue
        moves = {}
        for h in horizons:
            j = bisect.bisect_left(epochs, t0 + h * 60)
            if j < len(epochs):
                moves[h] = (float(candles[j]["close"]) - base) / base * 1e4
        if not moves:
            continue
        key = (ev.get("title", ""), ev.get("impact", ""), ev.get("currency", ""))
        g = groups.setdefault(key, {"n": 0, **{f"move_{h}m": [] for h in horizons}})
        g["n"] += 1
        for h, m in moves.items():
            g[f"move_{h}m"].append(round(m, 1))
    return {"|".join(k): v for k, v in groups.items()}
