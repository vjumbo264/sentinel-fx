"""Feature DSL: a JSON expression graph. STRICTLY CAUSAL.

Nodes: {"name": str, "op": str, "inputs": [str, ...], "params": {...}}
Inputs reference candle fields (open/high/low/close/epoch) or earlier node names.
Rejected: negative shifts, centered windows, whole-series statistics,
unknown ops, forward references. DSL ops are append-only across engine versions.
"""
import numpy as np
import pandas as pd
from . import indicators as ind

class DSLError(ValueError):
    pass

def _candles_to_df(candles) -> pd.DataFrame:
    df = pd.DataFrame(candles)
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="raise")
    if "epoch" in df.columns:
        df["epoch"] = pd.to_numeric(df["epoch"], errors="raise").astype("int64")
    return df

def _roll(s, n, fn):
    return s.rolling(int(n), min_periods=int(n)).apply(fn, raw=True)

def compute_features(dsl_nodes: list, candles) -> pd.DataFrame:
    """Evaluate the DSL graph. Raises DSLError on any non-causal construct."""
    if not isinstance(dsl_nodes, list):
        raise DSLError("dsl must be a list of nodes")
    df = _candles_to_df(candles)
    env = {c: df[c] for c in df.columns if c in ("open", "high", "low", "close", "epoch")}
    names = set()
    for node in dsl_nodes:
        name, op = node.get("name"), node.get("op")
        params = node.get("params", {}) or {}
        ins = node.get("inputs", []) or []
        if not name or not op:
            raise DSLError("every node needs name and op")
        for i in ins:
            if i not in env:
                raise DSLError(f"node {name}: unknown/forward input '{i}'")
        env[name] = _eval_op(name, op, ins, params, env)
        names.add(name)
    return pd.DataFrame({n: env[n] for n in names}, index=df.index)

def _num(params, key, default=None):
    v = params.get(key, default)
    if v is None:
        raise DSLError(f"missing param {key}")
    return v

def _window(params, key="n"):
    n = int(_num(params, key))
    if n < 1:
        raise DSLError(f"window must be >= 1, got {n}")
    return n

