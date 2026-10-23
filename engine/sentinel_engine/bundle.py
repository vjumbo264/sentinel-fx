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
from .policy_schema import VERSION, OBSERVATION_DIM

SCHEMA_VERSION = 2
ALLOWED_MODEL_EXT = (".onnx", ".txt", ".json")   # .txt = LightGBM text
BANNED_EXT = (".pkl", ".pickle", ".joblib", ".pt", ".pth", ".ts", ".py",
              ".so", ".dll", ".dylib", ".exe", ".sh")
RECOMMENDED_MAX = 200 * 1024 * 1024              # advisory, per spec


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _scan_onnx(b: bytes) -> list[str]:
    problems=[]
    try:
        import onnx
        model=onnx.load_model_from_string(b)
        for op in model.opset_import:
            if (op.domain or '') not in ('','ai.onnx','ai.onnx.ml'):problems.append('custom ONNX opset domain')
        def tensor(t):
            if t.data_location==onnx.TensorProto.EXTERNAL or t.external_data:problems.append('ONNX external-data tensor: '+t.name)
        def graph(g):
            for t in g.initializer:tensor(t)
            for t in g.sparse_initializer:tensor(t.values);tensor(t.indices)
            for node in g.node:
                if (node.domain or '') not in ('','ai.onnx','ai.onnx.ml'):problems.append('custom ONNX node domain')
                for a in node.attribute:
                    if a.type==onnx.AttributeProto.TENSOR:tensor(a.t)
                    elif a.type==onnx.AttributeProto.TENSORS:
                        for t in a.tensors:tensor(t)
                    elif a.type==onnx.AttributeProto.GRAPH:graph(a.g)
                    elif a.type==onnx.AttributeProto.GRAPHS:
                        for nested in a.graphs:graph(nested)
        graph(model.graph)
        if model.functions:problems.append('custom ONNX local functions forbidden')
    except Exception as error:problems.append('ONNX safety verification failed: '+str(error))
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
        if not n.endswith("/") and not p.lower().endswith(ALLOWED_MODEL_EXT):
            problems.append(f"non-data file: {n}")
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
    listed = {}
    files_spec = manifest.get("files")
    if isinstance(files_spec, dict):
        for p_k, val in files_spec.items():
            if isinstance(val, dict):
                listed[p_k] = val
            elif isinstance(val, str):
                listed[p_k] = {"path": p_k, "sha256": val}
    elif isinstance(files_spec, list):
        for f in files_spec:
            if isinstance(f, dict):
                listed[f.get("path", "")] = f
            elif isinstance(f, str):
                listed[f] = {"path": f}
    else:
        return False, problems + ["manifest files must include explicit hashes and sizes"]

    for n in names:
        if n.endswith("/") or n == "manifest.json":
            continue
        if n not in listed:
            problems.append(f"file not declared in manifest: {n}")
            continue
        b = zf.read(n)
        f = listed[n]
        if not f.get("sha256") or f.get("sha256") != _sha256(b):
            problems.append(f"sha256 mismatch: {n}")
        if f.get("size") is not None and f.get("size") != len(b):
            problems.append(f"size mismatch: {n}")
        if n.lower().endswith(".onnx"):
            problems.extend(_scan_onnx(b))
    for p in listed:
        if p and p not in names:
            problems.append(f"manifest references missing file: {p}")
    # Required core files
    if "analysis_plan.json" not in names:
        problems.append("missing analysis_plan.json")
    if "decision.json" not in names and "policy.json" not in names and "risk_brain.json" not in names:
        problems.append("missing decision.json or policy.json")
    # Verify policy input compatibility BEFORE creating an inference session.
    # Metadata and actual ONNX shapes must both agree; retired 47-d models
    # cannot pass by declaring a new schema around old weights.
    try:
        plan = json.loads(zf.read('analysis_plan.json'))
        policy = json.loads(zf.read('policy.json')) if 'policy.json' in names else json.loads(zf.read('decision.json'))
        dim = policy.get('observation_dim')
        if policy.get('schema_version') != VERSION or dim != OBSERVATION_DIM:
            problems.append(f'observation size mismatch: expected {OBSERVATION_DIM} ({VERSION}), got {dim}; retired, incompatible')
        for node in plan.get('nodes', []):
            if node.get('type') != 'policy':
                continue
            name = node.get('model', '')
            if name.endswith('.onnx') and name in names:
                import onnx
                model = onnx.load_model_from_string(zf.read(name))
                inputs = model.graph.input
                shape = inputs[0].type.tensor_type.shape.dim if len(inputs) == 1 else []
                actual = shape[1].dim_value if len(shape) == 2 else None
                if actual != OBSERVATION_DIM:
                    problems.append(f'policy model input size mismatch: expected {OBSERVATION_DIM}, got {actual}; retired, incompatible')
    except Exception as error:
        problems.append('policy observation compatibility unavailable: ' + str(error))
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
        self.preprocess = json.loads(self.zf.read("preprocess.json")) if "preprocess.json" in self.zf.namelist() else {}
        self.decision = (json.loads(self.zf.read("decision.json")) if "decision.json" in self.zf.namelist()
                         else (json.loads(self.zf.read("policy.json")) if "policy.json" in self.zf.namelist()
                               else (json.loads(self.zf.read("risk_brain.json")) if "risk_brain.json" in self.zf.namelist() else {})))
        self.risk = (json.loads(self.zf.read("risk_brain.json")) if "risk_brain.json" in self.zf.namelist()
                     else (json.loads(self.zf.read("risk.json")) if "risk.json" in self.zf.namelist() else {}))
        self.news_layer = (json.loads(self.zf.read("news_layer.json"))
                           if "news_layer.json" in self.zf.namelist()
                           else {"enabled": False, "learned": False})
        self.training_report = (json.loads(self.zf.read("training_report.json"))
                                if "training_report.json" in self.zf.namelist() else {})
        self._models = {}
        for n in self.plan.get("nodes", []):
            if n.get("model") and n["model"] in self.zf.namelist():
                try:
                    self.model(n["model"])
                except Exception:
                    pass

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
