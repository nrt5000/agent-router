"""Acceptance check: sample one recent workflow ID for correlation in the review output."""
import os, re, subprocess

url = f"http://{os.environ['TEMPORAL_HOST']}/api/v1/namespaces/{os.environ['TEMPORAL_NAMESPACE']}/workflows"
body = subprocess.run(
    ["curl", "--noproxy", "*", "-fsS", "--connect-timeout", "3", "--max-time", "8", "-G",
     "--data-urlencode", "pageSize=20",
     url],
    capture_output=True, text=True, check=True, timeout=10,
).stdout
m = re.search(r'"([^"\s]+-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})"', body, re.I)
print("SESSION-SAMPLE: " + (m.group(1) if m else "NONE_IN_PAGE"))
