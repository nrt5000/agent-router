"""Acceptance check: list recent workflows with types for correlation in the review output."""
import asyncio
import os
import shutil
import subprocess
import sys

HOST = os.environ.get("TEMPORAL_HOST") or "temporal-frontend.temporal:7233"
NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE") or "alfred"


def has_temporalio(py: str) -> bool:
    try:
        return subprocess.run([py, "-c", "import temporalio"], capture_output=True, timeout=15).returncode == 0
    except Exception:
        return False


candidates = ["/app/.venv/bin/python", "/usr/local/bin/python", "/usr/local/bin/python3"]
candidates += [shutil.which(p) or "" for p in ("python", "python3")]
chosen = None
for py in dict.fromkeys(candidates):
    if py and os.path.exists(py) and has_temporalio(py):
        chosen = py
        break
print(f"PY-DIAG: chosen={chosen} current={sys.executable} host={HOST} ns={NAMESPACE}")
if chosen and sys.executable != chosen:
    os.execv(chosen, [chosen, os.path.abspath(__file__)])


async def main() -> None:
    from temporalio.client import Client

    client = await asyncio.wait_for(Client.connect(HOST, namespace=NAMESPACE), timeout=15)
    count = 0
    async for wf in client.list_workflows(query="", page_size=20):
        count += 1
        print(f"WF-{count}: [{wf.workflow_type}] {wf.id}")
        if count >= 10:
            break


try:
    asyncio.run(asyncio.wait_for(main(), timeout=45))
except Exception as exc:
    print(f"SESSION-DIAG: {type(exc).__name__}: {exc}")
