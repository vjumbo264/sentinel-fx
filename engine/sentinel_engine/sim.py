"""
sentinel_engine.sim — replay a bundle (or v1 pack) over history exactly as the
live bot would (MODEL task M6).

Entry = open of the next 1m candle after the decision; expiry = close of the
candle +15m later; tie = loss. News is shown only as the live system would
know it (news_as_known_at). Reports trades, win rate with Wilson 95% CI,
break-even, edge, equity curve, max drawdown, and breakdowns by confidence
bucket / analyst agreement / news state. Fast: vectorized decisions.

replay(bundle_or_pack, candles, news_events=None, payout=0.85,
       decision_every=1, stake=1.0) -> dict
"""
from __future__ import annotations
import math


def wilson(wins: int, n: int, z: float = 1.96):
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def break_even(payout: float) -> float:
    return 1.0 / (1.0 + payout)


def replay(bundle, candles, news_events=None, payout: float = 0.85,
           decision_every: int = 1, stake: float = 1.0,
           min_conf: float | None = None):
    """candles: list of {epoch,open,high,low,close} ascending, 1m bars."""
    import pandas as pd
    from .plan import evaluate as plan_eval
    from . import news as newsmod

    df = pd.DataFrame(candles).sort_values("epoch").reset_index(drop=True)
    n = len(df)
    warm = 120
    trades, equity, curve = [], 0.0, []
    for i in range(warm, n - 16, decision_every):
        ctx = {}
        if news_events:
            t = pd.to_datetime(df["epoch"].iloc[i], unit="s", utc=True).to_pydatetime()
            known = newsmod.news_as_known_at(news_events, t)
            curs = newsmod.pair_currencies(bundle.symbol or "frxEURUSD")
            m = newsmod.minutes_to_event(known, t, curs)
            ctx = {"minutes_to_news": m if m is not None else 9999.0}
        try:
            dec = plan_eval(bundle, df.iloc[: i + 1], ctx)
        except Exception:
            continue
        if dec["action"] != "trade":
            continue
        pwin = dec["p_win"]
        if min_conf is not None and (pwin is None or pwin < min_conf):
            continue
        entry = float(df["open"].iloc[i + 1])
        exitp = float(df["close"].iloc[i + 15])
        side = dec["side"]
        win = (side == "CALL" and exitp > entry) or (side == "PUT" and exitp < entry)
        if exitp == entry:
            win = False  # tie = loss
        pnl = stake * payout if win else -stake
        equity += pnl
        agree = sum(1 for o in dec["opinions"] if not o.get("skipped")
                    and o["direction"] == ("up" if side == "CALL" else "down"))
        trades.append({"i": i, "side": side, "p_win": pwin, "win": win,
                       "pnl": pnl, "agree": agree, "n_opinions": len(dec["opinions"])})
        curve.append(equity)
    wins = sum(1 for t in trades if t["win"])
    nt = len(trades)
    wr = wins / nt if nt else 0.0
    lo, hi = wilson(wins, nt)
    be = break_even(payout)
    peak, mdd = 0.0, 0.0
    for e in curve:
        peak = max(peak, e)
        mdd = max(mdd, peak - e)
    # payout sensitivity
    def at(p):
        w = sum(1 for t in trades if t["win"])
        return {"payout": p, "edge": (w / nt if nt else 0) - break_even(p)}
    buckets = {}
    for t in trades:
        b = round((t["p_win"] or 0) * 10) / 10
        buckets.setdefault(b, [0, 0])
        buckets[b][1] += 1
        buckets[b][0] += 1 if t["win"] else 0
    return {
        "trades": nt, "wins": wins, "win_rate": round(wr, 4),
        "wilson95": [round(lo, 4), round(hi, 4)],
        "break_even": round(be, 4), "edge": round(wr - be, 4),
        "final_equity": round(equity, 2), "max_drawdown": round(mdd, 2),
        "payout_sensitivity": [at(payout - 0.05), at(payout), at(payout + 0.05)],
        "by_confidence_bucket": {str(k): {"wins": v[0], "n": v[1],
                                          "win_rate": round(v[0] / v[1], 4)}
                                 for k, v in sorted(buckets.items())},
        "verdict": "pass" if (nt >= 60 and lo > be) else "fail",
    }
