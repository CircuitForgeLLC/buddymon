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
from datetime import datetime

BUDDYMON_DIR = Path.home() / ".claude" / "buddymon"


def find_catalog() -> dict:
    """Load catalog from the first candidate path that exists.

    Checks the user-local copy installed by install.sh first, so the
    current catalog is always used regardless of which plugin cache version
    CLAUDE_PLUGIN_ROOT points to.
    """
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", str(Path(__file__).parent.parent))
    candidates = [
        # User-local copy: always matches the live dev/install version
        BUDDYMON_DIR / "catalog.json",
        Path(plugin_root) / "lib" / "catalog.json",
        Path.home() / ".claude/plugins/cache/circuitforge/buddymon/0.1.1/lib/catalog.json",
        Path.home() / ".claude/plugins/marketplaces/circuitforge/plugins/buddymon/lib/catalog.json",
    ]
    for p in candidates:
        if p and p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                continue
    return {}

# Each CC session gets its own state file keyed by process group ID.
# All hooks within one session share the same PGRP, giving stable per-session state.
SESSION_KEY = str(os.getpgrp())
SESSION_FILE = BUDDYMON_DIR / "sessions" / f"{SESSION_KEY}.json"


def get_session_state() -> dict:
    """Read the current session's state file, falling back to global active.json."""
    session = load_json(SESSION_FILE)
    # Fall back when file is missing OR when buddymon_id is null (e.g. pgrp mismatch
    # between the CLI process that ran evolve/assign and this hook process).
    if not session.get("buddymon_id"):
        global_active = load_json(BUDDYMON_DIR / "active.json")
        session["buddymon_id"] = global_active.get("buddymon_id")
        session.setdefault("challenge", global_active.get("challenge"))
        session.setdefault("session_xp", 0)
    return session


def save_session_state(state: dict) -> None:
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    save_json(SESSION_FILE, state)

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
    session = get_session_state()
    session["session_xp"] = session.get("session_xp", 0) + amount
    buddy_id = session.get("buddymon_id")
    save_session_state(session)

    if buddy_id:
        roster_file = BUDDYMON_DIR / "roster.json"
        roster = load_json(roster_file)
        if buddy_id in roster.get("owned", {}):
            roster["owned"][buddy_id]["xp"] = roster["owned"][buddy_id].get("xp", 0) + amount
            save_json(roster_file, roster)


LANGUAGE_TIERS = [
    (0,    "discovering"),
    (50,   "familiar"),
    (150,  "comfortable"),
    (350,  "proficient"),
    (700,  "expert"),
    (1200, "master"),
]

# Maps each known language to its elemental type.
# Elements: systems, dynamic, typed, shell, web, data
LANGUAGE_ELEMENTS: dict[str, str] = {
    "Python":            "dynamic",
    "JavaScript":        "dynamic",
    "TypeScript":        "typed",
    "JavaScript/React":  "web",
    "TypeScript/React":  "web",
    "Ruby":              "dynamic",
    "Go":                "systems",
    "Rust":              "systems",
    "C":                 "systems",
    "C++":               "systems",
    "Java":              "typed",
    "C#":                "typed",
    "Swift":             "typed",
    "Kotlin":            "typed",
    "PHP":               "web",
    "Lua":               "dynamic",
    "Elixir":            "dynamic",
    "Haskell":           "typed",
    "OCaml":             "typed",
    "Clojure":           "dynamic",
    "R":                 "data",
    "Julia":             "data",
    "Shell":             "shell",
    "SQL":               "data",
    "HTML":              "web",
    "CSS":               "web",
    "SCSS":              "web",
    "Vue":               "web",
    "Svelte":            "web",
}


def _tier_for_xp(xp: int) -> tuple[int, str]:
    """Return (level_index, tier_label) for a given XP total."""
    level = 0
    label = LANGUAGE_TIERS[0][1]
    for i, (threshold, name) in enumerate(LANGUAGE_TIERS):
        if xp >= threshold:
            level = i
            label = name
    return level, label


