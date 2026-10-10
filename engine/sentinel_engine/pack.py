"""
sentinel_engine.pack
====================
Pair-pack loading, canonical checksum, and the decision pipeline
features -> model prob -> rule layer -> news logic -> final decision.
"""
from __future__ import annotations
import base64
import gzip
import hashlib
import json
import numpy as np
import pandas as pd

from . import dsl as _dsl
from . import rules as _rules
from . import models as _models
from . import sandbox as _sandbox

SYMBOL_RE = r"^(frx[A-Z]{6}|R_\d+|1HZ\d+V)$"
MAX_PACK_BYTES = 20 * 1024 * 1024


def canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def pack_checksum(pack: dict) -> str:
    body = {k: v for k, v in pack.items() if k != "checksum_sha256"}
    return hashlib.sha256(canonical_json(body).encode("utf8")).hexdigest()


def verify_checksum(pack: dict) -> bool:
    return pack.get("checksum_sha256") == pack_checksum(pack)


def decode_b64gz(s: str) -> bytes:
    return gzip.decompress(base64.b64decode(s))


def encode_b64gz(b: bytes) -> str:
    return base64.b64encode(gzip.compress(b)).decode("ascii")


def test_candles(pack: dict) -> list[dict]:
    t = pack.get("tests", {})
    if not t.get("candles_b64gz"):
        return []
    return json.loads(decode_b64gz(t["candles_b64gz"]).decode("utf8"))


class Pack:
    """Loaded pack: features, model, rules, risk. Thread of the decision pipeline."""

    def __init__(self, pack: dict):
        self.raw = pack
        self.symbol = pack["symbol"]
        self.features_dsl = pack.get("features", {}).get("dsl", [])
        self.custom_modules = pack.get("features", {}).get("custom_modules", [])
        self.model_spec = pack["model"]
        self.input_features = self.model_spec.get("input_features", [])
        self.rules_tree = pack.get("rules", {})
        self.news_rules = pack.get("news_rules", {})
        self.decision = pack.get("decision", {})
        self.risk = pack.get("risk", {})
        self._model = None

    @property
    def model(self):
        if self._model is None:
            self._model = _models.load_model(self.model_spec)
        return self._model

    @property
    def has_custom_code(self) -> bool:
        return len(self.custom_modules) > 0

    def compute_features(self, df: pd.DataFrame) -> pd.DataFrame:
        feats = _dsl.compute_features(self.features_dsl, df)
        for mod in self.custom_modules:
            code = decode_b64gz(mod["code_b64gz"]).decode("utf8")
            if hashlib.sha256(code.encode("utf8")).hexdigest() != mod["sha256"]:
                raise ValueError(f"custom module {mod['name']} sha256 mismatch")
            candles = df[["epoch", "open", "high", "low", "close"]].to_dict(orient="records")
            res = _sandbox.run_module(code, candles, mod.get("params", {}))
            if not res.get("ok"):
                raise RuntimeError(f"custom module {mod['name']} failed: {res.get('error')}")
            cf = pd.DataFrame(res["features"])
            for c in cf.columns:
                feats[f"{mod['name']}__{c}"] = cf[c].astype(float).values
        return feats

    def predict_proba(self, feats: pd.DataFrame) -> np.ndarray:
        X = feats[self.input_features].to_numpy(dtype=float)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        return self.model.predict(X)

    def decide(self, df: pd.DataFrame, ctx: dict | None = None) -> dict:
        """Full pipeline for the LAST bar of df.
        Returns {"side": "CALL"|"PUT"|None, "prob": float, "allow": bool,
                 "margin": float, "reasons": [...]}"""
        ctx = dict(ctx or {})
        feats = self.compute_features(df)
        prob = float(self.predict_proba(feats)[-1])
        side = "CALL" if prob >= 0.5 else "PUT"
        edge = prob if side == "CALL" else 1.0 - prob
        ctx.setdefault("model_prob", prob)
        ctx.setdefault("edge", edge)
        # expose last-bar indicator facts to the rule layer if present
        for f in ("adx", "rsi", "atr_pct", "hour_utc"):
            if f in feats.columns:
                ctx.setdefault(f, float(feats[f].iloc[-1]) if not np.isnan(feats[f].iloc[-1]) else None)
        dec = _rules.evaluate(self.rules_tree, ctx)
        margin = float(self.decision.get("margin", 0.0)) + dec.margin_add
        return {
            "side": side if dec.allow else None,
            "prob": prob,
            "edge": edge * dec.confidence_mult,
            "allow": dec.allow,
            "margin": margin,
            "reasons": dec.reasons,
        }


def load_pack(path_or_dict) -> Pack:
    if isinstance(path_or_dict, dict):
        return Pack(path_or_dict)
    with open(path_or_dict) as f:
        return Pack(json.load(f))
