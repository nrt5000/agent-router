#!/usr/bin/env python3
"""CI delivery status check.

Reports the status of the delivery workflow and the notification
workflow pool: describes the designated delivery workflow, summarizes
the tail of its history (which activity it is waiting on), and counts
active notification workflows by their current phase. Read-only Temporal
queries; no signals are sent and no credentials are exposed. Exits
non-zero only if the queries themselves fail.
"""

import asyncio
import os
import pathlib
import shutil
import subprocess
import sys

VENV_PYTHON = "/app/.venv/bin/python"
RUNTIME_PROBE = "import temporalio, alfred.contracts.slack, pydantic_ai"
DELIVERY_WORKFLOW_ID = "slack-event-1794205101-330479"


def _supports_runtime(python: str) -> bool:
    try:
        proc = subprocess.run([python, "-c", RUNTIME_PROBE], capture_output=True, timeout=30)
        return proc.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _ensure_runtime() -> None:
    candidates = [VENV_PYTHON, sys.executable]
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    candidates.extend(["/usr/local/bin/python3", "/usr/bin/python3"])
    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            unique.append(c)
    for candidate in unique:
        if _supports_runtime(candidate):
            if sys.executable != candidate:
                os.execv(candidate, [candidate, os.path.abspath(__file__), *sys.argv[1:]])
            return


_ensure_runtime()


async def status() -> dict:
    from temporalio.client import Client

    host = os.environ.get("TEMPORAL_HOST", "temporal-frontend.temporal:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "alfred")
    try:
        from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

        client = await Client.connect(host, namespace=namespace, plugins=[PydanticAIPlugin()])
    except Exception:  # noqa: BLE001
        client = await Client.connect(host, namespace=namespace)

    out: dict = {}

    handle = client.get_workflow_handle(DELIVERY_WORKFLOW_ID)
    try:
        desc = await handle.describe()
        out["delivery-workflow"] = {
            "id": DELIVERY_WORKFLOW_ID,
            "status": str(desc.status),
            "start_time": str(desc.start_time),
        }
    except Exception as e:  # noqa: BLE001
        out["delivery-workflow"] = {"id": DELIVERY_WORKFLOW_ID, "error": f"{type(e).__name__}: {e}"}
        return out

    # Summarize the last few history events to see what it is waiting on.
    tail = []
    try:
        async for event in handle.fetch_history_events():
            tail.append(event)
            if len(tail) > 4000:
                break
        recent = tail[-14:]
        lines = []
        for ev in recent:
            kind = ev.WhichOneof("attributes")
            attrs = getattr(ev, kind) if kind else None
            detail = ""
            if kind == "activity_task_scheduled_event_attributes":
                detail = f"sched-activity={attrs.activity_type.name}"
            elif kind == "activity_task_started_event_attributes":
                detail = "started-activity"
            elif kind == "activity_task_completed_event_attributes":
                detail = "completed-activity"
            elif kind == "activity_task_failed_event_attributes":
                detail = "failed-activity"
            elif kind == "workflow_task_scheduled_event_attributes":
                detail = "wf-task"
            elif kind == "workflow_task_completed_event_attributes":
                detail = "wf-task-done"
            elif kind == "workflow_execution_signaled_event_attributes":
                detail = f"signal={attrs.signal_name}"
            lines.append(f"event {ev.event_id}: {kind} {detail}")
        out["delivery-history-tail"] = lines
    except Exception as e:  # noqa: BLE001
        out["delivery-history-tail"] = [f"error {type(e).__name__}: {e}"]

    # Notification workflow pool health by phase label.
    phases: dict[str, int] = {}
    try:
        async for wf in client.list_workflows(query="WorkflowType = 'SlackChannelParticipantWorkflow'"):
            label = str(getattr(wf, "status", "?"))
            search = ""
            try:
                search = json_dumps_search(wf)
            except Exception:  # noqa: BLE001
                pass
            phases[label] = phases.get(label, 0) + 1
    except Exception as e:  # noqa: BLE001
        out["pool-error"] = f"{type(e).__name__}: {e}"
    out["notification-workflow-pool"] = phases
    return out


def json_dumps_search(wf) -> str:  # pragma: no cover - helper
    import json

    memo = getattr(wf, "memo", None) or {}
    return json.dumps(memo)[:120]


def main() -> int:
    print("DELIVERY-STATUS-BEGIN")
    try:
        out = asyncio.run(status())
    except Exception as e:  # noqa: BLE001
        print(f"DELIVERY-STATUS: FAIL {type(e).__name__}: {e}")
        print("DELIVERY-STATUS-END")
        return 1
    dw = out.get("delivery-workflow", {})
    print(f"delivery-workflow: {dw.get('id')} status={dw.get('status') or dw.get('error')}")
    print(f"started: {dw.get('start_time', 'unknown')}")
    print("history-tail (latest events):")
    for line in out.get("delivery-history-tail", []):
        print(f"  {line}")
    if "notification-workflow-pool" in out:
        print("notification-workflow-pool:")
        for phase, count in sorted(out["notification-workflow-pool"].items()):
            print(f"  {phase}: {count}")
    if "pool-error" in out:
        print(f"pool-error: {out['pool-error']}")
    print("DELIVERY-STATUS-END")
    return 0


if __name__ == "__main__":
    sys.exit(main())
