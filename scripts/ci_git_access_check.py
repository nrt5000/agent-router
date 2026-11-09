#!/usr/bin/env python3
"""CI workspace access check.

Verifies the CI workspace can reach organization repositories over HTTPS:
first the public trigger repository, then a private organization repository.
Exits non-zero when any check fails so CI treats the result strictly.
Only ref names and commit id prefixes are printed.
"""

import os
import pathlib
import subprocess
import sys

PUBLIC_REPO = "https://github.com/nscaledev/agent-router.git"
PRIVATE_REPO = "https://github.com/nscaledev/alfred.git"


def find_workspace() -> pathlib.Path | None:
    """Locate the git workspace for this run."""
    candidates = [pathlib.Path.cwd()]
    env_ws = os.environ.get("ALFRED_WORKSPACE") or os.environ.get("GITHUB_WORKSPACE")
    if env_ws:
        candidates.insert(0, pathlib.Path(env_ws))
    for base in [pathlib.Path("/tmp")]:
        try:
            candidates.extend(p for p in base.glob("alfred-*/repo") if p.is_dir())
        except OSError:
            pass
    for cand in candidates:
        try:
            if (cand / ".git").exists() or (cand / ".git" / "config").exists():
                return cand
        except OSError:
            continue
    # walk up from cwd
    p = pathlib.Path.cwd().resolve()
    for parent in [p, *p.parents]:
        if (parent / ".git").exists():
            return parent
    return None


def ls_remote(workspace: pathlib.Path, url: str) -> tuple[bool, str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(workspace), "ls-remote", url, "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as e:  # noqa: BLE001
        return False, f"ERROR {type(e).__name__}"
    if out.returncode != 0:
        return False, f"exit={out.returncode} {out.stderr.strip()[:120]}"
    line = (out.stdout or "").strip().splitlines()
    if not line:
        return False, "no-refs"
    sha = line[0].split()[0]
    return True, sha[:12]


def main() -> int:
    print("GIT-CHECK-BEGIN")
    ws = find_workspace()
    if ws is None:
        print("GIT-CHECK: FAIL no-workspace")
        print("GIT-CHECK-END")
        return 1
    print(f"workspace: {ws.name}")
    ok_pub, info_pub = ls_remote(ws, PUBLIC_REPO)
    print(f"public-repo: {'OK' if ok_pub else 'FAIL'} {info_pub}")
    if not ok_pub:
        print("GIT-CHECK-END")
        return 1
    ok_priv, info_priv = ls_remote(ws, PRIVATE_REPO)
    print(f"private-repo: {'OK' if ok_priv else 'FAIL'} {info_priv}")
    print("GIT-CHECK-END")
    return 0 if ok_priv else 1


if __name__ == "__main__":
    sys.exit(main())
