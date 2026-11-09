#!/usr/bin/env python3
"""CI delivery diagnostic.

Reports the delivery status of the notification workflow from the prior
run: workflow status, event sequence, and any failure reason. No message
contents are printed. Exits non-zero when the workflow cannot be inspected.
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


async def inspect() -> int:
    from temporalio.client import Client

    host = os.environ.get("TEMPORAL_HOST", "temporal-frontend.temporal:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "alfred")
    client = await Client.connect(host, namespace=namespace)

    print("DELIVERY-DIAG-BEGIN")
    handle = client.get_workflow_handle(WORKFLOW_ID)
    try:
        desc = await handle.describe()
        print(f"workflow: id={WORKFLOW_ID}")
        print(f"status: {desc.status}")
        print(f"run_id: {str(desc.run_id)[:12]}...")
    except Exception as e:  # noqa: BLE001
        print(f"describe: FAIL {type(e).__name__}: {e}")
        print("DELIVERY-DIAG-END")
        return 1

    try:
        history = await handle.fetch_history()
    except Exception as e:  # noqa: BLE001
        print(f"history: FAIL {type(e).__name__}: {e}")
        print("DELIVERY-DIAG-END")
        return 1

    event_types: list[str] = []
    failure_reason: str | None = None
    for event in history.events:
        et = event.event_type
        name = str(et).rsplit(".", 1)[-1]
        if not event_types or event_types[-1] != name:
            event_types.append(name)
        if "WorkflowExecutionFailed" in str(et):
            attr = event.workflow_execution_failed_event_attributes
            failure_reason = str(attr.failure.message)[:300]
        if "WorkflowTaskFailed" in str(et):
            attr = event.workflow_task_failed_event_attributes
            failure_reason = str(attr.failure.message)[:300]
    print("event-sequence: " + " -> ".join(event_types))
    if failure_reason:
        print(f"failure-reason: {failure_reason}")
    else:
        print("failure-reason: none")
    print("DELIVERY-DIAG-END")
    return 0


def main() -> int:
    try:
        return asyncio.run(inspect())
    except Exception as e:  # noqa: BLE001
        print(f"DELIVERY-DIAG: FAIL {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
