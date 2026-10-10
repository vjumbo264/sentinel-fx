"""
sentinel_engine.rules
=====================
JSON rule tree evaluated AFTER the model. Node forms:
  {"if": <cond>, "then": <action>, "else": <action>?}     (branch)
  {"all": [cond,...]} / {"any": [...]} / {"not": cond}    (boolean)
  {"op": "gt|gte|lt|lte|eq|between|in", "field": name, "value": x | [a,b] | [...]}
Actions: {"action": "allow"|"block"|"adjust", "reason": str, "margin_add": float?,
          "confidence_mult": float?}
Output: RuleDecision(allow: bool, margin_add: float, confidence_mult: float,
                     reasons: list[str])
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class RuleDecision:
    allow: bool = True
    margin_add: float = 0.0
    confidence_mult: float = 1.0
    reasons: list[str] = field(default_factory=list)


def _get(field: str, ctx: dict):
    return ctx.get(field)


def _eval_cond(node, ctx) -> bool:
    if isinstance(node, dict):
        if "all" in node:
            return all(_eval_cond(c, ctx) for c in node["all"])
        if "any" in node:
            return any(_eval_cond(c, ctx) for c in node["any"])
        if "not" in node:
            return not _eval_cond(node["not"], ctx)
        op = node.get("op")
        val = _get(node.get("field", ""), ctx)
        target = node.get("value")
        if val is None:
            return False
        if op == "gt": return val > target
        if op == "gte": return val >= target
        if op == "lt": return val < target
        if op == "lte": return val <= target
        if op == "eq": return val == target
        if op == "ne": return val != target
        if op == "between": return target[0] <= val <= target[1]
        if op == "in": return val in target
        raise ValueError(f"unknown rule op {op}")
    return bool(node)


def _apply(action: dict, dec: RuleDecision) -> RuleDecision:
    a = action.get("action", "allow")
    if a == "block":
        dec.allow = False
    elif a == "adjust":
        dec.margin_add += float(action.get("margin_add", 0.0))
        dec.confidence_mult *= float(action.get("confidence_mult", 1.0))
    reason = action.get("reason")
    if reason:
        dec.reasons.append(reason)
    return dec


def evaluate(tree: dict, ctx: dict) -> RuleDecision:
    """Walk the rule tree. ctx holds named facts: model_prob, adx, regime,
    news_state, minutes_to_news, session, streak, hour_utc, spread_pct ..."""
    dec = RuleDecision()
    if not tree:
        return dec
    _walk(tree, ctx, dec)
    return dec


def _walk(node, ctx, dec: RuleDecision):
    if isinstance(node, dict) and "if" in node:
        if _eval_cond(node["if"], ctx):
            branch = node.get("then")
        else:
            branch = node.get("else")
        if isinstance(branch, dict) and ("action" in branch):
            _apply(branch, dec)
        elif branch is not None:
            _walk(branch, ctx, dec)
    elif isinstance(node, list):
        for n in node:
            _walk(n, ctx, dec)
    elif isinstance(node, dict) and "action" in node:
        _apply(node, dec)


def validate_rules(tree) -> list[str]:
    problems = []
    known = {"model_prob", "adx", "regime", "news_state", "minutes_to_news",
             "session", "streak", "hour_utc", "atr_pct", "spread_pct", "hour_sin",
             "hour_cos", "rsi", "edge", "balance", "payout"}
    def chk(n):
        if isinstance(n, dict):
            if "field" in n and n["field"] not in known:
                problems.append(f"rule references unknown field '{n['field']}'")
            for k in ("if", "then", "else", "not"):
                if k in n:
                    chk(n[k])
            for k in ("all", "any"):
                if k in n:
                    for c in n[k]:
                        chk(c)
        elif isinstance(n, list):
            for c in n:
                chk(c)
    chk(tree)
    return problems
