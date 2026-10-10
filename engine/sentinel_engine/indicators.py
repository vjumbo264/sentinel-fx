"""Indicator library. All functions take/return pandas Series aligned on the
input index. STRICTLY CAUSAL: value at index i depends only on rows <= i.
No volume inputs (Deriv forex candles have none)."""
import numpy as np
import pandas as pd

def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()

def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()

def wma(s: pd.Series, n: int) -> pd.Series:
    w = np.arange(1, n + 1, dtype=float)
    return s.rolling(n, min_periods=n).apply(lambda x: float(np.dot(x, w) / w.sum()), raw=True)

def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0.0); dn = -d.clip(upper=0.0)
    ru = up.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rd = dn.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = ru / rd.replace(0.0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0).where(rd.notna())

def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    m = ema(close, fast) - ema(close, slow)
    sig = m.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return m, sig, m - sig

def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    return mid + k * sd, mid, mid - k * sd

def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    pc = close.shift(1)
    tr = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()

def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14, d: int = 3):
    ll = low.rolling(n, min_periods=n).min(); hh = high.rolling(n, min_periods=n).max()
    k = 100 * (close - ll) / (hh - ll).replace(0.0, np.nan)
    return k, k.rolling(d, min_periods=d).mean()

def adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14):
    up = high.diff(); dn = -low.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(high, low, close, n).replace(0.0, np.nan)
    pdi = 100 * pd.Series(pdm, index=high.index).ewm(alpha=1/n, adjust=False, min_periods=n).mean() / a
    ndi = 100 * pd.Series(ndm, index=high.index).ewm(alpha=1/n, adjust=False, min_periods=n).mean() / a
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0.0, np.nan)
    return dx.ewm(alpha=1/n, adjust=False, min_periods=n).mean(), pdi, ndi

def cci(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 20) -> pd.Series:
    tp = (high + low + close) / 3
    md = tp.rolling(n, min_periods=n).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    return (tp - sma(tp, n)) / (0.015 * md.replace(0.0, np.nan))

def willr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    hh = high.rolling(n, min_periods=n).max(); ll = low.rolling(n, min_periods=n).min()
    return -100 * (hh - close) / (hh - ll).replace(0.0, np.nan)

def roc(close: pd.Series, n: int = 10) -> pd.Series:
    return 100 * close.diff(n) / close.shift(n).replace(0.0, np.nan)

def keltner(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 20, k: float = 2.0):
    mid = ema(close, n); a = atr(high, low, close, n)
    return mid + k * a, mid, mid - k * a

def donchian(high: pd.Series, low: pd.Series, n: int = 20):
    return high.rolling(n, min_periods=n).max(), low.rolling(n, min_periods=n).min()

def ichimoku(high: pd.Series, low: pd.Series, tenkan=9, kijun=26, senkou_b=52):
    def mid(h, l, n): return (h.rolling(n, min_periods=n).max() + l.rolling(n, min_periods=n).min()) / 2
    t = mid(high, low, tenkan); k = mid(high, low, kijun)
    return t, k, ((t + k) / 2).shift(kijun), mid(high, low, senkou_b).shift(kijun)

def rolling_volatility(ret: pd.Series, n: int) -> pd.Series:
    return ret.rolling(n, min_periods=n).std(ddof=0)

def rolling_skew(ret: pd.Series, n: int) -> pd.Series:
    return ret.rolling(n, min_periods=n).skew()

def rolling_kurtosis(ret: pd.Series, n: int) -> pd.Series:
    return ret.rolling(n, min_periods=n).kurt()

def zscore(s: pd.Series, n: int) -> pd.Series:
    m = s.rolling(n, min_periods=n).mean(); sd = s.rolling(n, min_periods=n).std(ddof=0)
    return (s - m) / sd.replace(0.0, np.nan)

def cross_over(a: pd.Series, b: pd.Series) -> pd.Series:
    return ((a > b) & (a.shift(1) <= b.shift(1))).astype(float)

def cross_under(a: pd.Series, b: pd.Series) -> pd.Series:
    return ((a < b) & (a.shift(1) >= b.shift(1))).astype(float)
