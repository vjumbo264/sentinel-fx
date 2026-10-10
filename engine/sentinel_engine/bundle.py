"""
sentinel_engine.bundle — .sfxmodel.zip (schema_version 2) loader/verifier.

A bundle is a plain zip containing DATA ONLY:
  manifest.json, analysis_plan.json, preprocess.json, decision.json,
  risk.json, news_layer.json, training_report.json, tests/*.json,
  and model files (ONNX preferred; LightGBM text; XGBoost JSON; tree_json;
  logreg_json). NO pickle/joblib/torch.save, NO custom ONNX operator domains,
  NO ONNX external-data references, NO path traversal, NO code execution.

verify_bundle(path) -> (ok, problems) performs the full static gate used by
the validator and the bot before anything is executed.
"""
from __future__ import annotations
import hashlib
import io
import json
import zipfile

SCHEMA_VERSION = 2
ALLOWED_MODEL_EXT = (".onnx", ".txt", ".json")   # .txt = LightGBM text
BANNED_EXT = (".pkl", ".pickle", ".joblib", ".pt", ".pth", ".ts", ".py",
              ".so", ".dll", ".dylib", ".exe", ".sh")
RECOMMENDED_MAX = 200 * 1024 * 1024              # advisory, per spec


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _scan_onnx(b: bytes) -> list[str]:
    """Reject custom operator domains and external-data references without
    executing anything. Best-effort protobuf parse of ModelProto."""
    problems = []
    try:
        import onnx  # optional; only needed to load ONNX bundles
        m = onnx.load_model_from_string(b)
        for op in m.opset_import:
            dom = (op.domain or "").strip()
            if dom not in ("", "ai.onnx", "ai.onnx.ml"):
                problems.append(f"custom ONNX opset domain: {dom!r}")
        for node in m.graph.node:
            if node.domain not in ("", "ai.onnx", "ai.onnx.ml"):
                problems.append(f"custom ONNX node domain: {node.domain!r}")
        if m.graph.HasField("metadata_props"):
            for p in m.graph.metadata_props:
                if p.key == "model_bytes" and p.value == "":
                    pass
        for t in list(m.graph.initializer):
            if t.data_location == 1:  # EXTERNAL
                problems.append(f"ONNX external-data tensor: {t.name}")
    except ImportError:
        # onnx not installed: fall back to a byte-level sniff for the
        # external-data marker so obviously-unsafe files are still rejected.
        if b"external_data" in b[:65536] and b"location" in b[:65536]:
            problems.append("possible ONNX external-data reference (unverified, onnx not installed)")
    except Exception as e:
        problems.append(f"ONNX parse failed: {e}")
    return problems


def verify_bundle(path: str) -> tuple[bool, list[str]]:
    problems: list[str] = []
    try:
        zf = zipfile.ZipFile(path)
    except Exception as e:
        return False, [f"not a zip: {e}"]
    names = zf.namelist()
    for n in names:
        p = n.replace("\\", "/")
        if p.startswith("/") or ".." in p.split("/"):
            problems.append(f"path traversal entry: {n}")
        if p.lower().endswith(BANNED_EXT):
            problems.append(f"banned file type: {n}")
    if "manifest.json" not in names:
        problems.append("missing manifest.json")
        return False, problems
    try:
        manifest = json.loads(zf.read("manifest.json"))
    except Exception as e:
        return False, problems + [f"manifest unreadable: {e}"]
    if manifest.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version != {SCHEMA_VERSION}")
    listed = {f["path"]: f for f in manifest.get("files", [])}
    for n in names:
        if n.endswith("/"):
            continue
        if n not in listed:
            problems.append(f"file not declared in manifest: {n}")
            continue
        b = zf.read(n)
        f = listed[n]
        if f.get("sha256") != _sha256(b):
            problems.append(f"sha256 mismatch: {n}")
        if f.get("size") != len(b):
            problems.append(f"size mismatch: {n}")
        if n.lower().endswith(".onnx"):
            problems.extend(_scan_onnx(b))
    for p in listed:
        if p not in names:
            problems.append(f"manifest references missing file: {p}")
    for req in ("analysis_plan.json", "preprocess.json", "decision.json"):
        if req not in names:
            problems.append(f"missing {req}")
    return not problems, problems


class Bundle:
    """Loaded, verified bundle. Data only — nothing executed at load time."""

    def __init__(self, path: str, verified: bool = True):
        ok, problems = verify_bundle(path)
        if not ok:
            raise ValueError("bundle rejected: " + "; ".join(problems))
        self.path = path
        self.zf = zipfile.ZipFile(path)
        self.manifest = json.loads(self.zf.read("manifest.json"))
        self.symbol = self.manifest.get("symbol")
        self.version = self.manifest.get("version")
        self.plan = json.loads(self.zf.read("analysis_plan.json"))
        self.preprocess = json.loads(self.zf.read("preprocess.json"))
        self.decision = json.loads(self.zf.read("decision.json"))
        self.risk = json.loads(self.zf.read("risk.json")) if "risk.json" in self.zf.namelist() else {}
        self.news_layer = (json.loads(self.zf.read("news_layer.json"))
                           if "news_layer.json" in self.zf.namelist()
                           else {"enabled": False, "learned": False})
        self.training_report = (json.loads(self.zf.read("training_report.json"))
                                if "training_report.json" in self.zf.namelist() else {})
        self._models = {}

    def model(self, name: str):
        if name in self._models:
            return self._models[name]
        b = self.zf.read(name)
        if name.endswith(".onnx"):
            import onnxruntime as ort
            mdl = ort.InferenceSession(io.BytesIO(b).read(),
                                       providers=["CPUExecutionProvider"])
        else:
            from .models import load_model
            import base64
            kind = "lightgbm_text" if name.endswith(".txt") else \
                   ("tree_json" if "tree" in name else "logreg_json")
            mdl = load_model({"type": kind, "encoding": "base64",
                              "blob": base64.b64encode(b).decode()})
        self._models[name] = mdl
        return mdl


def load_bundle(path: str) -> Bundle:
    return Bundle(path)
