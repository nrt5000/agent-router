#!/usr/bin/env python3
"""CI delivery diagnostic (v4).

Reports the delivery status of the notification workflow from the prior
run: workflow status, the event sequence with activity names, and any
activity failure reasons. No message contents are printed. Exits
non-zero when the workflow cannot be inspected.
"""

import asyncio
import os
import shutil
import subprocess
import sys

VENV_PYTHON = "/app/.venv/bin/python"
RUNTIME_PROBE = "import temporalio"
WORKFLOW_ID = "slack-event-1794205101-330479"


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

EVENT_NAMES = {
    1: "STARTED",
    2: "WF-COMPLETED",
    3: "WF-FAILED",
    5: "WF-TASK-SCHEDULED",
    6: "WF-TASK-STARTED",
    7: "WF-TASK-COMPLETED",
    9: "WF-TASK-FAILED",
    10: "ACT-SCHEDULED",
    11: "ACT-STARTED",
    12: "ACT-COMPLETED",
    13: "ACT-FAILED",
    14: "ACT-TIMED-OUT",
    25: "MARKER",
    26: "SIGNALED",
    40: "UPSERT-ATTRS",
}


async def inspect() -> int:
    from temporalio.client import Client

    host = os.environ.get("TEMPORAL_HOST", "temporal-frontend.temporal:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "alfred")
    client = await Client.connect(host, namespace=namespace)

    print("DELIVERY-DIAG4-BEGIN")
    handle = client.get_workflow_handle(WORKFLOW_ID)
    try:
        desc = await handle.describe()
        print(f"status: {desc.status}")
    except Exception as e:  # noqa: BLE001
        print(f"describe: FAIL {type(e).__name__}: {e}")
        print("DELIVERY-DIAG4-END")
        return 1

    try:
        history = await handle.fetch_history()
    except Exception as e:  # noqa: BLE001
        print(f"history: FAIL {type(e).__name__}: {e}")
        print("DELIVERY-DIAG4-END")
        return 1

    act_by_event: dict[int, str] = {}
    lines: list[str] = []
    failures: list[str] = []
    for event in history.events:
        num = int(event.event_type)
        name = EVENT_NAMES.get(num, f"EVENT-{num}")
        detail = ""
        if name == "ACT-SCHEDULED":
            attrs = event.activity_task_scheduled_event_attributes
            act_name = str(attrs.activity_type.name)[:44]
            act_by_event[int(event.event_id)] = act_name
            detail = act_name
        elif name == "ACT-FAILED":
            attr = event.activity_task_failed_event_attributes
            act = act_by_event.get(int(attr.scheduled_event_id), f"event-{attr.scheduled_event_id}")
            msg = str(attr.failure.message)[:220]
            failures.append(f"{act}: {msg}")
            detail = f"{act} FAILED"
        elif name == "WF-TASK-FAILED":
            attr = event.workflow_task_failed_event_attributes
            failures.append("WF-TASK: " + str(attr.failure.message)[:220])
            detail = "wf-task failed"
        lines.append(f"{name} {detail}".rstrip())

    print("events:")
    for line in lines:
        print(f"  {line}")
    print(f"failures: {len(failures)}")
    for failure in failures:
        print(f"  FAILURE {failure}")
    print("DELIVERY-DIAG4-END")
    return 0


def main() -> int:
    try:
        return asyncio.run(inspect())
    except Exception as e:  # noqa: BLE001
        print(f"DELIVERY-DIAG4: FAIL {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
