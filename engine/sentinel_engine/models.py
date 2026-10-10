"""
sentinel_engine.models
======================
Data-only model loaders. NEVER pickle/joblib. Supported:
  - lightgbm_text : raw LightGBM text dump (requires lightgbm installed)
  - tree_json     : {"trees":[{"split_feature":i,"threshold":t,"left":..,"right":..,"leaf":v}...],
                     "learning_rate":..., "init_score":...}  (simple stumps/depth trees)
  - logreg_json   : {"coef": [...], "intercept": b, "mean": [...], "scale": [...]}
All output P(up) in [0,1] via sigmoid where relevant.
"""
from __future__ import annotations
import base64
import gzip
import json
import math
import numpy as np


def _decode_blob(blob: str, encoding: str) -> str:
    if encoding == "utf8":
        return blob
    if encoding == "base64-gzip":
        return gzip.decompress(base64.b64decode(blob)).decode("utf8")
    if encoding == "base64":
        return base64.b64decode(blob).decode("utf8")
    raise ValueError(f"unknown model encoding {encoding}")


class _LGBMText:
    def __init__(self, text: str):
        from lightgbm import Booster
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, "w") as f:
            f.write(text)
        try:
            self.booster = Booster(model_file=path)
        finally:
            os.unlink(path)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.booster.predict(X)


class _TreeJSON:
    def __init__(self, spec: dict):
        self.trees = spec["trees"]
        self.lr = float(spec.get("learning_rate", 0.1))
        self.init = float(spec.get("init_score", 0.0))

    def _one(self, node, x):
        while "leaf" not in node:
            if x[node["split_feature"]] <= node["threshold"]:
                node = node["left"]
            else:
                node = node["right"]
        return node["leaf"]

    def predict(self, X: np.ndarray) -> np.ndarray:
        out = []
        for x in X:
            s = self.init
            for t in self.trees:
                s += self.lr * self._one(t, x)
            out.append(1.0 / (1.0 + math.exp(-s)))
        return np.array(out)


class _LogRegJSON:
    def __init__(self, spec: dict):
        self.coef = np.array(spec["coef"], dtype=float)
        self.intercept = float(spec.get("intercept", 0.0))
        self.mean = np.array(spec.get("mean", np.zeros_like(self.coef)), dtype=float)
        self.scale = np.array(spec.get("scale", np.ones_like(self.coef)), dtype=float)
        self.scale[self.scale == 0] = 1.0

    def predict(self, X: np.ndarray) -> np.ndarray:
        z = (X - self.mean) / self.scale
        s = z @ self.coef + self.intercept
        return 1.0 / (1.0 + np.exp(-s))


def load_model(model_spec: dict):
    """Return an object with .predict(np.ndarray)->np.ndarray of P(up)."""
    mtype = model_spec.get("type")
    encoding = model_spec.get("encoding", "utf8")
    blob = model_spec.get("blob", "")
    if mtype == "lightgbm_text":
        return _LGBMText(_decode_blob(blob, encoding))
    text = _decode_blob(blob, encoding)
    spec = json.loads(text)
    if mtype == "tree_json":
        return _TreeJSON(spec)
    if mtype == "logreg_json":
        return _LogRegJSON(spec)
    raise ValueError(f"unsupported model type {mtype}")
