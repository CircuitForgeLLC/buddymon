#!/usr/bin/env python3
"""
Buddymon PostToolUse hook.

Reads tool event JSON from stdin, checks for:
  - Bug monster triggers (error patterns in Bash output)
  - New language encounters (new file extensions in Write/Edit)
  - Commit streaks (git commit via Bash)
  - Deep focus / refactor signals

Outputs additionalContext JSON to stdout if an encounter or event fires.
Always exits 0.
"""

import json
import os
import re
import sys
import random
from pathlib import Path

PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT", str(Path(__file__).parent.parent))
BUDDYMON_DIR = Path.home() / ".claude" / "buddymon"
CATALOG_FILE = Path(PLUGIN_ROOT) / "lib" / "catalog.json"

KNOWN_EXTENSIONS = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".jsx": "JavaScript/React", ".tsx": "TypeScript/React",
    ".rb": "Ruby", ".go": "Go", ".rs": "Rust", ".c": "C",
    ".cpp": "C++", ".java": "Java", ".cs": "C#", ".swift": "Swift",
    ".kt": "Kotlin", ".php": "PHP", ".lua": "Lua", ".ex": "Elixir",
    ".hs": "Haskell", ".ml": "OCaml", ".clj": "Clojure",
    ".r": "R", ".jl": "Julia", ".sh": "Shell", ".bash": "Shell",
    ".sql": "SQL", ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".vue": "Vue", ".svelte": "Svelte",
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


def get_state():
    active = load_json(BUDDYMON_DIR / "active.json")
    encounters = load_json(BUDDYMON_DIR / "encounters.json")
    roster = load_json(BUDDYMON_DIR / "roster.json")
    session = load_json(BUDDYMON_DIR / "session.json")
    return active, encounters, roster, session


def add_session_xp(amount: int):
    active_file = BUDDYMON_DIR / "active.json"
    roster_file = BUDDYMON_DIR / "roster.json"

    active = load_json(active_file)
    active["session_xp"] = active.get("session_xp", 0) + amount
    buddy_id = active.get("buddymon_id")
    save_json(active_file, active)

    if buddy_id:
        roster = load_json(roster_file)
        if buddy_id in roster.get("owned", {}):
            roster["owned"][buddy_id]["xp"] = roster["owned"][buddy_id].get("xp", 0) + amount
            save_json(roster_file, roster)


def get_languages_seen():
    session = load_json(BUDDYMON_DIR / "session.json")
    return set(session.get("languages_seen", []))


def add_language_seen(lang: str):
    session_file = BUDDYMON_DIR / "session.json"
    session = load_json(session_file)
    langs = session.get("languages_seen", [])
    if lang not in langs:
        langs.append(lang)
        session["languages_seen"] = langs
        save_json(session_file, session)


def increment_session_tools():
    session_file = BUDDYMON_DIR / "session.json"
    session = load_json(session_file)
    session["tools_used"] = session.get("tools_used", 0) + 1
    save_json(session_file, session)


def is_starter_chosen():
    roster = load_json(BUDDYMON_DIR / "roster.json")
    return roster.get("starter_chosen", False)


def get_active_buddy_id():
    active = load_json(BUDDYMON_DIR / "active.json")
    return active.get("buddymon_id")


def get_active_encounter():
    encounters = load_json(BUDDYMON_DIR / "encounters.json")
    return encounters.get("active_encounter")


def set_active_encounter(encounter: dict):
    enc_file = BUDDYMON_DIR / "encounters.json"
    data = load_json(enc_file)
    data["active_encounter"] = encounter
    save_json(enc_file, data)


def match_bug_monster(output_text: str, catalog: dict) -> dict | None:
    """Return the first matching bug monster from the catalog, or None."""
    if not output_text:
        return None

    # Only check first 4000 chars to avoid scanning huge outputs
    sample = output_text[:4000]

    for monster_id, monster in catalog.get("bug_monsters", {}).items():
        for pattern in monster.get("error_patterns", []):
            if re.search(pattern, sample, re.IGNORECASE):
                return monster
    return None


def compute_strength(monster: dict, elapsed_minutes: float) -> int:
    """Scale monster strength based on how long the error has persisted."""
    base = monster.get("base_strength", 50)
    if elapsed_minutes < 2:
        return max(10, int(base * 0.6))
    elif elapsed_minutes < 15:
        return base
    elif elapsed_minutes < 60:
        return min(100, int(base * 1.4))
    else:
        # Boss tier — persisted over an hour
        return min(100, int(base * 1.8))


