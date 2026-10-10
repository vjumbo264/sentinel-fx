"""
sentinel_engine.indicators
==========================
Pure-pandas/numpy technical indicator library for Deriv forex candles.
All functions take and return pandas objects indexed like the input.
NO volume (Deriv forex candles have none). All functions are strictly
causal: output at index i depends only on inputs at index <= i.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

__all__ = [
    "sma", "ema", "wma", "rsi", "macd", "bollinger", "atr", "true_range",
    "stochastic", "adx", "cci", "willr", "roc", "mom", "keltner", "donchian",
    "ichimoku", "pivots", "rolling_volatility", "rolling_skew", "rolling_kurt",
    "zscore", "rolling_rank", "session_features", "multi_tf_resample",
    "candle_patterns",
]


def _s(x) -> pd.Series:
    if isinstance(x, pd.Series):
        return x.astype(float)
    return pd.Series(x, dtype=float)


# ---------------------------------------------------------------- moving averages
def sma(close, period: int) -> pd.Series:
    return _s(close).rolling(int(period), min_periods=int(period)).mean()


def ema(close, period: int) -> pd.Series:
    return _s(close).ewm(span=int(period), adjust=False, min_periods=int(period)).mean()


def wma(close, period: int) -> pd.Series:
    p = int(period)
    w = np.arange(1, p + 1, dtype=float)
    return _s(close).rolling(p, min_periods=p).apply(lambda v: float(np.dot(v, w) / w.sum()), raw=True)


# ---------------------------------------------------------------- RSI (Wilder)
def rsi(close, period: int = 14) -> pd.Series:
    c = _s(close)
    d = c.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    roll_up = up.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    roll_dn = dn.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = roll_up / roll_dn.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    out = out.where(roll_dn != 0.0, 100.0)  # all-gains edge case
    return out


# ---------------------------------------------------------------- MACD
def macd(close, fast: int = 12, slow: int = 26, signal: int = 9):
    c = _s(close)
    line = ema(c, fast) - ema(c, slow)
    sig = line.ewm(span=int(signal), adjust=False, min_periods=int(signal)).mean()
    hist = line - sig
    return {"macd": line, "signal": sig, "hist": hist}


# ---------------------------------------------------------------- Bollinger
def bollinger(close, period: int = 20, mult: float = 2.0):
    c = _s(close)
    mid = sma(c, period)
    sd = c.rolling(period, min_periods=period).std(ddof=0)
    upper = mid + mult * sd
    lower = mid - mult * sd
    width = (upper - lower) / mid
    pctb = (c - lower) / (upper - lower)
    return {"mid": mid, "upper": upper, "lower": lower, "width": width, "pctb": pctb}


# ---------------------------------------------------------------- ATR
def true_range(high, low, close) -> pd.Series:
    h, l, c = _s(high), _s(low), _s(close)
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr


def atr(high, low, close, period: int = 14) -> pd.Series:
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


# ---------------------------------------------------------------- Stochastic
def stochastic(high, low, close, k: int = 14, d: int = 3, smooth: int = 3):
    h, l, c = _s(high), _s(low), _s(close)
    hh = h.rolling(k, min_periods=k).max()
    ll = l.rolling(k, min_periods=k).min()
    raw_k = 100.0 * (c - ll) / (hh - ll).replace(0.0, np.nan)
    k_s = raw_k.rolling(smooth, min_periods=1).mean()
    d_s = k_s.rolling(d, min_periods=1).mean()
    return {"k": k_s, "d": d_s}


# ---------------------------------------------------------------- ADX / DI (Wilder)
def adx(high, low, close, period: int = 14):
    h, l, c = _s(high), _s(low), _s(close)
    up_move = h.diff()
    dn_move = -l.diff()
    plus_dm = pd.Series(np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0), index=h.index)
    minus_dm = pd.Series(np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0), index=h.index)
    tr = true_range(h, l, c)
    atr_w = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean() / atr_w
    minus_di = 100.0 * minus_dm.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean() / atr_w
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx_v = dx.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    return {"adx": adx_v, "plus_di": plus_di, "minus_di": minus_di}


# ---------------------------------------------------------------- CCI
def cci(high, low, close, period: int = 20) -> pd.Series:
    h, l, c = _s(high), _s(low), _s(close)
    tp = (h + l + c) / 3.0
    ma = tp.rolling(period, min_periods=period).mean()
    md = tp.rolling(period, min_periods=period).apply(lambda v: np.mean(np.abs(v - v.mean())), raw=True)
    return (tp - ma) / (0.015 * md.replace(0.0, np.nan))


# ---------------------------------------------------------------- Williams %R
def willr(high, low, close, period: int = 14) -> pd.Series:
    h, l, c = _s(high), _s(low), _s(close)
    hh = h.rolling(period, min_periods=period).max()
    ll = l.rolling(period, min_periods=period).min()
    return -100.0 * (hh - c) / (hh - ll).replace(0.0, np.nan)


# ---------------------------------------------------------------- ROC / momentum
def roc(close, period: int = 10) -> pd.Series:
    c = _s(close)
    return 100.0 * (c - c.shift(period)) / c.shift(period).replace(0.0, np.nan)


def mom(close, period: int = 10) -> pd.Series:
    c = _s(close)
    return c - c.shift(period)


# ---------------------------------------------------------------- Keltner
def keltner(high, low, close, period: int = 20, mult: float = 2.0):
    c = _s(close)
    mid = ema(c, period)
    rng = atr(high, low, close, period)
    return {"mid": mid, "upper": mid + mult * rng, "lower": mid - mult * rng}


# ---------------------------------------------------------------- Donchian
def donchian(high, low, period: int = 20):
    h, l = _s(high), _s(low)
    upper = h.rolling(period, min_periods=period).max()
    lower = l.rolling(period, min_periods=period).min()
    mid = (upper + lower) / 2.0
    return {"upper": upper, "mid": mid, "lower": lower}


# ---------------------------------------------------------------- Ichimoku
def ichimoku(high, low, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52):
    h, l = _s(high), _s(low)
    ten = (h.rolling(tenkan, min_periods=tenkan).max() + l.rolling(tenkan, min_periods=tenkan).min()) / 2.0
    kij = (h.rolling(kijun, min_periods=kijun).max() + l.rolling(kijun, min_periods=kijun).min()) / 2.0
    sa = ((ten + kij) / 2.0)  # senkou A (unshifted value at current bar)
    sb = (h.rolling(senkou_b, min_periods=senkou_b).max() + l.rolling(senkou_b, min_periods=senkou_b).min()) / 2.0
    # chikou = close relative to past is used as close (current close vs cloud)
    return {"tenkan": ten, "kijun": kij, "senkou_a": sa, "senkou_b": sb}


# ---------------------------------------------------------------- Pivot points (classic, from prior day's H/L/C)
def pivots(df: pd.DataFrame) -> pd.DataFrame:
    """Compute daily classic pivots from a candle df with utc epoch index/column.
    Each intraday row gets the pivot set computed from the PREVIOUS day's
    high/low/close (strictly causal)."""
    d = df.copy()
    if "epoch" in d.columns:
        d.index = pd.to_datetime(d["epoch"], unit="s", utc=True)
    daily = d.resample("1D").agg({"high": "max", "low": "min", "close": "last"}).dropna()
    pp = (daily["high"] + daily["low"] + daily["close"]) / 3.0
    r1 = 2 * pp - daily["low"]
    s1 = 2 * pp - daily["high"]
    r2 = pp + (daily["high"] - daily["low"])
    s2 = pp - (daily["high"] - daily["low"])
    p = pd.DataFrame({"pivot": pp, "r1": r1, "s1": s1, "r2": r2, "s2": s2}).shift(1)  # yesterday
    out = p.reindex(d.index, method="ffill")
    return out


# ---------------------------------------------------------------- Rolling stats
def rolling_volatility(close, period: int = 20, annualize: bool = False) -> pd.Series:
    """Std of log returns over window (causal)."""
    c = _s(close)
    lr = np.log(c / c.shift(1))
    v = lr.rolling(period, min_periods=period).std(ddof=0)
    if annualize:
        v = v * np.sqrt(252 * 24 * 60)  # minute bars approx
    return v


def rolling_skew(close, period: int = 20) -> pd.Series:
    lr = np.log(_s(close) / _s(close).shift(1))
    return lr.rolling(period, min_periods=period).skew()


def rolling_kurt(close, period: int = 20) -> pd.Series:
    lr = np.log(_s(close) / _s(close).shift(1))
    return lr.rolling(period, min_periods=period).kurt()


def zscore(close, period: int = 20) -> pd.Series:
    c = _s(close)
    m = c.rolling(period, min_periods=period).mean()
    s = c.rolling(period, min_periods=period).std(ddof=0)
    return (c - m) / s.replace(0.0, np.nan)


def rolling_rank(series, period: int = 100) -> pd.Series:
    """Rank of the last value within the trailing window, in [0,1]. Causal."""
    s = _s(series)
    return s.rolling(period, min_periods=period).apply(
        lambda v: (v <= v[-1]).mean(), raw=True
    )


# ---------------------------------------------------------------- Session / calendar features
def session_features(df: pd.DataFrame) -> pd.DataFrame:
    """From a candle df with utc epoch column, emit hour sin/cos, dow sin/cos,
    and boolean session flags (asia/london/ny in UTC). Strictly causal."""
    if "epoch" in df.columns:
        ts = pd.to_datetime(pd.Series(df["epoch"].values), unit="s", utc=True)
    else:
        ts = pd.Series(pd.to_datetime(df.index, utc=True))
    hour = ts.dt.hour + ts.dt.minute / 60.0
    dow = ts.dt.dayofweek
    out = pd.DataFrame(index=df.index)
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    out["dow_sin"] = np.sin(2 * np.pi * dow / 7.0)
    out["dow_cos"] = np.cos(2 * np.pi * dow / 7.0)
    out["sess_asia"] = ((ts.dt.hour >= 0) & (ts.dt.hour < 7)).astype(float)
    out["sess_london"] = ((ts.dt.hour >= 7) & (ts.dt.hour < 16)).astype(float)
    out["sess_ny"] = ((ts.dt.hour >= 13) & (ts.dt.hour < 22)).astype(float)
    out["hour_utc"] = ts.dt.hour.astype(float)
    return out


# ---------------------------------------------------------------- Candle patterns (causal)
def candle_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Body/wick geometry + a few classic patterns. Values are floats; pattern
    flags are 0/1. All causal (only current + previous candles)."""
    o, h, l, c = (_s(df["open"]), _s(df["high"]), _s(df["low"]), _s(df["close"]))
    body = (c - o)
    rng = (h - l).replace(0.0, np.nan)
    out = pd.DataFrame(index=df.index)
    out["body"] = body
    out["body_pct"] = body / rng
    out["upper_wick"] = (h - pd.concat([o, c], axis=1).max(axis=1)) / rng
    out["lower_wick"] = (pd.concat([o, c], axis=1).min(axis=1) - l) / rng
    out["bull"] = (body > 0).astype(float)
    out["doji"] = ((body.abs() / rng) < 0.1).astype(float)
    out["hammer"] = ((out["lower_wick"] > 2 * body.abs() / rng) & (out["upper_wick"] < 0.3)).astype(float)
    out["shooting"] = ((out["upper_wick"] > 2 * body.abs() / rng) & (out["lower_wick"] < 0.3)).astype(float)
    prev_body = body.shift(1)
    out["engulf_bull"] = ((body > 0) & (prev_body < 0) & (c >= o.shift(1)) & (o <= c.shift(1))).astype(float)
    out["engulf_bear"] = ((body < 0) & (prev_body > 0) & (c <= o.shift(1)) & (o >= c.shift(1))).astype(float)
    out["range_pct"] = rng / c
    return out


# ---------------------------------------------------------------- Multi-timeframe (no look-ahead)
def multi_tf_resample(df: pd.DataFrame, factor: int) -> pd.DataFrame:
    """Aggregate minute candles to `factor`-minute bars, then forward-fill onto
    the ORIGINAL index with the rule: a row at time t sees only bars whose
    close time <= t (i.e. completed higher-TF bars). No look-ahead."""
    d = df.copy()
    if "epoch" in d.columns:
        d.index = pd.to_datetime(d["epoch"], unit="s", utc=True)
    agg = d.resample(f"{int(factor)}min", label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    # bar labelled at its END time; it is only known once t >= label
    agg = agg.shift(1)  # at time t expose only the bar that ended at t
    out = agg.reindex(d.index, method="ffill")
    out.columns = [f"tf{factor}_{c}" for c in out.columns]
    return out
