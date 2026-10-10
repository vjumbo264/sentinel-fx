"""Sandboxed runner for pack custom code. Security boundary is the sandbox:
separate subprocess, EMPTY environment (no secrets), no network, resource
limits, JSON in/out with size cap. FAIL CLOSED: if isolation is unavailable,
raise SandboxUnavailable and the caller must refuse custom-code packs.

Static scan (engine.static_scan) is an early filter only, NOT the boundary.
"""
import base64, gzip, json, os, subprocess, sys, tempfile

MAX_CODE_BYTES = 256 * 1024
MAX_OUT_BYTES = 4 * 1024 * 1024

class SandboxUnavailable(RuntimeError):
    pass
class SandboxError(RuntimeError):
    pass

_RUNNER = r'''
import sys, json, base64, gzip, importlib.util
code = gzip.decompress(base64.b64decode(sys.argv[1])).decode("utf-8")
spec = importlib.util.spec_from_loader("packmod", loader=None)
mod = importlib.util.module_from_spec(spec)
exec(compile(code, "packmod", "exec"), mod.__dict__)
candles = json.loads(sys.stdin.read())
out = mod.compute(candles, json.loads(sys.argv[2]))
sys.stdout.write(json.dumps(out.to_dict(orient="list"))[:%d])
''' % MAX_OUT_BYTES

def network_isolation_available() -> bool:
    import shutil
    return shutil.which("unshare") is not None

def run_custom_module(name: str, code_b64gz: str, candles, params: dict | None = None):
    raw = gzip.decompress(base64.b64decode(code_b64gz))
    if len(raw) > MAX_CODE_BYTES:
        raise SandboxError(f"module {name}: code exceeds {MAX_CODE_BYTES} bytes")
    if not network_isolation_available():
        raise SandboxUnavailable("no network isolation (unshare) available; refusing to run custom code")
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(_RUNNER); runner = f.name
    try:
        cmd = ["unshare", "--net", "--", sys.executable, "-I", runner, code_b64gz, json.dumps(params or {})]
        proc = subprocess.run(
            cmd, input=json.dumps(candles), capture_output=True, text=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "0"},  # empty-ish env: NO secrets
            timeout=30, cwd="/",
        )
        if proc.returncode != 0:
            raise SandboxError(f"module {name} failed: {proc.stderr[-500:]}")
        if len(proc.stdout) > MAX_OUT_BYTES:
            raise SandboxError(f"module {name}: output too large")
        import pandas as pd
        return pd.DataFrame(json.loads(proc.stdout))
    finally:
        os.unlink(runner)