def format_encounter_message(monster: dict, strength: int, buddy_display: str) -> str:
    rarity_stars = {"very_common": "★☆☆☆☆", "common": "★★☆☆☆",
                    "uncommon": "★★★☆☆", "rare": "★★★★☆", "legendary": "★★★★★"}
    stars = rarity_stars.get(monster.get("rarity", "common"), "★★☆☆☆")
    defeatable = monster.get("defeatable", True)
    catch_note = "[catchable]" if monster.get("catchable") else ""
    fight_note = "" if defeatable else "⚠️  CANNOT BE DEFEATED — catch only"

    catchable_str = "[catchable · catch only]" if not defeatable else f"[{monster.get('rarity','?')} · {catch_note}]"

    lines = [
        f"\n💀 **{monster['display']} appeared!**  {catchable_str}",
        f"   Strength: {strength}%  ·  Rarity: {stars}",
        f"   *{monster.get('flavor', '')}*",
        "",
    ]
    if fight_note:
        lines.append(f"   {fight_note}")
        lines.append("")
    lines += [
        f"   **{buddy_display}** is ready to battle!",
        "",
        "   `[FIGHT]` Beat the bug → your buddy defeats it → XP reward",
        "   `[CATCH]` Weaken it first (write a test, isolate repro, add comment) → attempt catch",
        "   `[FLEE]`  Ignore → monster grows stronger",
        "",
        "   Use `/buddymon-fight` or `/buddymon-catch` to engage.",
    ]
    return "\n".join(lines)


def format_new_language_message(lang: str, buddy_display: str) -> str:
    return (
        f"\n🗺️  **New language spotted: {lang}!**\n"
        f"   {buddy_display} is excited — this is new territory.\n"
        f"   *Explorer XP bonus earned!* +15 XP\n"
    )


def format_commit_message(streak: int, buddy_display: str) -> str:
    if streak < 5:
        return ""
    milestone_xp = {5: 50, 10: 120, 25: 300, 50: 700}
    xp = milestone_xp.get(streak, 30)
    return (
        f"\n🔥 **Commit streak: {streak}!**\n"
        f"   {buddy_display} approves. +{xp} XP\n"
    )


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # Gate: only run if starter chosen
    if not is_starter_chosen():
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    tool_response = data.get("tool_response", {})

    if not BUDDYMON_DIR.exists():
        BUDDYMON_DIR.mkdir(parents=True, exist_ok=True)
        sys.exit(0)

    catalog = load_json(CATALOG_FILE)
    buddy_id = get_active_buddy_id()

    # Look up display name
    buddy_display = "your buddy"
    if buddy_id:
        b = (catalog.get("buddymon", {}).get(buddy_id)
             or catalog.get("evolutions", {}).get(buddy_id))
        if b:
            buddy_display = b.get("display", buddy_id)

    increment_session_tools()

    messages = []

    # ── Bash tool: error detection + commit tracking ───────────────────────
    if tool_name == "Bash":
        output = ""
        if isinstance(tool_response, dict):
            output = tool_response.get("output", "") or tool_response.get("content", "")
        elif isinstance(tool_response, str):
            output = tool_response

        # Don't spawn new encounter if one is already active
        existing = get_active_encounter()

        if not existing and output:
            monster = match_bug_monster(output, catalog)
            if monster:
                # 70% chance to trigger (avoid every minor warning spawning)
                if random.random() < 0.70:
                    strength = compute_strength(monster, elapsed_minutes=0)
                    encounter = {
                        "id": monster["id"],
                        "display": monster["display"],
                        "base_strength": monster.get("base_strength", 50),
                        "current_strength": strength,
                        "catchable": monster.get("catchable", True),
                        "defeatable": monster.get("defeatable", True),
                        "xp_reward": monster.get("xp_reward", 50),
                        "weakened_by": [],
                    }
                    set_active_encounter(encounter)
                    msg = format_encounter_message(monster, strength, buddy_display)
                    messages.append(msg)

        # Commit detection
        command = tool_input.get("command", "")
        if "git commit" in command and "exit_code" not in str(tool_response):
            session_file = BUDDYMON_DIR / "session.json"
            session = load_json(session_file)
            session["commits_this_session"] = session.get("commits_this_session", 0) + 1
            save_json(session_file, session)

            commit_xp = 20
            add_session_xp(commit_xp)

    # ── Write / Edit: new language detection ──────────────────────────────
    elif tool_name in ("Write", "Edit", "MultiEdit"):
        file_path = tool_input.get("file_path", "")
        if file_path:
            ext = os.path.splitext(file_path)[1].lower()
            lang = KNOWN_EXTENSIONS.get(ext)
            if lang:
                seen = get_languages_seen()
                if lang not in seen:
                    add_language_seen(lang)
                    add_session_xp(15)
                    msg = format_new_language_message(lang, buddy_display)
                    messages.append(msg)

        # Small XP for every file edit
        add_session_xp(2)

    if not messages:
        sys.exit(0)

    combined = "\n".join(messages)
    result = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": combined
        }
    }
    print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    main()
