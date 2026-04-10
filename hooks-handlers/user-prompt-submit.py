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

SESSION_KEY = str(os.getpgrp())
SESSION_FILE = BUDDYMON_DIR / "sessions" / f"{SESSION_KEY}.json"


def get_session_state() -> dict:
    try:
        with open(SESSION_FILE) as f:
            return json.load(f)
    except Exception:
        global_active = {}
        try:
            with open(BUDDYMON_DIR / "active.json") as f:
                global_active = json.load(f)
        except Exception:
            pass
        return {
            "buddymon_id": global_active.get("buddymon_id"),
            "challenge": global_active.get("challenge"),
            "session_xp": 0,
        }


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

    # Resolve buddy display name from session-specific state
    buddy_id = get_session_state().get("buddymon_id")
    buddy_display = "your buddy"
    if buddy_id:
        catalog = load_json(CATALOG_FILE)
        b = (catalog.get("buddymon", {}).get(buddy_id)
             or catalog.get("evolutions", {}).get(buddy_id))
        if b:
            buddy_display = b.get("display", buddy_id)
    else:
        catalog = load_json(CATALOG_FILE)

    rarity_stars = {
        "very_common": "★☆☆☆☆", "common": "★★☆☆☆",
        "uncommon": "★★★☆☆", "rare": "★★★★☆", "legendary": "★★★★★",
    }
    strength = enc.get("current_strength", 50)
    is_mascot = enc.get("encounter_type") == "language_mascot"

    if is_mascot:
        mascot_data = catalog.get("language_mascots", {}).get(enc.get("id", ""), {})
        rarity = mascot_data.get("rarity", "common")
        stars = rarity_stars.get(rarity, "★★☆☆☆")
        flavor = mascot_data.get("flavor", "")
        lang = enc.get("language") or mascot_data.get("language", "")
        assignable = mascot_data.get("assignable", False)

        if enc.get("wounded"):
            lines = [
                f"\n🩹 **{enc['display']} is weakened and retreating!**",
                f"   Strength: {strength}%  ·  Your {lang} work has worn it down.",
                "",
                f"   **{buddy_display}** senses the opportunity — act now!",
                "",
                "   `[CATCH]` → `/buddymon catch`  (near-guaranteed at 5% strength)",
                "   `[IGNORE]` → it fades on your next edit",
            ]
        else:
            lines = [
                f"\n🦎 **{enc['display']} appeared!**  [language mascot · {rarity}]",
                f"   Language: {lang}  ·  Strength: {strength}%  ·  Rarity: {stars}",
            ]
            if flavor:
                lines.append(f"   *{flavor}*")
            if assignable:
                lines.append(f"   ✓ Catchable and assignable as buddy — has its own challenges.")
            lines += [
                "",
                f"   **{buddy_display}** is intrigued!",
                "",
                f"   `[CATCH]` Code more in {lang} to weaken it → `/buddymon catch`",
                "   `[FLEE]`  Ignore → it retreats as your affinity fades",
            ]
    else:
        monster = catalog.get("bug_monsters", {}).get(enc.get("id", ""), {})
        rarity = monster.get("rarity", "common")
        stars = rarity_stars.get(rarity, "★★☆☆☆")
        defeatable = enc.get("defeatable", True)
        catchable = enc.get("catchable", True)
        flavor = monster.get("flavor", "")

        if enc.get("wounded"):
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
            catchable_str = "[catchable · catch only]" if not defeatable else f"[{rarity} · {'catchable' if catchable else ''}]"
            lines = [
                f"\n💀 **{enc['display']} appeared!**  {catchable_str}",
                f"   Strength: {strength}%  ·  Rarity: {stars}",
            ]
            if flavor:
                lines.append(f"   *{flavor}*")
            rival_id = enc.get("rival") or monster.get("rival")
            if rival_id:
                rival_entry = (catalog.get("bug_monsters", {}).get(rival_id)
                               or catalog.get("event_encounters", {}).get(rival_id, {}))
                rival_display = rival_entry.get("display", rival_id)
                lines.append(f"   ⚔️  Eternal rival of **{rival_display}** — catch both to settle the debate.")
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
