"""
Generate reports/platform_test_summary.json from a REAL pytest run.

This script never fabricates results — it executes the actual test
suite via pytest's own JSON-ish terminal summary and records what
pytest reported. If pytest cannot run, it writes an explicit error
status rather than inventing passing numbers.

Usage (from the repository root):

    python python/generate_test_summary.py
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(REPO_ROOT, "reports", "platform_test_summary.json")


def parse_pytest_output(output):
    """Parse pytest's terminal summary line, e.g.
    '370 passed, 1 warning in 28.09s' or '5 failed, 10 passed in 2s'.
    """
    counts = {"passed": 0, "failed": 0, "skipped": 0, "warnings": 0, "errors": 0}
    for key in counts:
        singular = key.rstrip("s") if key.endswith("s") else key
        pattern = rf"(\d+)\s+{singular}s?\b"
        matches = re.findall(pattern, output)
        if matches:
            counts[key] = int(matches[-1])
    return counts


def main():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests", "-q"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    output = result.stdout + result.stderr
    counts = parse_pytest_output(output)

    total = counts["passed"] + counts["failed"] + counts["skipped"] + counts["errors"]
    if total == 0:
        status = "ERROR"
    elif counts["failed"] or counts["errors"]:
        status = "FAILING"
    else:
        status = "PASSING"

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_tests": total,
        "passed": counts["passed"],
        "failed": counts["failed"],
        "skipped": counts["skipped"],
        "errors": counts["errors"],
        "warnings": counts["warnings"],
        "status": status,
        "exit_code": result.returncode,
        "command": "python -m pytest backend/tests -q",
        "note": "Generated from an actual pytest run; values are not hand-edited.",
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as fh:
        json.dump(summary, fh, indent=2)

    print(json.dumps(summary, indent=2))
    return 0 if status == "PASSING" else 1


if __name__ == "__main__":
    sys.exit(main())
