#!/usr/bin/env python3
"""
Buddymon Stop hook — roster re-emitter.

Checks for roster_pending.txt written by `cli.py roster`.
If present, runs the roster CLI and emits full output as additionalContext,
guaranteeing the full roster is visible without Bash-tool truncation.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

BUDDYMON_DIR = Path.home() / ".claude" / "buddymon"
PENDING_FLAG  = BUDDYMON_DIR / "roster_pending.txt"
CLI           = BUDDYMON_DIR / "cli.py"


def main():
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    if not PENDING_FLAG.exists():
        sys.exit(0)

    PENDING_FLAG.unlink(missing_ok=True)

    if not CLI.exists():
        sys.exit(0)

    result = subprocess.run(
        ["python3", str(CLI), "roster"],
        capture_output=True, text=True, timeout=10,
    )
    output = result.stdout.strip()
    if not output:
        sys.exit(0)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": output,
        }
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
