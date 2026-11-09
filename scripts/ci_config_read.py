#!/usr/bin/env python3
"""CI repository configuration check.

Verifies the CI workspace can read the Alfred repository configuration used
by CI tooling: fetches the pinned upstream configuration commit with the
workspace's configured credentials and reads .alfred.yaml from it. Only the
file size, digest, and version field are printed; no full contents are
exposed. Exits non-zero on any failure so CI treats the result strictly.
"""

import hashlib
import pathlib
import subprocess
import sys

PINNED_COMMIT = "3bbd6cd54845f0c6071da09af3716cdddc9bb70a"
PRIVATE_REPO_URL = "https://github.com/nscaledev/alfred.git"
CONFIG_PATH = ".alfred.yaml"


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


def main() -> int:
    print("CONFIG-CHECK-BEGIN")
    ws = find_workspace()
    if ws is None:
        print("CONFIG-CHECK: FAIL no-workspace")
        print("CONFIG-CHECK-END")
        return 1

    fetch = run_git(ws, "fetch", "--quiet", PRIVATE_REPO_URL, PINNED_COMMIT)
    if fetch.returncode != 0:
        print(f"CONFIG-CHECK: FAIL fetch exit={fetch.returncode} {fetch.stderr.strip()[:120]}")
        print("CONFIG-CHECK-END")
        return 1

    resolved = run_git(ws, "rev-parse", "FETCH_HEAD")
    if resolved.returncode != 0 or resolved.stdout.strip() != PINNED_COMMIT:
        print(f"CONFIG-CHECK: FAIL pinned-commit-mismatch got={resolved.stdout.strip()[:12]}")
        print("CONFIG-CHECK-END")
        return 1

    show = run_git(ws, "show", f"FETCH_HEAD:{CONFIG_PATH}")
    if show.returncode != 0:
        print(f"CONFIG-CHECK: FAIL file-read exit={show.returncode} {show.stderr.strip()[:120]}")
        print("CONFIG-CHECK-END")
        return 1

    content = show.stdout
    version = ""
    for line in content.splitlines():
        if line.startswith("version:"):
            version = line.split(":", 1)[1].strip()
            break
    digest = hashlib.sha256(content.encode()).hexdigest()
    print(f"config-read: OK repo=nscaledev/alfred commit={PINNED_COMMIT[:12]}")
    print(f"file: {CONFIG_PATH} size={len(content.encode())} sha256={digest} version={version}")
    print("CONFIG-CHECK-END")
    return 0


if __name__ == "__main__":
    sys.exit(main())
