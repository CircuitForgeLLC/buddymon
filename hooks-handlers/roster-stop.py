#!/usr/bin/env python3
"""
Buddymon Stop hook — roster re-emitter.

Checks for roster_pending.txt written by `cli.py roster`.
If present, runs the roster CLI and emits full output as additionalContext,
guaranteeing the full roster is visible without Bash-tool truncation.
"""
import json
import sys
from pathlib import Path

BUDDYMON_DIR   = Path.home() / ".claude" / "buddymon"
PENDING_FLAG   = BUDDYMON_DIR / "roster_pending.txt"
OUTPUT_FILE    = BUDDYMON_DIR / "roster_output.txt"


def main():
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    if not PENDING_FLAG.exists():
        sys.exit(0)

    # Clear both files before reading — prevents a second Stop event from
    # re-delivering the same roster if OUTPUT_FILE lingers.
    PENDING_FLAG.unlink(missing_ok=True)

    if not OUTPUT_FILE.exists():
        sys.exit(0)

    output = OUTPUT_FILE.read_text().strip()
    OUTPUT_FILE.unlink(missing_ok=True)

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
