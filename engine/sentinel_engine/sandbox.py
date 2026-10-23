"""
sentinel_engine.sandbox
=======================
Isolated runner for pack custom-code modules. The module source is written to a
temp dir and executed as a SUBPROCESS with:
  - EMPTY environment (no env vars -> no secrets)
  - no network (unshare -n when available; otherwise FAIL CLOSED)
  - CPU / memory / wall-time limits
  - candles in via stdin, features out via stdout as JSON (size-capped)
The bot process holds secrets; the sandbox never does.
If network isolation cannot be achieved, sandbox_available() is False and the
caller MUST refuse to run custom-code packs (fail closed).
"""
from __future__ import annotations
import json
import os
try:
    import resource
except ImportError:
    resource = None
import shutil
import subprocess
import sys
import tempfile

MAX_STDOUT_BYTES = 8 * 1024 * 1024
DEFAULT_CPU_S = 20
DEFAULT_MEM_MB = 512
DEFAULT_WALL_S = 30

_CHILD = r'''
import json, sys, importlib.util
def _limited(kind, soft):
    try:
        resource.setrlimit(kind, (soft, soft))
    except Exception:
        pass
import resource
_limited(resource.RLIMIT_CPU, CPU_S)
_limited(resource.RLIMIT_AS, MEM_B)
spec = importlib.util.spec_from_file_location("pack_module", "MODULE_PATH")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
candles = json.loads(sys.stdin.read())
params = json.loads(open("PARAMS_PATH").read())
res = mod.compute(candles, params)
if hasattr(res, "to_dict"):
    res = res.to_dict(orient="list")
out = json.dumps({"ok": True, "features": res})
if len(out) > MAX_OUT:
    print(json.dumps({"ok": False, "error": "output too large"}))
else:
    print(out)
'''


def sandbox_available() -> bool:
    """True iff we can launch a child with network disabled and empty env."""
    if resource is None or not shutil.which("unshare"):
        return False
    try:
        r = subprocess.run(
            ["unshare", "-n", sys.executable, "-c", "print('ok')"],
            capture_output=True, text=True, timeout=10, env={},
        )
        return r.returncode == 0 and "ok" in r.stdout
    except Exception:
        return False


def run_module(code: str, candles: list, params: dict,
               cpu_s: int = DEFAULT_CPU_S, mem_mb: int = DEFAULT_MEM_MB,
               wall_s: int = DEFAULT_WALL_S) -> dict:
    """Execute custom module source. Returns {"ok":bool,"features":...,"error":...}.
    Raises RuntimeError('sandbox unavailable') when network isolation is missing."""
    if not sandbox_available():
        raise RuntimeError("sandbox unavailable: cannot isolate network; refusing to run custom code (fail closed)")
    with tempfile.TemporaryDirectory() as td:
        mpath = os.path.join(td, "pack_module.py")
        ppath = os.path.join(td, "params.json")
        with open(mpath, "w") as f:
            f.write(code)
        with open(ppath, "w") as f:
            json.dump(params, f)
        child = (_CHILD
                 .replace("CPU_S", str(int(cpu_s)))
                 .replace("MEM_B", str(int(mem_mb) * 1024 * 1024))
                 .replace("MODULE_PATH", mpath)
                 .replace("PARAMS_PATH", ppath)
                 .replace("MAX_OUT", str(MAX_STDOUT_BYTES)))
        script = os.path.join(td, "child.py")
        with open(script, "w") as f:
            f.write(child)
        try:
            r = subprocess.run(
                ["unshare", "-n", sys.executable, script],
                input=json.dumps(candles), capture_output=True, text=True,
                timeout=wall_s, env={},
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"wall time {wall_s}s exceeded"}
        if r.returncode != 0:
            return {"ok": False, "error": (r.stderr or "nonzero exit")[:2000]}
        try:
            out = json.loads(r.stdout)
        except Exception:
            return {"ok": False, "error": f"bad stdout: {r.stdout[:500]}"}
        return out
