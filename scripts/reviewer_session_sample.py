"""Acceptance check: list a few recent workflow IDs for correlation in the review output."""
import asyncio
import os


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
    asyncio.run(asyncio.wait_for(main(), timeout=40))
except Exception as exc:
    print(f"SESSION-DIAG: {type(exc).__name__}: {exc}")
