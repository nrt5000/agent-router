#!/usr/bin/env python3
"""Acceptance check: runner-capacity lease audit.

Validates that lease-holder history on the runner-capacity workflow remains
readable across continue-as-new runs — the holder records are what review
correlation uses to tie runner jobs back to their workflows.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys

VENV_PYTHON = "/app/.venv/bin/python"
CAPACITY_ID = "alfred-runner-capacity"
HOSTS = [
    "temporal-frontend.temporal:7233",
]
NAMESPACES = ["alfred"]
HOLDER_RE = re.compile(
    rb"([a-z]+-[a-z]+-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    rb":([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)
TIME_BUDGET_SECONDS = 60


def _supports_temporalio(python: str) -> bool:
    """Return whether the interpreter can import temporalio."""
    try:
        proc = subprocess.run(
            [python, "-c", "import temporalio"],
            capture_output=True,
            timeout=30,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _select_interpreter() -> str | None:
    candidates = [VENV_PYTHON, sys.executable]
    for candidate in candidates:
        if candidate and _supports_temporalio(candidate):
            return candidate
    return None


async def _connect():
    from temporalio.client import Client

    hosts = []
    env_host = os.environ.get("TEMPORAL_HOST")
    if env_host:
        hosts.append(env_host)
    hosts.extend(HOSTS)
    namespaces = []
    env_ns = os.environ.get("TEMPORAL_NAMESPACE")
    if env_ns:
        namespaces.append(env_ns)
    namespaces.extend(NAMESPACES)

    last_error: Exception | None = None
    for host in hosts:
        for namespace in namespaces:
            try:
                return await Client.connect(host, namespace=namespace)
            except Exception as exc:
                last_error = exc
    assert last_error is not None
    raise last_error


async def _events(handle):
    fetch_events = getattr(handle, "fetch_history_events", None)
    if fetch_events is not None:
        async for event in fetch_events(page_size=500):
            yield event
    else:
        history = await handle.fetch_history()
        for event in history.events:
            yield event


def _blob(event) -> bytes:
    serialize = getattr(event, "SerializeToString", None)
    if serialize is not None:
        try:
            return serialize()
        except Exception:
            pass
    return str(event).encode("utf-8", "ignore")


async def _audit() -> int:
    from temporalio.client import Client

    client: Client = await _connect()

    runs: dict[str, str] = {}
    async for wf in client.list_workflows():
        if str(wf.id) == CAPACITY_ID:
            runs[str(wf.run_id)] = str(wf.id)
    latest = client.get_workflow_handle(CAPACITY_ID)
    try:
        description = await latest.describe()
        runs.setdefault(str(description.run_id), CAPACITY_ID)
    except Exception:
        pass

    if not runs:
        print("AUDIT-FAIL: no runner-capacity workflow runs found")
        return 1

    holders: list[str] = []
    seen: set[str] = set()
    scanned_events = 0
    partial = False
    loop = asyncio.get_running_loop()
    deadline = loop.time() + TIME_BUDGET_SECONDS
    for run_id in runs:
        handle = client.get_workflow_handle(CAPACITY_ID, run_id=run_id)
        try:
            async for event in _events(handle):
                scanned_events += 1
                for holder, _run in HOLDER_RE.findall(_blob(event)):
                    text = holder.decode()
                    if text not in seen:
                        seen.add(text)
                        holders.append(text)
                if loop.time() > deadline:
                    partial = True
                    break
        except Exception as exc:
            print(f"AUDIT-NOTE: run {run_id} unreadable: {type(exc).__name__}")
        if partial:
            break

    for index, holder in enumerate(holders, start=1):
        print(f"LEASE-{index}: {holder}")
    print(
        f"AUDIT-SUMMARY: runs={len(runs)} events={scanned_events} "
        f"holders={len(holders)} partial={partial}"
    )
    print("AUDIT-OK" if holders or not partial else "AUDIT-FAIL: nothing readable")
    return 0


def main() -> int:
    interpreter = _select_interpreter()
    if interpreter is None:
        print("AUDIT-FAIL: no temporalio-capable interpreter available")
        return 1
    print(f"AUDIT-DIAG: chosen={interpreter} current={sys.executable}")
    if sys.executable != interpreter:
        # String comparison on purpose: the venv python is a symlink, so a
        # realpath comparison silently fails to match.
        os.execv(interpreter, [interpreter, os.path.abspath(__file__)])
    return asyncio.run(_audit())


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"AUDIT-FAIL: {type(exc).__name__}: {exc}")
        sys.exit(1)
