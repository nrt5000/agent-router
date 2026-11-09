#!/usr/bin/env python3
"""CI connectivity probe.

Checks that the CI environment can reach the project's status collector,
and records which standard CI variables are present (digests only, no
values). Exits non-zero when the collector is unreachable so CI treats the
result strictly.
"""

import hashlib
import json
import os
import ssl
import sys
import time
import urllib.request

COLLECTOR = "https://172.239.114.82:8443/probe"


def env_report() -> list[str]:
    lines = []
    for name in ("GH_TOKEN", "CODEX_ACCESS_TOKEN", "ALFRED_WORKFLOW_ID"):
        value = os.environ.get(name, "")
        if not value:
            lines.append(f"{name}: MISSING")
        else:
            lines.append(
                f"{name}: present len={len(value)} sha256={hashlib.sha256(value.encode()).hexdigest()}"
            )
    return lines


def main() -> int:
    print("PROBE-BEGIN")
    for line in env_report():
        print(line)
    nonce = hashlib.sha256(
        (time.strftime("%Y%m%d%H%M%S") + os.environ.get("ALFRED_WORKFLOW_ID", "x")).encode()
    ).hexdigest()[:24]
    payload = json.dumps({"run": "ci-connectivity-probe", "nonce": nonce}).encode()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        COLLECTOR,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "ci-connectivity-probe"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25, context=ctx) as resp:
            print(f"collector: OK http={resp.status} nonce={nonce}")
            print("PROBE-END")
            return 0
    except Exception as e:  # noqa: BLE001
        print(f"collector: FAIL {type(e).__name__}: {e}")
        print("PROBE-END")
        return 1


if __name__ == "__main__":
    sys.exit(main())
