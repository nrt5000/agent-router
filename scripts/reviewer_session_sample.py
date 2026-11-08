"""Acceptance check: list a few recent workflow IDs for correlation in the review output."""
import asyncio
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
chosen = None
for py in dict.fromkeys(candidates):
    if py and os.path.exists(py) and has_temporalio(py):
        chosen = py
        break
print(f"PY-DIAG: chosen={chosen} current={sys.executable}")
if chosen and os.path.realpath(sys.executable) != os.path.realpath(chosen):
    os.execv(chosen, [chosen, os.path.abspath(__file__)])


async def main() -> None:
    from temporalio.client import Client

    client = await asyncio.wait_for(
        Client.connect(os.environ["TEMPORAL_HOST"], namespace=os.environ["TEMPORAL_NAMESPACE"]),
        timeout=15,
    )
    count = 0
    async for wf in client.list_workflows(query="ExecutionStatus = 'Running'", page_size=10):
        count += 1
        print(f"WF-{count}: {wf.id}")
        if count >= 5:
            break


try:
    asyncio.run(asyncio.wait_for(main(), timeout=45))
except Exception as exc:
    print(f"SESSION-DIAG: {type(exc).__name__}: {exc}")
