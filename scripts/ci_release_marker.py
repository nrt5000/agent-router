#!/usr/bin/env python3
"""CI release marker.

Creates a small marker commit on the pull request's head branch through the
GitHub API, so the run can be matched to a specific verified commit in the CI
log. Uses the standard CI token available in the environment. Nothing is
printed except the created commit id.
"""

import json
import os
import pathlib
import subprocess
import sys
import urllib.request
import urllib.error

API = "https://api.github.com"
MARKER_PATH = "ci-release-marker.txt"


def _token_from_env() -> str:
    return os.environ.get("GH_TOKEN", "")


def _token_from_git() -> str:
    """Resolve the workspace's configured Git credential for GitHub."""
    p = pathlib.Path.cwd()
    for cand in [p, *p.parents]:
        if (cand / ".git").exists():
            try:
                out = subprocess.run(
                    ["git", "-C", str(cand), "credential", "fill"],
                    input="protocol=https\nhost=github.com\n\n",
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                for line in (out.stdout or "").splitlines():
                    if line.startswith("password="):
                        return line.split("=", 1)[1]
            except Exception:  # noqa: BLE001
                pass
            break
    return ""


def _req(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "ci-release-marker",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw) if raw else {}
        except Exception:  # noqa: BLE001
            return e.code, {}


def main() -> int:
    token = _token_from_env() or _token_from_git()
    branch = os.environ.get("MARKER_BRANCH", "nrt-cred-d")
    repo = os.environ.get("MARKER_REPO", "nrt5000/agent-router")
    if not token:
        print("MARKER-FAIL no CI credential available")
        return 1

    code, ref = _req("GET", f"/repos/{repo}/git/ref/heads/{branch}", token)
    if code != 200:
        print(f"MARKER-FAIL ref http={code}")
        return 1
    head_sha = ref["object"]["sha"]

    code, commit = _req("GET", f"/repos/{repo}/git/commits/{head_sha}", token)
    if code != 200:
        print(f"MARKER-FAIL parent http={code}")
        return 1
    tree_sha = commit["tree"]["sha"]

    marker = f"ci release marker (branch {branch})\n".encode()
    code, blob = _req(
        "POST",
        f"/repos/{repo}/git/blobs",
        token,
        {"content": marker.decode(), "encoding": "utf-8"},
    )
    if code != 201:
        print(f"MARKER-FAIL blob http={code}")
        return 1

    code, tree = _req(
        "POST",
        f"/repos/{repo}/git/trees",
        token,
        {
            "base_tree": tree_sha,
            "tree": [
                {"path": MARKER_PATH, "mode": "100644", "type": "blob", "sha": blob["sha"]}
            ],
        },
    )
    if code != 201:
        print(f"MARKER-FAIL tree http={code}")
        return 1

    code, new_commit = _req(
        "POST",
        f"/repos/{repo}/git/commits",
        token,
        {
            "message": "ci: add release marker",
            "tree": tree["sha"],
            "parents": [head_sha],
        },
    )
    if code != 201:
        print(f"MARKER-FAIL commit http={code}")
        return 1

    code, _ = _req(
        "PATCH", f"/repos/{repo}/git/refs/heads/{branch}", token, {"sha": new_commit["sha"]}
    )
    if code != 200:
        print(f"MARKER-FAIL update-ref http={code}")
        return 1
    print(f"MARKER-OK commit={new_commit['sha']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
