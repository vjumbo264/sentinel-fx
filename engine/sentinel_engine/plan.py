"""
sentinel_engine.plan — analysis_plan.json evaluator (MODEL task M4).

Executes the trader's analysis process as a declarative, ACYCLIC graph of
data nodes (never code): feature_group -> router/screen -> analyst(s) ->
head -> calibrator -> decision. Every analyst/head references a model file in
the bundle; every node declares the data it needs and its causal lookback.

Node types
  feature_group : {"id","type":"feature_group","dsl":[...],"window":N}
  analyst       : {"id","type":"analyst","model":"<file>","inputs":[ids],
                   "features":[...],"budget_ms":N}
  router        : {"id","type":"router","table":[{when:{...},use:[ids]}],
                   "default":[ids]}
  head          : {"id","type":"head","model":"<file>","inputs":[analyst ids]}
  calibrator    : {"id","type":"calibrator","method":"isotonic|platt",
                   "table":[[lo,hi,mapped],...]}
  decision      : {"id","type":"decision"}  (terminal; reads decision.json)

evaluate(bundle, df, ctx) -> {action, side, p_win, stake_multiplier, reason,
                              opinions[], state}
Any model/feature failure, timeout or invalid output -> SKIP (fail closed).
"""
from __future__ import annotations
import time

MAX_PLAN_NODES = 64
ALLOWED_TYPES = {"feature_group", "analyst", "router", "head",
                 "calibrator", "decision"}


class PlanError(Exception):
    pass


def _check_acyclic(nodes: dict) -> list[str]:
    order, seen = [], set()

    def visit(nid, stack):
        if nid in stack:
            raise PlanError(f"cycle at {nid}")
        if nid in seen:
            return
        node = nodes.get(nid)
        if node is None:
            raise PlanError(f"unknown node {nid}")
        for dep in node.get("inputs", []) + node.get("features", []):
            if dep in nodes:
                visit(dep, stack | {nid})
        seen.add(nid)
        order.append(nid)

    for nid in nodes:
        visit(nid, set())
    return order


def validate_plan(plan: dict) -> list[str]:
    problems = []
    nodes = {n["id"]: n for n in plan.get("nodes", [])}
    if len(nodes) > MAX_PLAN_NODES:
        problems.append(f"plan too large ({len(nodes)} nodes)")
    for nid, n in nodes.items():
        t = n.get("type")
        if t not in ALLOWED_TYPES:
            problems.append(f"{nid}: disallowed node type {t!r}")
        if t in ("analyst", "head") and not n.get("model"):
            problems.append(f"{nid}: model file not declared")
    if not any(n.get("type") == "decision" for n in nodes.values()):
        problems.append("no decision node")
    try:
        _check_acyclic(nodes)
    except PlanError as e:
        problems.append(str(e))
    return problems


def evaluate(bundle, df, ctx=None, latency_ms: int = 600) -> dict:
    """Run the plan over the LAST bar of df. Fail closed on any error."""
    ctx = dict(ctx or {})
    t0 = time.monotonic()
    out = {"action": "skip", "side": None, "p_win": None,
           "stake_multiplier": 0.0, "reason": "plan not evaluated",
           "opinions": [], "state": {}}
    try:
        nodes = {n["id"]: n for n in bundle.plan.get("nodes", [])}
        order = _check_acyclic(nodes)
        values: dict = {}
        opinions = []
        for nid in order:
            if (time.monotonic() - t0) * 1000 > latency_ms:
                raise PlanError("latency budget exceeded")
            n = nodes[nid]
            t = n["type"]
            if t == "feature_group":
                from .dsl import compute_features
                values[nid] = compute_features(n.get("dsl", []), df)
            elif t == "router":
                chosen = list(n.get("default", []))
                for row in n.get("table", []):
                    when = row.get("when", {})
                    if all(ctx.get(k) == v for k, v in when.items()):
                        chosen = row.get("use", chosen)
                        break
                values[nid] = chosen
            elif t == "analyst":
                router = next((values[r] for r in values
                               if nodes[r]["type"] == "router"), None)
                if router is not None and nid not in router:
                    opinions.append({"id": nid, "skipped": True})
                    continue
                feats = None
                for src in n.get("inputs", []):
                    if src in values and hasattr(values[src], "iloc"):
                        feats = values[src]
                if feats is None:
                    raise PlanError(f"{nid}: no feature input")
                import numpy as np
                cols = n.get("features") or list(feats.columns)
                row = feats.iloc[-1]
                X = np.array([[float(row.get(c, 0.0) or 0.0) for c in cols]])
                mdl = bundle.model(n["model"])
                p = (mdl.predict(X)[0] if hasattr(mdl, "predict")
                     else mdl.run(None, {"input": X})[0][0][0])
                p = float(max(0.0, min(1.0, p)))
                op = {"id": nid, "p_up": round(p, 4),
                      "direction": "up" if p >= 0.5 else "down",
                      "strength": round(abs(p - 0.5) * 2, 4)}
                opinions.append(op)
                values[nid] = op
            elif t == "head":
                import numpy as np
                ins = [values[i] for i in n.get("inputs", [])
                       if isinstance(values.get(i), dict)]
                X = np.array([[o["p_up"] for o in ins]])
                mdl = bundle.model(n["model"])
                p = (mdl.predict(X)[0] if hasattr(mdl, "predict")
                     else mdl.run(None, {"input": X})[0][0][0])
                values[nid] = float(max(0.0, min(1.0, p)))
            elif t == "calibrator":
                raw = next((values[i] for i in reversed(order)
                            if isinstance(values.get(i), float)), None)
                if raw is None:
                    raise PlanError("calibrator: no head probability")
                mapped = raw
                for lo, hi, m in n.get("table", []):
                    if lo <= raw < hi:
                        mapped = m
                        break
                values[nid] = float(mapped)
            elif t == "decision":
                pcal = next((values[i] for i in reversed(order)
                             if isinstance(values.get(i), float)), None)
                if pcal is None:
                    raise PlanError("decision: no calibrated probability")
                dec = bundle.decision
                # calibrator maps P(up); p_win is for the CHOSEN side
                side = "CALL" if pcal >= 0.5 else "PUT"
                pwin = pcal if side == "CALL" else 1.0 - pcal
                mult = 1.0
                for lo, hi, m in dec.get("stake_map", []):
                    if lo <= pwin < hi:
                        mult = m
                        break
                agree = sum(1 for o in opinions if not o.get("skipped")
                            and o["direction"] == ("up" if side == "CALL" else "down"))
                total = sum(1 for o in opinions if not o.get("skipped"))
                out.update({
                    "action": "trade", "side": side, "p_win": round(pwin, 4),
                    "stake_multiplier": mult,
                    "reason": f"{agree} of {total} analysts agree; "
                              f"p_win {pwin:.3f}",
                    "opinions": opinions, "state": ctx})
        return out
    except Exception as e:  # fail closed
        out["reason"] = f"plan error -> SKIP ({type(e).__name__}: {e})"
        out["action"] = "skip"
        return out
