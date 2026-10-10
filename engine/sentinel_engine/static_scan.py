"""Static safety scan of custom module source. EARLY FILTER ONLY - the sandbox
(engine.sandbox) is the real security boundary."""
import ast, base64, gzip

BANNED_NAMES = {"os", "sys", "subprocess", "socket", "open", "eval", "exec",
                "__import__", "ctypes", "importlib", "builtins", "globals",
                "locals", "compile", "input", "getattr", "setattr", "delattr",
                "memoryview", "breakpoint", "exit", "quit", "help", "vars",
                "shutil", "pathlib", "io", "threading", "multiprocessing",
                "signal", "requests", "urllib", "http", "ftplib", "pickle", "marshal"}
ALLOWED_IMPORTS = {"numpy", "pandas", "math", "scipy.signal", "scipy.stats", "scipy"}

def scan_code(code: str):
    """Returns list of findings (empty = clean)."""
    findings = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"syntax error: {e}"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in ALLOWED_IMPORTS:
                    findings.append(f"banned import: {a.name}")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                findings.append(f"banned import-from: {node.module}")
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            findings.append(f"banned name: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            findings.append(f"dunder attribute access: {node.attr}")
    return findings

def scan_module(code_b64gz: str):
    try:
        code = gzip.decompress(base64.b64decode(code_b64gz)).decode("utf-8")
    except Exception as e:
        return [f"cannot decode module: {e}"]
    return scan_code(code)
