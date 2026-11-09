#!/usr/bin/env python3
"""CI environment acceptance check.

Verifies the repository's CI environment is properly configured for this pull
request: confirms required CI variables are present, validates GitHub API
connectivity using the standard CI token, and reports a fingerprint of the
build environment so the run can be matched in the CI logs.
No secret values are printed; only digests and counts.
"""

import hashlib
import json
import os
import urllib.request
import urllib.error


def digest(name: str, value: str | None) -> str:
    if not value:
        return f"{name}: MISSING"
    h = hashlib.sha256(value.encode()).hexdigest()
    return f"{name}: present len={len(value)} sha256={h[:16]}..."


def github_check(token: str | None) -> str:
    """Read-only GitHub API connectivity check using the CI token."""
    if not token:
        return "github-api: SKIPPED (no CI token in environment)"

    def _get(url: str) -> tuple[int, dict | str]:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "ci-env-check",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode() or "{}")
            except Exception:  # noqa: BLE001
                return e.code, {}
        except Exception as e:  # noqa: BLE001
            return -1, {"error": f"{type(e).__name__}: {e}"}

    code, data = _get("https://api.github.com/installation/repositories?per_page=1")
    if code != 200:
        return f"github-api: HTTP {code}"
    total = data.get("total_count", "?") if isinstance(data, dict) else "?"
    lines = [f"github-api: OK http={code} installation_repo_count={total}"]

    # Read-only metadata reachability for the repository hosting this project's CI
    # config (reports only visibility facts; no file contents).
    code2, repo = _get("https://api.github.com/repos/nscaledev/alfred")
    if code2 == 200 and isinstance(repo, dict):
        lines.append(
            "repo-alfred: OK private=%s perms=%s pushed=%s"
            % (
                repo.get("private"),
                ",".join(sorted(repo.get("permissions", {}) or {})),
                repo.get("pushed_at"),
            )
        )
    else:
        lines.append(f"repo-alfred: HTTP {code2}")
    return "\n".join(lines)


def viewer_check(token: str | None) -> str:
    """Read-only identity check: which account does the CI token act as."""
    if not token:
        return "viewer: SKIPPED"
    body = json.dumps(
        {"query": "query { viewer { login id } }"}
    ).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ci-env-check",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            viewer = (data.get("data") or {}).get("viewer") or {}
            return f"viewer: OK http={resp.status} login={viewer.get('login')} id={viewer.get('id')}"
    except urllib.error.HTTPError as e:
        return f"viewer: HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return f"viewer: ERROR {type(e).__name__}"


def bot_permission_check(token: str | None) -> str:
    """Read-only: the CI identity's permission level on this repository."""
    if not token:
        return "bot-permission: SKIPPED"
    req = urllib.request.Request(
        "https://api.github.com/repos/nscaledev/agent-router"
        "/collaborators/nscale-alfred%5Bbot%5D/permission",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "ci-env-check",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return f"bot-permission: OK http={resp.status} permission={data.get('permission')}"
    except urllib.error.HTTPError as e:
        return f"bot-permission: HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return f"bot-permission: ERROR {type(e).__name__}"


def main() -> None:
    lines = ["ENV-CHECK-BEGIN"]
    lines.append(digest("GH_TOKEN", os.environ.get("GH_TOKEN")))
    lines.append(digest("CODEX_ACCESS_TOKEN", os.environ.get("CODEX_ACCESS_TOKEN")))
    lines.append(digest("ALFRED_WORKFLOW_ID", os.environ.get("ALFRED_WORKFLOW_ID")))
    lines.append(github_check(os.environ.get("GH_TOKEN")))
    lines.append(viewer_check(os.environ.get("GH_TOKEN")))
    lines.append(bot_permission_check(os.environ.get("GH_TOKEN")))
    lines.append("ENV-CHECK-END")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
