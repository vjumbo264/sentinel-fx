import os, subprocess, sys
FIX = os.path.join(os.path.dirname(__file__), "fixtures")
def run(f, mode="fast"):
    return subprocess.run([sys.executable, "-m", "sentinel_engine.validate",
                           os.path.join(FIX, f), "--mode", mode],
                          capture_output=True, text=True)
def test_leaky_rejected():
    r = run("leaky.pairpack.json"); assert r.returncode != 0
def test_tampered_rejected():
    r = run("tampered.pairpack.json"); assert r.returncode != 0
def test_malicious_rejected():
    r = run("malicious.pairpack.json"); assert r.returncode != 0
if __name__ == "__main__":
    test_leaky_rejected(); test_tampered_rejected(); test_malicious_rejected()
    print("all fixture packs correctly REJECTED")
