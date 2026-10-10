"""
sentinel_engine.dsl
===================
Causal feature expression graph (JSON). Nodes: {"id", "op", "inputs", "params"}.
All ops are strictly causal: no negative shifts, no centered windows, no
whole-series statistics (rolling/expanding only). Non-causal requests raise.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from . import indicators as ind

ENGINE_VERSION = "1.0.0"

# Registry of indicator ops that take candle columns
_CANDLE_OPS = {
    "sma": lambda c, df, p: ind.sma(df[p.get("col", "close")], p["period"]),
    "ema": lambda c, df, p: ind.ema(df[p.get("col", "close")], p["period"]),
    "wma": lambda c, df, p: ind.wma(df[p.get("col", "close")], p["period"]),
    "rsi": lambda c, df, p: ind.rsi(df[p.get("col", "close")], p.get("period", 14)),
    "macd": lambda c, df, p: ind.macd(df[p.get("col", "close")], p.get("fast", 12), p.get("slow", 26), p.get("signal", 9))[p.get("out", "macd")],
    "bollinger": lambda c, df, p: ind.bollinger(df[p.get("col", "close")], p.get("period", 20), p.get("mult", 2.0))[p.get("out", "mid")],
    "atr": lambda c, df, p: ind.atr(df["high"], df["low"], df["close"], p.get("period", 14)),
    "stochastic": lambda c, df, p: ind.stochastic(df["high"], df["low"], df["close"], p.get("k", 14), p.get("d", 3), p.get("smooth", 3))[p.get("out", "k")],
    "adx": lambda c, df, p: ind.adx(df["high"], df["low"], df["close"], p.get("period", 14))[p.get("out", "adx")],
    "cci": lambda c, df, p: ind.cci(df["high"], df["low"], df["close"], p.get("period", 20)),
    "willr": lambda c, df, p: ind.willr(df["high"], df["low"], df["close"], p.get("period", 14)),
    "roc": lambda c, df, p: ind.roc(df[p.get("col", "close")], p.get("period", 10)),
    "mom": lambda c, df, p: ind.mom(df[p.get("col", "close")], p.get("period", 10)),
    "keltner": lambda c, df, p: ind.keltner(df["high"], df["low"], df["close"], p.get("period", 20), p.get("mult", 2.0))[p.get("out", "mid")],
    "donchian": lambda c, df, p: ind.donchian(df["high"], df["low"], p.get("period", 20))[p.get("out", "mid")],
    "ichimoku": lambda c, df, p: ind.ichimoku(df["high"], df["low"])[p.get("out", "tenkan")],
    "rolling_volatility": lambda c, df, p: ind.rolling_volatility(df[p.get("col", "close")], p.get("period", 20)),
    "rolling_skew": lambda c, df, p: ind.rolling_skew(df[p.get("col", "close")], p.get("period", 20)),
    "rolling_kurt": lambda c, df, p: ind.rolling_kurt(df[p.get("col", "close")], p.get("period", 20)),
    "zscore": lambda c, df, p: ind.zscore(df[p.get("col", "close")], p.get("period", 20)),
}

# Series-transform ops operating on node inputs (causal only)
def _shift(s, p):
    n = p.get("n", 1)
    if n < 0:
        raise ValueError("negative shift is non-causal and forbidden")
    return s.shift(n)

def _rolling(s, p):
    fn = p["fn"]; w = int(p["window"])
    r = s.rolling(w, min_periods=w)
    m = {"mean": r.mean, "std": lambda: r.std(ddof=0), "min": r.min, "max": r.max,
         "sum": r.sum, "median": r.median}
    if fn not in m:
        raise ValueError(f"unsupported rolling fn {fn}")
    return m[fn]()

def _expanding(s, p):
    fn = p["fn"]
    e = s.expanding(min_periods=1)
    m = {"mean": e.mean, "std": lambda: e.std(ddof=0), "min": e.min, "max": e.max, "sum": e.sum}
    if fn not in m:
        raise ValueError(f"unsupported expanding fn {fn}")
    return m[fn]()

def _ewm(s, p):
    return s.ewm(span=int(p["span"]), adjust=False, min_periods=int(p["span"])).mean()

def _cross_over(a, b):
    return ((a > b) & (a.shift(1) <= b.shift(1))).astype(float)

def _cross_under(a, b):
    return ((a < b) & (a.shift(1) >= b.shift(1))).astype(float)

_SERIES_OPS = {
    "shift": _shift,
    "rolling": _rolling,
    "expanding": _expanding,
    "ewm": _ewm,
    "cross_over": lambda s, p: _cross_over(s, p["_second"]),
    "cross_under": lambda s, p: _cross_under(s, p["_second"]),
    "rank": lambda s, p: ind.rolling_rank(s, p.get("window", 100)),
    "zscore_of": lambda s, p: ind.zscore(s, p.get("period", 20)),
}

_ARITH = {
    "add": lambda xs: xs[0] + xs[1],
    "sub": lambda xs: xs[0] - xs[1],
    "mul": lambda xs: xs[0] * xs[1],
    "div": lambda xs: xs[0] / xs[1].replace(0.0, np.nan),
    "abs": lambda xs: xs[0].abs(),
    "log": lambda xs: np.log(xs[0].where(xs[0] > 0)),
    "sqrt": lambda xs: np.sqrt(xs[0].clip(lower=0)),
    "neg": lambda xs: -xs[0],
    "pow": lambda xs, p: xs[0] ** p.get("exp", 2),
}

_CMP = {
    "gt": lambda xs: (xs[0] > xs[1]).astype(float),
    "gte": lambda xs: (xs[0] >= xs[1]).astype(float),
    "lt": lambda xs: (xs[0] < xs[1]).astype(float),
    "lte": lambda xs: (xs[0] <= xs[1]).astype(float),
    "eq": lambda xs: (xs[0] == xs[1]).astype(float),
}

_LOGIC = {
    "and": lambda xs: ((xs[0] > 0) & (xs[1] > 0)).astype(float),
    "or": lambda xs: ((xs[0] > 0) | (xs[1] > 0)).astype(float),
    "not": lambda xs: (xs[0] <= 0).astype(float),
}


class DSLError(Exception):
    pass


def compute_features(dsl: list, df: pd.DataFrame, extra: dict | None = None) -> pd.DataFrame:
    """Evaluate a DSL graph against a candle DataFrame (columns: epoch,open,high,low,close).
    `extra` may carry precomputed frames keyed by name (e.g. session/news/tf resamples).
    Returns DataFrame of node outputs aligned to df.index."""
    df = df.reset_index(drop=True).copy()
    ctx: dict[str, pd.Series] = {
        "open": df["open"].astype(float), "high": df["high"].astype(float),
        "low": df["low"].astype(float), "close": df["close"].astype(float),
    }
    extra = extra or {}
    sess = ind.session_features(df)
    for col in sess.columns:
        ctx[col] = sess[col].reset_index(drop=True)
    for k, frame in extra.items():
        if isinstance(frame, pd.DataFrame):
            for col in frame.columns:
                ctx[col] = frame[col].reset_index(drop=True)

    out_cols = {}
    for node in dsl:
        nid, op = node.get("id"), node.get("op")
        inputs = node.get("inputs", []) or []
        params = dict(node.get("params", {}) or {})
        if not nid or not op:
            raise DSLError(f"node missing id/op: {node}")
        if op in _CANDLE_OPS:
            res = _CANDLE_OPS[op](None, df, params)
        elif op in _SERIES_OPS:
            if not inputs:
                raise DSLError(f"op {op} needs inputs")
            s = ctx.get(inputs[0])
            if s is None:
                raise DSLError(f"unknown input {inputs[0]} for op {op}")
            if op in ("cross_over", "cross_under"):
                if len(inputs) < 2:
                    raise DSLError(f"{op} needs 2 inputs")
                params["_second"] = ctx.get(inputs[1])
                if params["_second"] is None:
                    raise DSLError(f"unknown input {inputs[1]} for {op}")
            res = _SERIES_OPS[op](s, params)
        elif op in _ARITH or op in _CMP or op in _LOGIC:
            xs = [ctx.get(i) for i in inputs]
            if any(x is None for x in xs):
                missing = [i for i, x in zip(inputs, xs) if x is None]
                raise DSLError(f"unknown inputs {missing} for {op}")
            fn = _ARITH.get(op) or _CMP.get(op) or _LOGIC.get(op)
            try:
                res = fn(xs, params) if fn.__code__.co_argcount == 2 else fn(xs)
            except TypeError:
                res = fn(xs)
        elif op == "const":
            res = pd.Series(params.get("value", 0.0), index=df.index, dtype=float)
        else:
            raise DSLError(f"unsupported op '{op}' (engine {ENGINE_VERSION})")
        res = pd.Series(res).reset_index(drop=True).astype(float)
        ctx[nid] = res
        out_cols[nid] = res
    return pd.DataFrame(out_cols)


def validate_dsl(dsl: list) -> list[str]:
    """Static validation of a DSL graph. Returns list of problems (empty = ok)."""
    problems = []
    if not isinstance(dsl, list):
        return ["dsl must be a list"]
    seen = set(["open", "high", "low", "close"])
    allowed = set(_CANDLE_OPS) | set(_SERIES_OPS) | set(_ARITH) | set(_CMP) | set(_LOGIC) | {"const"}
    for node in dsl:
        nid, op = node.get("id"), node.get("op")
        if not nid:
            problems.append(f"node without id: {node}")
            continue
        if op not in allowed:
            problems.append(f"node {nid}: unsupported op '{op}'")
        for p in node.get("inputs", []) or []:
            if p not in seen and p not in [n.get("id") for n in dsl]:
                problems.append(f"node {nid}: unknown input '{p}'")
        if op == "shift" and (node.get("params", {}).get("n", 1) < 0):
            problems.append(f"node {nid}: negative shift forbidden")
        seen.add(nid)
    return problems
