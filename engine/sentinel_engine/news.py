"""News logic. Event -> affected pairs by currency; state for the decision pipeline.

news_rules (from the pack):
{
  "block_if_against": true,
  "against_extra_margin": 0.04,
  "with_boost": 0.0,
  "blackout_minutes_before": 15,
  "blackout_minutes_after": 5,
  "reaction_threshold_pips": 0
}
"""
import datetime as dt

def currencies_of(symbol: str):
    s = symbol[3:] if symbol.startswith("frx") else symbol
    return s[:3], s[3:6]

def event_affects(event_currency: str, symbol: str) -> bool:
    return event_currency in currencies_of(symbol)

def news_state(now_utc: dt.datetime, events: list, symbol: str, rules: dict, reactions: dict | None = None):
    """events: list of dicts {utc_time (epoch s), currency, impact, title}.
    Returns dict(minutes_to_next_high, blackout, last_reaction_pips)."""
    base, quote = currencies_of(symbol)
    mins_next, blackout = None, False
    bb, ba = rules.get("blackout_minutes_before", 0), rules.get("blackout_minutes_after", 0)
    for e in events:
        if str(e.get("impact", "")).lower() not in ("high", "3", "high impact"):
            continue
        if not event_affects(e.get("currency", ""), symbol):
            continue
        dm = (e["utc_time"] - now_utc.timestamp()) / 60.0
        if dm >= 0 and (mins_next is None or dm < mins_next):
            mins_next = dm
        if -ba <= dm <= bb:
            blackout = True
    last_react = None
    if reactions:
        vals = [abs(v.get("move_pips", 0.0)) for k, v in reactions.items() if v.get("pair") == symbol]
        if vals:
            last_react = max(vals[-5:])
    return {"minutes_to_next_high": mins_next, "blackout": blackout, "last_reaction_pips": last_react}