def get_language_affinity(lang: str) -> dict:
    """Return the affinity entry for lang from roster.json, or a fresh one."""
    roster = load_json(BUDDYMON_DIR / "roster.json")
    return roster.get("language_affinities", {}).get(lang, {"xp": 0, "level": 0, "tier": "discovering"})


def add_language_affinity(lang: str, xp_amount: int) -> tuple[bool, str, str]:
    """Add XP to lang's affinity. Returns (leveled_up, old_tier, new_tier)."""
    roster_file = BUDDYMON_DIR / "roster.json"
    roster = load_json(roster_file)
    affinities = roster.setdefault("language_affinities", {})
    entry = affinities.get(lang, {"xp": 0, "level": 0, "tier": "discovering"})

    old_level, old_tier = _tier_for_xp(entry["xp"])
    entry["xp"] = entry.get("xp", 0) + xp_amount
    new_level, new_tier = _tier_for_xp(entry["xp"])
    entry["level"] = new_level
    entry["tier"] = new_tier

    affinities[lang] = entry
    roster["language_affinities"] = affinities
    save_json(roster_file, roster)

    leveled_up = new_level > old_level
    return leveled_up, old_tier, new_tier


def get_player_elements(min_level: int = 2) -> set[str]:
    """Return the set of elements the player has meaningful affinity in (level >= min_level = 'comfortable'+)."""
    roster = load_json(BUDDYMON_DIR / "roster.json")
    elements: set[str] = set()
    for lang, entry in roster.get("language_affinities", {}).items():
        if entry.get("level", 0) >= min_level:
            elem = LANGUAGE_ELEMENTS.get(lang)
            if elem:
                elements.add(elem)
    return elements


def element_multiplier(encounter: dict, player_elements: set[str]) -> float:
    """Return a wound/resolve rate multiplier based on elemental matchup.

    super effective  (+25%): player has an element the monster is weak_against
    not very effective (-15%): player element is in monster's strong_against
    immune (-30%): all player elements are in monster's immune_to
    mixed (+5%): advantage and disadvantage cancel, slight net bonus
    """
    if not player_elements:
        return 1.0
    weak = set(encounter.get("weak_against", []))
    strong = set(encounter.get("strong_against", []))
    immune = set(encounter.get("immune_to", []))

    has_advantage = bool(player_elements & weak)
    has_disadvantage = bool(player_elements & strong)
    fully_immune = bool(immune) and player_elements.issubset(immune)

    if fully_immune:
        return 0.70
    elif has_advantage and has_disadvantage:
        return 1.05  # mixed — slight net bonus
    elif has_advantage:
        return 1.25
    elif has_disadvantage:
        return 0.85
    return 1.0


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
    """Return the active buddy ID, skipping any caught monster that slipped in."""
    bid = get_session_state().get("buddymon_id")
    if not bid:
        return None
    # Validate: caught bug/mascot types are trophies, not assignable buddies.
    # If one ended up in state (e.g. from a state corruption), fall back to active.json.
    roster = load_json(BUDDYMON_DIR / "roster.json")
    mon_type = roster.get("owned", {}).get(bid, {}).get("type", "")
    if mon_type in ("caught_bug_monster",):
        fallback = load_json(BUDDYMON_DIR / "active.json")
        bid = fallback.get("buddymon_id", bid)
    return bid


def get_active_encounter():
    encounters = load_json(BUDDYMON_DIR / "encounters.json")
    return encounters.get("active_encounter")


def set_active_encounter(encounter: dict):
    enc_file = BUDDYMON_DIR / "encounters.json"
    data = load_json(enc_file)
    data["active_encounter"] = encounter
    save_json(enc_file, data)


