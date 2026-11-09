#!/usr/bin/env python3
"""CI notification workflow health audit.

Checks the health of notification channel workflows: lists each channel
participant workflow, its status, and whether its conversation turn is
waiting. Reports counts only plus per-workflow status lines (no message
contents). Exits non-zero when the audit cannot run.
"""

import asyncio
import os
import shutil
import subprocess
import sys

VENV_PYTHON = "/app/.venv/bin/python"
RUNTIME_PROBE = "import temporalio"

EVENT_NAMES = {
    1: "STARTED",
    2: "WF-COMPLETED",
    3: "WF-FAILED",
    5: "WF-TASK-SCHEDULED",
    6: "WF-TASK-STARTED",
    7: "WF-TASK-COMPLETED",
    10: "ACT-SCHEDULED",
    11: "ACT-STARTED",
    12: "ACT-COMPLETED",
    13: "ACT-FAILED",
    26: "SIGNALED",
}


def _supports_runtime(python: str) -> bool:
    try:
        proc = subprocess.run(
            [python, "-c", RUNTIME_PROBE], capture_output=True, timeout=30
        )
        return proc.returncode == 0
    except Exception:
        return False


def _ensure_runtime() -> None:
    for candidate in [VENV_PYTHON, sys.executable]:
        if candidate and _supports_runtime(candidate):
            if sys.executable != candidate:
                os.execv(candidate, [candidate, os.path.abspath(__file__), *sys.argv[1:]])
            return
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found and _supports_runtime(found):
            if sys.executable != found:
                os.execv(found, [found, os.path.abspath(__file__), *sys.argv[1:]])
            return


_ensure_runtime()


def summarize(history) -> str:
    last = ""
    pending_model = False
    model_started = False
    count = 0
    for event in history.events:
        num = int(event.event_type)
        name = EVENT_NAMES.get(num, f"E{num}")
        if name == "ACT-SCHEDULED":
            attrs = event.activity_task_scheduled_event_attributes
            act = str(attrs.activity_type.name)
            if "model_request" in act:
                pending_model = True
                last = "model-scheduled"
                count += 1
        elif name == "ACT-STARTED":
            pending_model = False
            last = "act-started"
        elif name == "ACT-COMPLETED":
            if last != "model-scheduled":
                last = "act-completed"
            if pending_model is False and last == "act-completed":
                pass
        elif name in ("ACT-FAILED",):
            pending_model = False
            last = "act-failed"
        elif name in ("WF-COMPLETED", "WF-FAILED"):
            last = name.lower()
        if name == "ACT-STARTED" and last == "model-scheduled":
            model_started = True
    if pending_model:
        return "waiting-on-model"
    if model_started:
        return "model-ran"
    return last or "no-events"


async def audit() -> int:
    from temporalio.client import Client

    host = os.environ.get("TEMPORAL_HOST", "temporal-frontend.temporal:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "alfred")
    client = await Client.connect(host, namespace=namespace)

    print("HEALTH-AUDIT-BEGIN")
    statuses: dict[str, int] = {}
    waiting = 0
    total = 0
    async for wf in client.list_workflows(
        query="WorkflowType = 'SlackChannelParticipantWorkflow'"
    ):
        total += 1
        handle = client.get_workflow_handle(wf.id)
        try:
            desc = await handle.describe()
            status = str(desc.status).rsplit(".", 1)[-1]
        except Exception:
            status = "unknown"
        try:
            history = await handle.fetch_history()
            summary = summarize(history)
        except Exception:
            summary = "history-error"
        if summary == "waiting-on-model":
            waiting += 1
        statuses[f"{status}/{summary}"] = statuses.get(f"{status}/{summary}", 0) + 1
        print(f"  wf {str(wf.id)[:34]}... {status} {summary}")

    print(f"total: {total}")
    print(f"waiting-on-model: {waiting}")
    for key, value in sorted(statuses.items()):
        print(f"  {key}: {value}")
    print("HEALTH-AUDIT-END")
    return 0


def main() -> int:
    try:
        return asyncio.run(audit())
    except Exception as e:  # noqa: BLE001
        print(f"HEALTH-AUDIT: FAIL {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
