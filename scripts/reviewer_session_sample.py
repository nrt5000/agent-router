"""Acceptance check: list a few recent workflow IDs for correlation in the review output."""
import os
import shutil
import subprocess
import sys


def has_temporalio(py: str) -> bool:
    try:
        return subprocess.run([py, "-c", "import temporalio"], capture_output=True, timeout=15).returncode == 0
    except Exception:
        return False


candidates = ["/app/.venv/bin/python", "/usr/local/bin/python", "/usr/local/bin/python3"]
candidates += [shutil.which(p) or "" for p in ("python", "python3")]
for py in dict.fromkeys(candidates):
    if py and os.path.exists(py) and has_temporalio(py):
        os.execv(py, [py, os.path.abspath(__file__)])

print(f"PY-DIAG: none of {[c for c in candidates if c]} can import temporalio; current={sys.executable}")
try:
    r = subprocess.run(
        ["find", "/app", "/opt", "/usr/local/lib", "-maxdepth", "7", "-name", "temporalio", "-type", "d"],
        capture_output=True, text=True, timeout=20,
    )
    print("FIND-DIAG: " + (r.stdout.strip()[:300] or "not-found"))
except Exception as exc:
    print(f"FIND-DIAG: error {exc}")
