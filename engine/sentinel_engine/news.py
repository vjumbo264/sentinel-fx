"""
sentinel_engine.news
====================
ForexFactory weekly calendar helpers + news features.
Schema (verified): list of {"title","country","date","impact","forecast","previous"}
where `country` is actually the CURRENCY code (USD, EUR, ...) and `date` is an
ISO8601 string carrying a US/Eastern offset. No 'actual' value is provided.
Fetch at most once or twice per run; handle 429; set a normal User-Agent.
"""
from __future__ import annotations
import json
import urllib.request
from datetime import datetime, timezone

URL_THIS = "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json"
URL_NEXT = "https://cdn-nfs.faireconomy.media/ff_calendar_nextweek.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def fetch_calendar(url: str = URL_THIS, timeout: int = 30) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf8"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RuntimeError("calendar rate-limited (429); use cache")
        raise
    return data if isinstance(data, list) else []


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


def pair_currencies(symbol: str) -> set[str]:
    """frxEURUSD -> {EUR, USD}"""
    s = symbol.replace("frx", "").upper()
    return {s[:3], s[3:6]}


def news_state(signal_side: str, reaction: float | None) -> str:
    """reaction = signed +15m price move of the pair after the last high-impact
    event (positive = up). 'for' if it agrees with the signal direction."""
    if reaction is None:
        return "none"
    if signal_side == "CALL":
        return "for" if reaction > 0 else "against"
    return "for" if reaction < 0 else "against"
