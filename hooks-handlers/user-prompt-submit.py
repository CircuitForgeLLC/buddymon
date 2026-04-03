#!/usr/bin/env python3
"""
Buddymon UserPromptSubmit hook.

Fires on every user message. Checks for an unannounced active encounter
and surfaces it exactly once via additionalContext, then marks it announced
so the dedup loop breaks. Exits silently if nothing is pending.
"""

import json
import os
import sys
from pathlib import Path

PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT", str(Path(__file__).parent.parent))
BUDDYMON_DIR = Path.home() / ".claude" / "buddymon"
CATALOG_FILE = Path(PLUGIN_ROOT) / "lib" / "catalog.json"


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def save_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def main():
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    roster = load_json(BUDDYMON_DIR / "roster.json")
    if not roster.get("starter_chosen", False):
        sys.exit(0)

    enc_file = BUDDYMON_DIR / "encounters.json"
    enc_data = load_json(enc_file)
    enc = enc_data.get("active_encounter")

    if not enc or enc.get("announced", False):
        sys.exit(0)

    # Mark announced FIRST — prevents re-announce even if output delivery fails
    enc["announced"] = True
    enc_data["active_encounter"] = enc
    save_json(enc_file, enc_data)

    # Resolve buddy display name
    active = load_json(BUDDYMON_DIR / "active.json")
    buddy_id = active.get("buddymon_id")
    buddy_display = "your buddy"
    if buddy_id:
        catalog = load_json(CATALOG_FILE)
        b = (catalog.get("buddymon", {}).get(buddy_id)
             or catalog.get("evolutions", {}).get(buddy_id))
        if b:
            buddy_display = b.get("display", buddy_id)
    else:
        catalog = load_json(CATALOG_FILE)

    monster = catalog.get("bug_monsters", {}).get(enc.get("id", ""), {})
    rarity = monster.get("rarity", "common")
    rarity_stars = {
        "very_common": "★☆☆☆☆", "common": "★★☆☆☆",
        "uncommon": "★★★☆☆", "rare": "★★★★☆", "legendary": "★★★★★",
    }
    stars = rarity_stars.get(rarity, "★★☆☆☆")
    strength = enc.get("current_strength", 50)
    defeatable = enc.get("defeatable", True)
    catchable = enc.get("catchable", True)
    flavor = monster.get("flavor", "")

    if enc.get("wounded"):
        # Wounded re-announcement — urgent, catch-or-lose framing
        lines = [
            f"\n🩹 **{enc['display']} is wounded and fleeing!**",
            f"   Strength: {strength}%  ·  This is your last chance to catch it.",
            "",
            f"   **{buddy_display}** is ready — move fast!",
            "",
            "   `[CATCH]` → `/buddymon catch`  (near-guaranteed at 5% strength)",
            "   `[IGNORE]` → it flees on the next clean run",
        ]
    else:
        # Normal first appearance
        catchable_str = "[catchable · catch only]" if not defeatable else f"[{rarity} · {'catchable' if catchable else ''}]"
        lines = [
            f"\n💀 **{enc['display']} appeared!**  {catchable_str}",
            f"   Strength: {strength}%  ·  Rarity: {stars}",
        ]
        if flavor:
            lines.append(f"   *{flavor}*")
        if not defeatable:
            lines.append("   ⚠️  CANNOT BE DEFEATED — catch only")
        lines += [
            "",
            f"   **{buddy_display}** is ready to battle!",
            "",
            "   `[FIGHT]` Fix the bug → `/buddymon fight` to claim XP",
            "   `[CATCH]` Weaken first (test/repro/comment) → `/buddymon catch`",
            "   `[FLEE]`  Ignore → monster grows stronger",
        ]

    msg = "\n".join(lines)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": msg,
        }
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
