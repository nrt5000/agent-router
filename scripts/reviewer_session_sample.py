#!/usr/bin/env python3
"""Acceptance check: workflow inventory sample for review correlation.

Read-only: connects to the configured Temporal frontend, lists the current
workflow inventory (all types, uncapped), and prints one WF line per workflow
plus a summary. Session-shaped workflow IDs (two-word slug + UUID) are
flagged so they stand out in review correlation.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys

VENV_PYTHON = "/app/.venv/bin/python"
SESSION_ID_RE = re.compile(
    r"^[a-z]+-[a-z]+-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
SESSION_TYPES = {"TaskWorkflow", "LinearConversationWorkflow"}


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


async def _list_inventory() -> None:
    from temporalio.client import Client

    host = os.environ.get("TEMPORAL_HOST") or "temporal-frontend.temporal:7233"
    namespace = os.environ.get("TEMPORAL_NAMESPACE") or "alfred"

    client = await Client.connect(host, namespace=namespace)

    total = 0
    session_shaped = 0
    async for wf in client.list_workflows():
        total += 1
        raw_type = getattr(wf, "workflow_type", None)
        wf_type = getattr(raw_type, "name", None) or str(raw_type)
        wf_id = getattr(wf, "id", "?")
        status = getattr(wf, "status", None)
        start_time = getattr(wf, "start_time", None)
        shaped = (
            wf_type in SESSION_TYPES
            or bool(SESSION_ID_RE.match(str(wf_id)))
            or ("PullRequest" not in wf_type and "Review" not in wf_type)
        )
        if shaped:
            session_shaped += 1
        marker = "SESSION-SHAPED" if shaped else "pr"
        print(
            f"WF-{total}: [{wf_type}] {wf_id} status={status} "
            f"start={start_time} class={marker}"
        )
    print(
        f"SUMMARY: {total} workflows listed, {session_shaped} session-shaped"
    )


def main() -> None:
    interpreter = _select_interpreter()
    if interpreter is None:
        print("SESSION-DIAG: no temporalio-capable interpreter available")
        return
    print(
        f"SESSION-DIAG: chosen={interpreter} current={sys.executable} "
        f"host={os.environ.get('TEMPORAL_HOST') or 'default'} "
        f"ns={os.environ.get('TEMPORAL_NAMESPACE') or 'default'}"
    )
    if sys.executable != interpreter:
        # String comparison on purpose: the venv python is a symlink, so a
        # realpath comparison silently fails to match.
        os.execv(interpreter, [interpreter, os.path.abspath(__file__)])
    asyncio.run(_list_inventory())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"SESSION-DIAG: {type(exc).__name__}: {exc}")
