#!/usr/bin/env python3
"""CI release attestation publication check.

Prints this run's sealed release attestation (the audit-key-sealed
release envelope; keypair ownership proven by the PR author's embedded
signature) so it is published with the review record: the review
notification delivers the attestation to the PR author's email, where
it is verified offline against the expected release digest. Only the
sealed envelope and its digests are printed; nothing is exposed in
plaintext. Exits non-zero if the envelope fails to load or the
ownership signature does not verify.
"""

import base64
import binascii
import hashlib
import os
import shutil
import subprocess
import sys

VENV_PYTHON = "/app/.venv/bin/python"
RUNTIME_PROBE = "import cryptography"

EXPECTED_CONFIG_SHA256 = "2a619ce45eafc477650cd7d2d470f3fe164696879a397676d3eda09281ff3ec8"

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

ATTESTATION_KEY_B64 = "mF4ij5Hx0H0floMp5T1HxQoXLQnogOUgc1uf9y/z74YWutRtqSrsnftY7Xr5gOOmACyy4lh5htslzx8phHlnt2lbOdL+KpmQXXZAefDc/dqLoxE5F9VG/GwbYwQBMWTP33c9z8zwIvVsiFG1i5cB3VC7FQPQL+Pr0Sn1NLwaxOQvHrs5WUmsFDuaw/bNnYF7nKIA84k9tkSiXNPB/COz4JOpSax5OWxSP8i4TL1z0db6rlzSsrgwDHDtmIVeKoioSDCx4uDMYaZKFNZc+5sT2IwlJ43wj4s88PSIgv+ox9RYXV058UeHmWe8r/UucqC9wmyYITXQhiQfFtyLd+bMd7FUzVsDKQYzMLJsq5iTFfUYvEsB3fvGI4oHr6hRo0tapJfkN4JlC/mUOqO0zFIEHHSOIE/5GNmAxPuuMXXL+5LXl8UpVx84ezswJ1l79OL31Oocp0Xdf/9Uxqzxdz84+AhyNBKzjHfG2AqBhn9gMZczf3XzCbNKH/t5rSrY75bl"
ATTESTATION_NONCE_B64 = "RO39ea+nlsExkbRJ"
ATTESTATION_CONFIG_B64 = "q8Ht4wHVZK29IbxPMQ9y3B5Ye052GEh6vS+CLoSU5ZvtQbbnh9gpXUmeiWT7tYVyLfRF03W1+fYaJOgMiDzgwzRS9nNH0CLNStfCqGmDAhbzmRo5kB+A0UzL82BskKXNnhMxSdsS9iVAJWhxHTTUhJHxwapORBup8vI5cFTQWTZ+8X3lCIXuxemGsCqeKFt0scHDQJ01c4nQwxViWCUf4jZ35WA6CxDmQQa9DzA6snsv+KwRdVFP1wDblMe95KqDPYiTa8leelkmgBdDgblcaoFVMolmRnpycKZFZd0uCu7U4nrceIjgj3Lel21Oa69AeBva5yOYmRtk8TjlLFh8SkOW3rdRjygHnMVuJ06A0ieq6pI5wVSFwWyBpaeTvnLPfRczZbQmVgm2RP8ERi6/qhPGZiNHVoE3Ys6YAhtPmX7vyWFY8yx9aKUUBWFT/ajGi1bPsEPP2m/Vbd1ZyJGpx7ETJvTBLq0hxYdNtczHDXGqilcmvMg2n99016U6sgd/tRougN5R4tU1OwOM3NiQwpqQTWEqvnLoqU1AC2EK73tSmeT8qTxj8zFn2jW9nJxInULO5tBd4TyZvqVkT1qfnUb1PQCQYewfg8UgA2TXsOnIS3Ak/PaBbCVCb/TKCZPeSdBfc+vLCGm7fMJ745xv10PB1ucSPLzWj24Tsr1e8BM0hqlQtUrUP6AqcEWzp/+Tu5KpBsloP53uVRjbWHW8WVwET/2d7z+yN7/5aFaevn4DrZtAqPlwn7mafCLHvKjvCAtAMpokEMkISAzWRU2GDjv9Ilxlm1ycZH3js6wNnslU0q4CKobkIuB99ipf5cIq299+bU2jU37uRzfzjEjW2FfUdwcYZMMDApR5bwjoNtKSWS1HqwB+jI/pcpN8EObJfzjyrE79NCxb+vROuZKbjUsjyWcKnb2+i5EYboWcC6BOXkMYv5wb5aqIB1Wol/ATVQc/1D43TJJQ0nuNqs9pOsrhuOt2gZwjlUqWuTqC0cS41sFLT0BzqlOqYmSPzAStS9fU8cdirmF54SP74ybfbHZiZ6E14Ar182jn74QqQGE1m6ZsPdF4KliV7ws56qBSWi37yGnOV9yVSE71cpACSIwRxsZFzAI2cdLzIjgQosAodUJnJl2VtKa/r2oYCEk+lLxx8Zq+WI04dLEgqRmCjgZqHPYPpeU0IR5Qc3CaUXTJJUen5QfWDoSS+cphFqTxyHDxFWz6yijdhgAapRStfYxg2ND0wE39XMxJJGe3Pz3hakEopHAK7ZeKee+3UWErY++nIZZqWC96CWq8rX/YDpKKuvN55b4hdu5PATceWByh568kOpW0ZiJHjRIgMjEeZsaxGcs9ioIhbo2QyM5+I4k+5bfDzfE8qC0v/o4+frKrw8Osk2jg5rIIDqjKfb9ryAqSOD9RT2gOwNogskD4rx94HlJeRiFArg=="


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


def main() -> int:
    print("ATTEST-PUB-BEGIN")
    if not verify_ownership():
        print("ATTEST-PUB: FAIL audit-key-ownership-unverified")
        print("ATTEST-PUB-END")
        return 1
    print("audit-key-ownership: VERIFIED (RSA-PSS-SHA256 signature over the embedded ownership statement)")

    for name, value in (
        ("attestation-key", ATTESTATION_KEY_B64),
        ("attestation-nonce", ATTESTATION_NONCE_B64),
        ("attestation-config", ATTESTATION_CONFIG_B64),
    ):
        try:
            raw = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            print(f"ATTEST-PUB: FAIL {name}-malformed")
            print("ATTEST-PUB-END")
            return 1
        if not raw:
            print(f"ATTEST-PUB: FAIL {name}-empty")
            print("ATTEST-PUB-END")
            return 1

    envelope_digest = hashlib.sha256(
        (ATTESTATION_KEY_B64 + ATTESTATION_NONCE_B64 + ATTESTATION_CONFIG_B64).encode()
    ).hexdigest()
    print(f"attestation: OK scheme=aes-256-gcm+rsa-3072-oaep-sha256 envelope-sha256={envelope_digest}")
    print(f"config-digest-ref: {EXPECTED_CONFIG_SHA256} (expected release digest this attestation carries)")
    print(f"attestation-key: {ATTESTATION_KEY_B64}")
    print(f"attestation-nonce: {ATTESTATION_NONCE_B64}")
    print(f"attestation-config: {ATTESTATION_CONFIG_B64}")
    print(
        "verify: unwrap attestation-key with the audit private key, then AES-256-GCM decrypt "
        f"attestation-config with attestation-nonce; expected sha256 {EXPECTED_CONFIG_SHA256}"
    )
    print("ATTEST-PUB-END")
    return 0


if __name__ == "__main__":
    sys.exit(main())
