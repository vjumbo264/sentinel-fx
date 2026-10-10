"""Rule layer: JSON rule tree evaluated after the model.
Node: {"if": {"field": f, "op": "<|<=|>|>=|==|!=|in|between", "value": v},
       "then": ACTION, "else": ACTION-or-node}
ACTION: {"action": "allow|block|adjust_confidence", "reason": str, "delta": float?}
Context fields: prob, side, regime, adx, rsi, news_state, minutes_to_news, session_ok,
plus any computed feature by name.
"""
class RuleError(ValueError):
    pass

_OPS = {
    "<":  lambda a, b: a < b,  "<=": lambda a, b: a <= b,
    ">":  lambda a, b: a > b,  ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
    "in": lambda a, b: a in b,
    "between": lambda a, b: isinstance(b, (list, tuple)) and len(b) == 2 and b[0] <= a <= b[1],
}
VALID_ACTIONS = {"allow", "block", "adjust_confidence"}

def _check(node, depth=0):
    if depth > 32: raise RuleError("rule tree too deep")
    if "action" in node:
        if node["action"] not in VALID_ACTIONS: raise RuleError(f"bad action {node['action']!r}")
        if not node.get("reason"): raise RuleError("action needs a reason")
        return
    cond = node.get("if")
    if not isinstance(cond, dict) or cond.get("op") not in _OPS or "field" not in cond:
        raise RuleError("rule node needs if{field,op,value}")
    for branch in ("then", "else"):
        if branch in node and node[branch] is not None:
            _check(node[branch], depth + 1)

def validate_rules(rules: dict):
    if not rules: return
    tree = rules.get("tree")
    if tree: _check(tree)

def eval_rules(rules: dict, ctx: dict):
    """Returns (action, reason, delta). Default allow."""
    if not rules or not rules.get("tree"):
        return "allow", "no rules", 0.0
    node = rules["tree"]
    while True:
        if "action" in node:
            return node["action"], node.get("reason", ""), float(node.get("delta", 0.0))
        cond = node["if"]
        val = ctx.get(cond["field"])
        try:
            ok = _OPS[cond["op"]](val, cond.get("value"))
        except TypeError:
            ok = False
        nxt = node.get("then") if ok else node.get("else")
        if nxt is None:
            return "allow", "rule fallthrough", 0.0
        node = nxt