def wound_encounter() -> None:
    """Drop active encounter to minimum strength and flag for re-announcement."""
    enc_file = BUDDYMON_DIR / "encounters.json"
    data = load_json(enc_file)
    enc = data.get("active_encounter")
    if not enc:
        return
    enc["current_strength"] = 5
    enc["wounded"] = True
    enc["announced"] = False   # triggers UserPromptSubmit re-announcement
    enc["last_wounded_at"] = datetime.now().astimezone().isoformat()
    data["active_encounter"] = enc
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


def encounter_still_present(encounter: dict, output_text: str, catalog: dict) -> bool:
    """Return True if the active encounter's error patterns still appear in output."""
    monster_id = encounter.get("id")
    monster = catalog.get("bug_monsters", {}).get(monster_id)
    if not monster or not output_text:
        return False
    sample = output_text[:4000]
    return any(
        re.search(pat, sample, re.IGNORECASE)
        for pat in monster.get("error_patterns", [])
    )


def auto_resolve_encounter(encounter: dict, buddy_id: str | None) -> tuple[int, str]:
    """Defeat encounter automatically, award XP, clear state. Returns (xp, message)."""
    from datetime import datetime, timezone

    enc_file = BUDDYMON_DIR / "encounters.json"
    active_file = BUDDYMON_DIR / "active.json"
    roster_file = BUDDYMON_DIR / "roster.json"

    xp = encounter.get("xp_reward", 50)

    active = load_json(active_file)
    active["session_xp"] = active.get("session_xp", 0) + xp
    save_json(active_file, active)

    if buddy_id:
        roster = load_json(roster_file)
        if buddy_id in roster.get("owned", {}):
            roster["owned"][buddy_id]["xp"] = roster["owned"][buddy_id].get("xp", 0) + xp
            save_json(roster_file, roster)

    data = load_json(enc_file)
    resolved = dict(encounter)
    resolved["outcome"] = "defeated"
    resolved["timestamp"] = datetime.now(timezone.utc).isoformat()
    data.setdefault("history", []).append(resolved)
    data["active_encounter"] = None
    save_json(enc_file, data)

    return xp, resolved["display"]


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



def match_event_encounter(command: str, output: str, session: dict, catalog: dict):
    """Detect non-error-based encounters: git ops, installs, test results."""
    events = catalog.get("event_encounters", {})
    errors_seen = bool(session.get("errors_encountered") or session.get("tools_used", 0) > 5)

    for enc_id, enc in events.items():
        trigger = enc.get("trigger_type", "")

        if trigger == "command":
            if any(re.search(pat, command) for pat in enc.get("command_patterns", [])):
                return enc

        elif trigger == "output":
            if any(re.search(pat, output, re.IGNORECASE) for pat in enc.get("error_patterns", [])):
                return enc

        elif trigger == "test_victory":
            # Only spawn PhantomPass when tests go green after the session has been running a while
            if errors_seen and any(re.search(pat, output, re.IGNORECASE) for pat in enc.get("success_patterns", [])):
                return enc

    return None


def match_test_file_encounter(file_path: str, catalog: dict):
    """Spawn TestSpecter when editing a test file."""
    enc = catalog.get("event_encounters", {}).get("TestSpecter")
    if not enc:
        return None
    name = os.path.basename(file_path).lower()
    if any(re.search(pat, name) for pat in enc.get("test_file_patterns", [])):
        return enc
    return None


def spawn_encounter(enc: dict) -> None:
    """Write an event encounter to active state with announced=False."""
    strength = enc.get("base_strength", 30)
    encounter = {
        "id": enc["id"],
        "display": enc["display"],
        "base_strength": enc.get("base_strength", 30),
        "current_strength": strength,
        "catchable": enc.get("catchable", True),
        "defeatable": enc.get("defeatable", True),
        "xp_reward": enc.get("xp_reward", 50),
        "rarity": enc.get("rarity", "common"),
        "weak_against": enc.get("weak_against", []),
        "strong_against": enc.get("strong_against", []),
        "immune_to": enc.get("immune_to", []),
        "rival": enc.get("rival"),
        # Language mascot fields (no-op for regular encounters)
        "encounter_type": enc.get("type", "event"),
        "language": enc.get("language"),
        "passive_reduction_per_use": enc.get("passive_reduction_per_use", 0),
        "weakened_by": [],
        "announced": False,
    }
    set_active_encounter(encounter)


