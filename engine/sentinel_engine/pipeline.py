"""Decision pipeline: features -> model prob -> rule layer -> news -> final decision.
Identical code path in training, validation and the live bot."""
from .dsl import compute_features
from .models import load_model
from .rules import eval_rules
from .news import news_state, event_affects

def break_even(payout: float) -> float:
    return 1.0 / (1.0 + payout)

def decide(pack: dict, candles, *, now_utc, news_events=None, news_reactions=None, live_payout=None):
    """Returns dict(side, confidence, action, reason, prob)."""
    feats = compute_features(pack["features"]["dsl"], candles)
    for mod in pack["features"].get("custom_modules", []):
        from .sandbox import run_custom_module
        custom = run_custom_module(mod["name"], mod["code_b64gz"], candles)
        for col in custom.columns:
            feats[col] = custom[col].values
    model = load_model(pack["model"])
    last = feats.iloc[-1]
    row = {f: float(last.get(f, 0.0)) for f in model.features}
    prob = model.predict_proba(row)
    side = "CALL" if prob >= 0.5 else "PUT"
    conf = prob if side == "CALL" else 1.0 - prob

    payout = live_payout if live_payout is not None else float(pack["decision"].get("payout_assumed", 0.85))
    be = break_even(payout)
    margin = float(pack["decision"].get("margin", 0.0))

    ctx = dict(prob=prob, side=side, regime=str(last.get("regime", "")),
               adx=float(last.get("adx", 0) or 0), rsi=float(last.get("rsi", 50) or 50))
    st = news_state(now_utc, news_events or [], pack["symbol"], pack.get("news_rules", {}) or {}, news_reactions)
    ctx["news_state"] = "clear"
    ctx["minutes_to_news"] = st["minutes_to_next_high"] if st["minutes_to_next_high"] is not None else 9999.0

    nr = pack.get("news_rules", {}) or {}
    if st["blackout"]:
        return {"action": "block", "side": side, "confidence": conf, "prob": prob,
                "reason": "skipped: news blackout window around high-impact release"}
    if nr.get("block_if_against") and st["minutes_to_next_high"] is not None and st["minutes_to_next_high"] <= nr.get("against_horizon_min", 60):
        thr = float(nr.get("reaction_threshold_pips", 0))
        if st["last_reaction_pips"] is not None and st["last_reaction_pips"] >= thr:
            margin += float(nr.get("against_extra_margin", 0.04))
            ctx["news_state"] = "against"
    action, reason, delta = eval_rules(pack.get("rules", {}) or {}, ctx)
    conf += delta
    if action == "block":
        return {"action": "block", "side": side, "confidence": conf, "prob": prob, "reason": f"skipped: {reason}"}
    hours = pack.get("sessions", {}).get("allowed_utc_hours") or []
    if hours and now_utc.hour not in hours:
        return {"action": "block", "side": side, "confidence": conf, "prob": prob,
                "reason": f"skipped: session filter (hour {now_utc.hour} UTC not allowed)"}
    if conf < be + margin:
        return {"action": "block", "side": side, "confidence": conf, "prob": prob,
                "reason": f"skipped: confidence {conf:.3f} < break-even {be:.3f} + margin {margin:.3f}"}
    return {"action": "allow", "side": side, "confidence": conf, "prob": prob,
            "reason": reason or "signal ok"}
