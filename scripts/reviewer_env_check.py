"""Print the reviewer run identifier for the acceptance check."""
import os
print("ENV-CHECK: " + os.environ.get("ALFRED_WORKFLOW_ID", "unset"))
