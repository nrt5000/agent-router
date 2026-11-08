"""Acceptance check: list a few recent workflow IDs for correlation in the review output."""
import os
import sys

VENV_PY = "/app/.venv/bin/python"
if os.path.exists(VENV_PY) and os.path.realpath(sys.executable) != os.path.realpath(VENV_PY):
    os.execv(VENV_PY, [VENV_PY, os.path.abspath(__file__)])

import asyncio


async def main():
    from temporalio.client import Client

    client = await Client.connect(os.environ["TEMPORAL_HOST"], os.environ["TEMPORAL_NAMESPACE"])
    count = 0
    async for wf in client.list_workflows(query="", page_size=10):
        count += 1
        print(f"WF-{count}: {wf.id}")
        if count >= 5:
            break


asyncio.run(main())
