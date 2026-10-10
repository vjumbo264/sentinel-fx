"""Data-only model loaders. NEVER pickle/joblib.

Supported types:
  tree_json      - {"trees":[{"feat":i,"thr":x,"left":L,"right":R,"value":v|null,...}], "base_score":0.5}
                   node: if value is not null -> leaf probability; else branch feat<thr.
  logreg_json    - {"coef":[...], "intercept":b} -> sigmoid(dot(coef,x)+b)
  lightgbm_text  - standard LightGBM text model; used only when lightgbm is installed.
"""
import math, base64, gzip

def _decode_blob(model: dict) -> str:
    blob = model.get("blob", "")
    if model.get("encoding") == "base64-gzip":
        return gzip.decompress(base64.b64decode(blob)).decode("utf-8")
    return blob

class LoadedModel:
    def __init__(self, spec: dict):
        self.spec = spec
        self.type = spec.get("type")
        self.features = list(spec.get("input_features", []))
        if self.type == "tree_json":
            import json
            self.model = json.loads(_decode_blob(spec))
        elif self.type == "logreg_json":
            import json
            d = json.loads(_decode_blob(spec))
            self.model = (list(map(float, d["coef"])), float(d["intercept"]))
        elif self.type == "lightgbm_text":
            import lightgbm as lgb  # optional dependency
            self.model = lgb.Booster(model_str=_decode_blob(spec))
        else:
            raise ValueError(f"unsupported model type {self.type!r}")

    def predict_proba(self, row) -> float:
        """row: mapping feature-name -> float. Returns P(up)."""
        if self.type == "tree_json":
            p = float(self.model.get("base_score", 0.5))
            for tree in self.model.get("trees", []):
                p += self._walk(tree, row)
            return min(1.0, max(0.0, 1.0 / (1.0 + math.exp(-p))))
        if self.type == "logreg_json":
            coef, b = self.model
            z = b + sum(c * float(row.get(f, 0.0)) for c, f in zip(coef, self.features))
            return 1.0 / (1.0 + math.exp(-z))
        if self.type == "lightgbm_text":
            import numpy as np
            x = np.array([[float(row.get(f, 0.0)) for f in self.features]])
            return float(self.model.predict(x)[0])
        raise ValueError(self.type)

    def _walk(self, node, row):
        if node.get("value") is not None:
            return float(node["value"])
        v = float(row.get(self.features[node["feat"]], 0.0)) if isinstance(node.get("feat"), int) else float(row.get(node.get("feat"), 0.0))
        return self._walk(node["left"] if v < float(node["thr"]) else node["right"], row)

def load_model(spec: dict) -> LoadedModel:
    return LoadedModel(spec)
