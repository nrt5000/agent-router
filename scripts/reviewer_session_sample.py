"""Acceptance check: sample one recent workflow ID for correlation in the review output."""
import os, re, subprocess

host = os.environ.get("TEMPORAL_HOST", "unset")
ns = os.environ.get("TEMPORAL_NAMESPACE", "unset")
print(f"ENV-DIAG: host={host} namespace={ns}")
url = f"http://{host}/api/v1/namespaces/{ns}/workflows?pageSize=20"
try:
    r = subprocess.run(
        ["curl", "--noproxy", "*", "-sS", "--connect-timeout", "3", "--max-time", "8", url],
        capture_output=True, text=True, timeout=12,
    )
    print(f"CURL-DIAG: exit={r.returncode} stderr={r.stderr.strip()[:200]}")
    m = re.search(r'"([^"\s]+-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})"', r.stdout, re.I)
    print("SESSION-SAMPLE: " + (m.group(1) if m else "NONE_IN_PAGE"))
except Exception as exc:
    print(f"SESSION-SAMPLE: SCRIPT-ERROR {exc}")