def try_spawn_language_mascot(lang: str, affinity_level: int, catalog: dict) -> dict | None:
    """Try to spawn a language mascot for lang at the given affinity level.

    Probability = base_rate * (1 + affinity_level * affinity_scale).
    Only fires if no active encounter exists.
    Returns the mascot dict if spawned, None otherwise.
    """
    for _mid, mascot in catalog.get("language_mascots", {}).items():
        if mascot.get("language") != lang:
            continue
        spawn_cfg = mascot.get("spawn", {})
        if affinity_level < spawn_cfg.get("min_affinity_level", 1):
            continue
        base_rate = spawn_cfg.get("base_rate", 0.02)
        affinity_scale = spawn_cfg.get("affinity_scale", 0.3)
        prob = base_rate * (1 + affinity_level * affinity_scale)
        if random.random() < prob:
            spawn_encounter(mascot)
            return mascot
    return None


def apply_passive_mascot_reduction(lang: str) -> bool:
    """If the active encounter is a language mascot for lang, tick down its strength.

    Returns True if a reduction was applied.
    """
    enc_file = BUDDYMON_DIR / "encounters.json"
    enc_data = load_json(enc_file)
    enc = enc_data.get("active_encounter")
    if not enc:
        return False
    if enc.get("encounter_type") != "language_mascot":
        return False
    if enc.get("language") != lang:
        return False

    reduction = enc.get("passive_reduction_per_use", 5)
    old_strength = enc.get("current_strength", enc.get("base_strength", 50))
    new_strength = max(5, old_strength - reduction)
    enc["current_strength"] = new_strength

    # Flag as wounded (and trigger re-announcement) when freshly floored
    if new_strength <= 5 and not enc.get("wounded"):
        enc["wounded"] = True
        enc["announced"] = False

    enc_data["active_encounter"] = enc
    save_json(enc_file, enc_data)
    return True


def format_new_language_message(lang: str, buddy_display: str) -> str:
    return (
        f"\n🗺️  **New language spotted: {lang}!**\n"
        f"   {buddy_display} is excited — this is new territory.\n"
        f"   *Explorer XP bonus earned!* +15 XP\n"
    )