def _eval_op(name, op, ins, params, env):
    a = env[ins[0]] if ins else None
    b = env[ins[1]] if len(ins) > 1 else None

    if op == "shift":
        n = int(_num(params, "n"))
        if n < 0:  # negative shift = look-ahead. Hard reject.
            raise DSLError(f"node {name}: negative shift is non-causal")
        return a.shift(n)
    if op == "const":
        return pd.Series(float(_num(params, "value")), index=a.index if a is not None else None)
    if op in ("add", "sub", "mul", "div"):
        if op == "add": return a + b
        if op == "sub": return a - b
        if op == "mul": return a * b
        return a / b.replace(0.0, np.nan)
    if op in ("gt", "ge", "lt", "le", "eq", "ne"):
        return {"gt": a > b, "ge": a >= b, "lt": a < b, "le": a <= b, "eq": a == b, "ne": a != b}[op].astype(float)
    if op in ("and_", "or_", "xor"):
        return {"and_": (a > 0) & (b > 0), "or_": (a > 0) | (b > 0), "xor": (a > 0) ^ (b > 0)}[op].astype(float)
    if op == "not_":
        return (a <= 0).astype(float)
    if op == "clip":
        return a.clip(float(_num(params, "lo")), float(_num(params, "hi")))
    if op == "abs": return a.abs()
    if op == "log":
        return np.log(a.where(a > 0))
    if op == "diff":
        return a.diff(int(params.get("n", 1)))
    if op == "pct_change":
        return a.pct_change(int(params.get("n", 1)))
    if op == "logret":
        return np.log(a / a.shift(1).where(a.shift(1) > 0))

    # rolling / expanding stats only (causal). Whole-series stats are banned.
    if op == "roll_mean": return a.rolling(_window(params), min_periods=_window(params)).mean()
    if op == "roll_std":  return a.rolling(_window(params), min_periods=_window(params)).std(ddof=0)
    if op == "roll_min":  return a.rolling(_window(params), min_periods=_window(params)).min()
    if op == "roll_max":  return a.rolling(_window(params), min_periods=_window(params)).max()
    if op == "roll_sum":  return a.rolling(_window(params), min_periods=_window(params)).sum()
    if op == "roll_median": return a.rolling(_window(params), min_periods=_window(params)).median()
    if op == "roll_skew": return ind.rolling_skew(a, _window(params))
    if op == "roll_kurt": return ind.rolling_kurtosis(a, _window(params))
    if op == "roll_rank":
        n = _window(params)
        return a.rolling(n, min_periods=n).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True)
    if op == "expanding_mean": return a.expanding(min_periods=_window(params)).mean()
    if op == "ewm_mean": return a.ewm(span=_window(params, "span"), adjust=False, min_periods=_window(params, "span")).mean()
    if op == "ewm_std":  return a.ewm(span=_window(params, "span"), adjust=False, min_periods=_window(params, "span")).std()
    if op == "zscore": return ind.zscore(a, _window(params))
    if op == "cross_over": return ind.cross_over(a, b)
    if op == "cross_under": return ind.cross_under(a, b)

    # library indicators (all causal by construction)
    if op == "sma": return ind.sma(a, _window(params))
    if op == "ema": return ind.ema(a, _window(params))
    if op == "wma": return ind.wma(a, _window(params))
    if op == "rsi": return ind.rsi(a, int(params.get("n", 14)))
    if op == "macd":        return ind.macd(a, int(params.get("fast",12)), int(params.get("slow",26)), int(params.get("signal",9)))[0]
    if op == "macd_signal": return ind.macd(a, int(params.get("fast",12)), int(params.get("slow",26)), int(params.get("signal",9)))[1]
    if op == "macd_hist":   return ind.macd(a, int(params.get("fast",12)), int(params.get("slow",26)), int(params.get("signal",9)))[2]
    if op == "bb_upper": return ind.bollinger(a, int(params.get("n",20)), float(params.get("k",2.0)))[0]
    if op == "bb_lower": return ind.bollinger(a, int(params.get("n",20)), float(params.get("k",2.0)))[2]
    if op == "bb_width":
        u, m, l = ind.bollinger(a, int(params.get("n",20)), float(params.get("k",2.0)))
        return (u - l) / m.replace(0.0, np.nan)
    if op == "atr":  return ind.atr(env[ins[0]], env[ins[1]], env[ins[2]], int(params.get("n", 14)))
    if op == "stoch_k": return ind.stochastic(env[ins[0]], env[ins[1]], env[ins[2]], int(params.get("n",14)), int(params.get("d",3)))[0]
    if op == "stoch_d": return ind.stochastic(env[ins[0]], env[ins[1]], env[ins[2]], int(params.get("n",14)), int(params.get("d",3)))[1]
    if op == "adx":  return ind.adx(env[ins[0]], env[ins[1]], env[ins[2]], int(params.get("n", 14)))[0]
    if op == "di_plus":  return ind.adx(env[ins[0]], env[ins[1]], env[ins[2]], int(params.get("n", 14)))[1]
    if op == "di_minus": return ind.adx(env[ins[0]], env[ins[1]], env[ins[2]], int(params.get("n", 14)))[2]
    if op == "cci": return ind.cci(env[ins[0]], env[ins[1]], env[ins[2]], int(params.get("n", 20)))
    if op == "willr": return ind.willr(env[ins[0]], env[ins[1]], env[ins[2]], int(params.get("n", 14)))
    if op == "roc": return ind.roc(a, int(params.get("n", 10)))
    if op == "kc_upper": return ind.keltner(env[ins[0]], env[ins[1]], env[ins[2]], int(params.get("n",20)), float(params.get("k",2.0)))[0]
    if op == "kc_lower": return ind.keltner(env[ins[0]], env[ins[1]], env[ins[2]], int(params.get("n",20)), float(params.get("k",2.0)))[2]
    if op == "donchian_high": return ind.donchian(env[ins[0]], env[ins[1]], int(params.get("n",20)))[0]
    if op == "donchian_low":  return ind.donchian(env[ins[0]], env[ins[1]], int(params.get("n",20)))[1]
    if op == "ichimoku_tenkan": return ind.ichimoku(env[ins[0]], env[ins[1]])[0]
    if op == "ichimoku_kijun":  return ind.ichimoku(env[ins[0]], env[ins[1]])[1]
    if op == "roll_vol": return ind.rolling_volatility(a, _window(params))

    # session / calendar features from epoch (UTC) - causal, known in advance
    if op in ("hour_utc", "dow_utc", "hour_lagos"):
        e = env["epoch"]
        if op == "hour_utc": return pd.Series((e // 3600) % 24, index=e.index).astype(float)
        if op == "dow_utc":  return pd.Series((e // 86400 + 3) % 7, index=e.index).astype(float)  # 1970-01-01 = Thu=3
        return pd.Series(((e + 3600) // 3600) % 24, index=e.index).astype(float)

    raise DSLError(f"node {name}: unknown op '{op}' (DSL ops are append-only; upgrade the engine or use a supported op)")

SUPPORTED_OPS = frozenset("""
shift const add sub mul div gt ge lt le eq ne and_ or_ xor not_ clip abs log diff pct_change logret
roll_mean roll_std roll_min roll_max roll_sum roll_median roll_skew roll_kurt roll_rank
expanding_mean ewm_mean ewm_std zscore cross_over cross_under
sma ema wma rsi macd macd_signal macd_hist bb_upper bb_lower bb_width atr stoch_k stoch_d
adx di_plus di_minus cci willr roc kc_upper kc_lower donchian_high donchian_low
ichimoku_tenkan ichimoku_kijun roll_vol hour_utc dow_utc hour_lagos
""".split())