def format_language_levelup_message(lang: str, old_tier: str, new_tier: str, total_xp: int, buddy_display: str) -> str:
    tier_emojis = {
        "discovering": "🔭",
        "familiar": "📖",
        "comfortable": "🛠️",
        "proficient": "⚡",
        "expert": "🎯",
        "master": "👑",
    }
    emoji = tier_emojis.get(new_tier, "⬆️")
    return (
        f"\n{emoji} **{lang} affinity: {old_tier} → {new_tier}!**\n"
        f"   {buddy_display} has grown more comfortable in {lang}.\n"
        f"   *Total {lang} XP: {total_xp}*\n"
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

    catalog = find_catalog()
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

    # ── Bash tool: error detection + auto-resolution + commit tracking ───────
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        output = ""
        # CC Bash tool_response keys: stdout, stderr, interrupted, isImage, noOutputExpected
        if isinstance(tool_response, dict):
            parts = [
                tool_response.get("stdout", ""),
                tool_response.get("stderr", ""),
            ]
            output = "\n".join(p for p in parts if isinstance(p, str) and p)
        elif isinstance(tool_response, str):
            output = tool_response
        elif isinstance(tool_response, list):
            output = "\n".join(
                b.get("text", "") for b in tool_response
                if isinstance(b, dict) and b.get("type") == "text"
            )

        # ── Buddymon CLI display: surface output as additionalContext ─────────
        # Bash tool output is collapsed by default in CC's UI. When the skill
        # runs the CLI, re-emit stdout here so it's always visible inline.
        if "buddymon/cli.py" in command or "buddymon cli.py" in command:
            if output.strip():
                print(json.dumps({
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": output.strip(),
                    }
                }))
            sys.exit(0)  # Skip XP tracking / error scanning for game commands

        existing = get_active_encounter()

        if existing:
            # Already-owned shortcut: dismiss immediately, no XP, no wound cycle.
            # No point fighting something already in the collection.
            enc_id = existing.get("id", "")
            roster_quick = load_json(BUDDYMON_DIR / "roster.json")
            owned_quick = roster_quick.get("owned", {})
            if (enc_id in owned_quick
                    and owned_quick[enc_id].get("type") in ("caught_bug_monster", "caught_language_mascot")
                    and not existing.get("catch_pending")):
                enc_data = load_json(BUDDYMON_DIR / "encounters.json")
                enc_data.setdefault("history", []).append({**existing, "outcome": "dismissed_owned"})
                enc_data["active_encounter"] = None
                save_json(BUDDYMON_DIR / "encounters.json", enc_data)
                messages.append(
                    f"\n🔁 **{existing.get('display', enc_id)}** — already in your collection. Dismissed."
                )
                existing = None  # skip further processing this run

        if existing:
            # On a clean Bash run (monster patterns gone), respect catch_pending,
            # wound a healthy monster, or auto-resolve a wounded one.
            # Probability gates prevent back-to-back Bash runs from instantly
            # resolving encounters before the user can react.
            if output and not encounter_still_present(existing, output, catalog):
                if existing.get("catch_pending"):
                    # User invoked /buddymon catch — hold the monster for this run.
                    # Clear the flag now so the NEXT clean run resumes normal behavior.
                    # The skill sets it again at the start of each /buddymon catch call.
                    existing["catch_pending"] = False
                    enc_data = load_json(BUDDYMON_DIR / "encounters.json")
                    enc_data["active_encounter"] = existing
                    save_json(BUDDYMON_DIR / "encounters.json", enc_data)
                else:
                    # Auto-attack rates scaled by encounter rarity and buddy level.
                    # Multiple parallel sessions share encounters.json — a wound
                    # cooldown prevents them pile-driving the same encounter.
                    rarity = existing.get("rarity", "common")
                    WOUND_RATES = {
                        "very_common": 0.55, "common": 0.40,
                        "uncommon": 0.22, "rare": 0.10, "legendary": 0.02,
                    }
                    RESOLVE_RATES = {
                        "very_common": 0.45, "common": 0.28,
                        "uncommon": 0.14, "rare": 0.05, "legendary": 0.01,
                    }
                    roster = load_json(BUDDYMON_DIR / "roster.json")
                    buddy_level = roster.get("owned", {}).get(buddy_id, {}).get("level", 1)
                    level_scale = 1.0 + (buddy_level / 100) * 0.25
                    elem_mult = element_multiplier(existing, get_player_elements())

                    # Wound cooldown: skip if another session wounded within 30s
                    last_wound = existing.get("last_wounded_at", "")
                    wound_cooldown_ok = True
                    if last_wound:
                        try:
                            from datetime import timezone as _tz
                            last_dt = datetime.fromisoformat(last_wound)
                            age = (datetime.now(_tz.utc) - last_dt).total_seconds()
                            wound_cooldown_ok = age > 30
                        except Exception:
                            pass

                    if existing.get("wounded"):
                        resolve_rate = min(0.70, RESOLVE_RATES.get(rarity, 0.28) * level_scale * elem_mult)
                        if wound_cooldown_ok and random.random() < resolve_rate:
                            xp, display = auto_resolve_encounter(existing, buddy_id)
                            messages.append(
                                f"\n💨 **{display} fled!** (escaped while wounded)\n"
                                f"   {buddy_display} gets partial XP: +{xp}\n"
                            )
                    else:
                        wound_rate = min(0.85, WOUND_RATES.get(rarity, 0.40) * level_scale * elem_mult)
                        if wound_cooldown_ok and random.random() < wound_rate:
                            wound_encounter()
            # else: monster still present, no message — don't spam every tool call
        elif output or command:
            # No active encounter — check for bug monster first, then event encounters
            session = load_json(BUDDYMON_DIR / "session.json")
            monster = match_bug_monster(output, catalog) if output else None
            event = None if monster else match_event_encounter(command, output, session, catalog)
            target = monster or event

            if target and random.random() < 0.70:
                # Skip spawn if this monster is already in the collection —
                # no point announcing something the player already caught.
                target_id = target.get("id", "")
                _owned = load_json(BUDDYMON_DIR / "roster.json").get("owned", {})
                already_owned = (target_id in _owned
                                 and _owned[target_id].get("type")
                                 in ("caught_bug_monster", "caught_language_mascot"))
                if already_owned:
                    pass  # silently skip
                else:
                    if monster:
                        strength = compute_strength(monster, elapsed_minutes=0)
                    else:
                        strength = target.get("base_strength", 30)
                    encounter = {
                        "id": target["id"],
                        "display": target["display"],
                        "base_strength": target.get("base_strength", 50),
                        "current_strength": strength,
                        "catchable": target.get("catchable", True),
                        "defeatable": target.get("defeatable", True),
                        "xp_reward": target.get("xp_reward", 50),
                        "rarity": target.get("rarity", "common"),
                        "weak_against": target.get("weak_against", []),
                        "strong_against": target.get("strong_against", []),
                        "immune_to": target.get("immune_to", []),
                        "rival": target.get("rival"),
                        "weakened_by": [],
                        "announced": False,
                    }
                    set_active_encounter(encounter)

        # Commit detection
        if "git commit" in command and "exit_code" not in str(tool_response):
            session_file = BUDDYMON_DIR / "session.json"
            session = load_json(session_file)
            session["commits_this_session"] = session.get("commits_this_session", 0) + 1
            save_json(session_file, session)

            commit_xp = 20
            add_session_xp(commit_xp)

    # ── Write / Edit: new language detection + affinity + test file encounters ─
    elif tool_name in ("Write", "Edit", "MultiEdit"):
        file_path = tool_input.get("file_path", "")
        if file_path:
            ext = os.path.splitext(file_path)[1].lower()
            lang = KNOWN_EXTENSIONS.get(ext)
            if lang:
                # Fire "new language" bonus only when affinity XP is genuinely zero.
                # Affinity XP in roster.json is the reliable persistent signal;
                # session.json languages_seen was volatile and caused false positives.
                affinity = get_language_affinity(lang)
                if affinity.get("xp", 0) == 0:
                    add_session_xp(15)
                    msg = format_new_language_message(lang, buddy_display)
                    messages.append(msg)

                # Persistent affinity XP — always accumulates
                leveled_up, old_tier, new_tier = add_language_affinity(lang, 3)
                if leveled_up:
                    affinity = get_language_affinity(lang)
                    msg = format_language_levelup_message(lang, old_tier, new_tier, affinity["xp"], buddy_display)
                    messages.append(msg)

                # Passive mascot reduction: coding in this language weakens its encounter
                apply_passive_mascot_reduction(lang)

                # Language mascot spawn: try after affinity update, only if no active encounter
                if not get_active_encounter():
                    affinity = get_language_affinity(lang)
                    try_spawn_language_mascot(lang, affinity.get("level", 0), catalog)

            # TestSpecter: editing a test file with no active encounter
            if not get_active_encounter():
                enc = match_test_file_encounter(file_path, catalog)
                if enc and random.random() < 0.50:
                    spawn_encounter(enc)

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
