#!/usr/bin/env python3
"""Buddymon CLI — all game logic lives here.

SKILL.md is a thin orchestrator that runs this script and handles
one round of user I/O when the script emits a marker:

  [INPUT_NEEDED: <prompt>]   — ask user, re-run with answer appended
  [HAIKU_NEEDED: <json>]     — spawn Haiku agent to parse NL input, re-run with result

Everything else is deterministic: no LLM reasoning, no context cost.
"""
import sys
import json
import os
import random
from pathlib import Path
from datetime import datetime, timezone


# ── Paths ─────────────────────────────────────────────────────────────────────

BUDDYMON_DIR = Path.home() / ".claude" / "buddymon"


def find_catalog() -> dict:
    pr = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    candidates = [
        Path(pr) / "lib" / "catalog.json" if pr else None,
        Path.home() / ".claude/plugins/cache/circuitforge/buddymon/0.1.0/lib/catalog.json",
        Path.home() / ".claude/plugins/cache/circuitforge/buddymon/0.1.1/lib/catalog.json",
        Path.home() / ".claude/plugins/marketplaces/circuitforge/plugins/buddymon/lib/catalog.json",
    ]
    for p in candidates:
        if p and p.exists():
            return json.loads(p.read_text())
    raise FileNotFoundError("buddymon catalog not found — check plugin installation")


# ── State helpers ─────────────────────────────────────────────────────────────

def load(path) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return {}


def save(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2))


def session_file() -> Path:
    key = str(os.getpgrp())
    return BUDDYMON_DIR / "sessions" / f"{key}.json"


def get_buddy_id() -> str | None:
    try:
        ss = load(session_file())
        bid = ss.get("buddymon_id")
        if bid:
            return bid
    except Exception:
        pass
    return load(BUDDYMON_DIR / "active.json").get("buddymon_id")


def get_session_xp() -> int:
    try:
        return load(session_file()).get("session_xp", 0)
    except Exception:
        return load(BUDDYMON_DIR / "active.json").get("session_xp", 0)


def add_xp(amount: int):
    buddy_id = get_buddy_id()
    sf = session_file()
    try:
        ss = load(sf)
        ss["session_xp"] = ss.get("session_xp", 0) + amount
        save(sf, ss)
    except Exception:
        active = load(BUDDYMON_DIR / "active.json")
        active["session_xp"] = active.get("session_xp", 0) + amount
        save(BUDDYMON_DIR / "active.json", active)

    if buddy_id:
        roster = load(BUDDYMON_DIR / "roster.json")
        if buddy_id in roster.get("owned", {}):
            roster["owned"][buddy_id]["xp"] = roster["owned"][buddy_id].get("xp", 0) + amount
            save(BUDDYMON_DIR / "roster.json", roster)


# ── Display helpers ───────────────────────────────────────────────────────────

def xp_bar(current: int, maximum: int, width: int = 20) -> str:
    if maximum <= 0:
        return "░" * width
    filled = int(width * min(current, maximum) / maximum)
    return "█" * filled + "░" * (width - filled)


def compute_level(total_xp: int) -> int:
    level = 1
    while total_xp >= level * 100:
        level += 1
    return level


# ── Element system (mirrors post-tool-use.py) ─────────────────────────────────

LANGUAGE_ELEMENTS = {
    "Python":     "dynamic", "Ruby":       "dynamic", "JavaScript": "dynamic",
    "TypeScript": "typed",   "Java":       "typed",   "C#":         "typed",
    "Go":         "typed",   "Rust":       "systems", "C":          "systems",
    "C++":        "systems", "Bash":       "shell",   "Shell":      "shell",
    "PowerShell": "shell",   "HTML":       "web",     "CSS":        "web",
    "Vue":        "web",     "React":      "web",     "SQL":        "data",
    "GraphQL":    "data",    "JSON":       "data",    "YAML":       "data",
    "Kotlin":     "typed",   "Swift":      "typed",   "PHP":        "dynamic",
    "Perl":       "dynamic", "R":          "data",    "Julia":      "data",
    "TOML":       "data",    "Dockerfile": "systems",
}

ELEMENT_MATCHUPS = {
    # (attacker_element, defender_element): multiplier
    ("dynamic", "typed"):   1.25,  ("dynamic", "systems"): 0.85,
    ("typed",   "shell"):   1.25,  ("typed",   "dynamic"): 0.85,
    ("systems", "web"):     1.25,  ("systems", "typed"):   0.85,
    ("shell",   "dynamic"): 1.25,  ("shell",   "data"):    0.85,
    ("web",     "data"):    1.25,  ("web",     "systems"): 0.70,
    ("data",    "dynamic"): 1.25,  ("data",    "web"):     0.85,
}

LANGUAGE_AFFINITY_TIERS = [
    (0,    "discovering"),
    (50,   "familiar"),
    (150,  "comfortable"),
    (350,  "proficient"),
    (700,  "expert"),
    (1200, "master"),
]
TIER_EMOJI = {
    "discovering": "🔭", "familiar": "📖", "comfortable": "🛠️",
    "proficient": "⚡", "expert": "🎯", "master": "👑",
}


def get_player_elements(roster: dict, min_level: int = 2) -> set:
    """Return the set of elements the player has meaningful affinity in."""
    elements = set()
    for lang, data in roster.get("language_affinities", {}).items():
        if data.get("level", 0) >= min_level:
            elem = LANGUAGE_ELEMENTS.get(lang)
            if elem:
                elements.add(elem)
    return elements


def element_multiplier(enc: dict, player_elements: set) -> float:
    """Calculate catch rate bonus from element matchup."""
    enc_elems = set(enc.get("weak_against", []))
    immune_elems = set(enc.get("immune_to", []))
    strong_elems = set(enc.get("strong_against", []))

    if player_elements & immune_elems:
        return 0.70
    if player_elements & enc_elems:
        return 1.25
    if player_elements & strong_elems:
        return 0.85
    return 1.0


# ── Subcommands ───────────────────────────────────────────────────────────────

def cmd_status():
    active = load(BUDDYMON_DIR / "active.json")
    roster = load(BUDDYMON_DIR / "roster.json")
    enc_data = load(BUDDYMON_DIR / "encounters.json")

    if not roster.get("starter_chosen"):
        print("No starter chosen yet. Run: /buddymon start")
        return

    buddy_id = get_buddy_id() or active.get("buddymon_id")
    if not buddy_id:
        print("No buddy assigned to this session. Run: /buddymon assign <name>")
        return

    sf = session_file()
    try:
        ss = load(sf)
        session_xp = ss.get("session_xp", 0)
        challenge = ss.get("challenge") or active.get("challenge")
    except Exception:
        session_xp = active.get("session_xp", 0)
        challenge = active.get("challenge")

    owned = roster.get("owned", {})
    buddy = owned.get(buddy_id, {})
    display = buddy.get("display", buddy_id)
    total_xp = buddy.get("xp", 0)
    level = buddy.get("level", compute_level(total_xp))
    max_xp = level * 100
    xp_in_level = total_xp % max_xp if max_xp else 0
    bar = xp_bar(xp_in_level, max_xp)

    ch_name = ""
    if challenge:
        ch_name = challenge.get("name", str(challenge)) if isinstance(challenge, dict) else str(challenge)

    evolved_from = buddy.get("evolved_from", "")
    prestige = f"  (prestige from {evolved_from})" if evolved_from else ""

    print("╔══════════════════════════════════════════╗")
    print("║  🐾 Buddymon                             ║")
    print("╠══════════════════════════════════════════╣")
    lv_str = f"Lv.{level}{prestige}"
    print(f"║  Active: {display}")
    print(f"║  {lv_str}")
    print(f"║  XP: [{bar}] {xp_in_level}/{max_xp}")
    print(f"║  Session: +{session_xp} XP")
    if ch_name:
        print(f"║  Challenge: {ch_name}")
    print("╚══════════════════════════════════════════╝")

    enc = enc_data.get("active_encounter")
    if enc:
        enc_display = enc.get("display", "???")
        strength = enc.get("current_strength", 100)
        wounded = enc.get("wounded", False)
        print(f"\n⚔️  Active encounter: {enc_display} [{strength}% strength]")
        if wounded:
            print("   ⚠️  Wounded — `/buddymon catch` for near-guaranteed capture.")
        else:
            print("   Run `/buddymon fight` or `/buddymon catch`")


def cmd_fight(confirmed: bool = False):
    enc_data = load(BUDDYMON_DIR / "encounters.json")
    enc = enc_data.get("active_encounter")

    if not enc:
        print("No active encounter — it may have already been auto-resolved.")
        return

    display = enc.get("display", "???")
    strength = enc.get("current_strength", 100)

    if enc.get("id") == "ShadowBit":
        print(f"⚠️  {display} cannot be defeated — use `/buddymon catch` instead.")
        return

    if not confirmed:
        print(f"⚔️  Fighting {display} [{strength}% strength]")
        print(f"\n[INPUT_NEEDED: Have you fixed the bug that triggered {display}? (yes/no)]")
        return

    # Confirmed — award XP and clear
    xp = enc.get("xp_reward", 50)
    add_xp(xp)

    enc["outcome"] = "defeated"
    enc["timestamp"] = datetime.now(timezone.utc).isoformat()
    enc_data.setdefault("history", []).append(enc)
    enc_data["active_encounter"] = None
    save(BUDDYMON_DIR / "encounters.json", enc_data)

    print(f"✅ Defeated {display}! +{xp} XP")


def cmd_catch(args: list[str]):
    enc_data = load(BUDDYMON_DIR / "encounters.json")
    enc = enc_data.get("active_encounter")

    if not enc:
        print("No active encounter.")
        return

    display = enc.get("display", "???")
    current_strength = enc.get("current_strength", 100)
    wounded = enc.get("wounded", False)
    is_mascot = enc.get("encounter_type") == "language_mascot"

    # --strength N means we already have a resolved strength value; go straight to roll
    strength_override = None
    if "--strength" in args:
        idx = args.index("--strength")
        try:
            strength_override = int(args[idx + 1])
        except (IndexError, ValueError):
            pass

    if strength_override is None and not wounded:
        enc["catch_pending"] = True
        enc_data["active_encounter"] = enc
        save(BUDDYMON_DIR / "encounters.json", enc_data)

        print(f"🎯 Catching {display} [{current_strength}% strength]")
        print()
        if is_mascot:
            lang = enc.get("language", "this language")
            print("Weakening actions (language mascots weaken through coding):")
            print(f"  1) Write 10+ lines in {lang}          → -20% strength")
            print(f"  2) Refactor existing {lang} code       → -15% strength")
            print(f"  3) Add type annotations / docs         → -10% strength")
        else:
            print("Weakening actions:")
            print("  1) Write a failing test            → -20% strength")
            print("  2) Isolate a minimal repro case    → -20% strength")
            print("  3) Add a documenting comment       → -10% strength")
        print()
        print("[INPUT_NEEDED: Which have you done? Enter numbers (e.g. \"1 2\"), describe in words, or \"none\" to throw now]")
        return

    # Resolve to a final strength and roll
    final_strength = strength_override if strength_override is not None else current_strength
    enc["catch_pending"] = False

    roster = load(BUDDYMON_DIR / "roster.json")
    buddy_id = get_buddy_id() or load(BUDDYMON_DIR / "active.json").get("buddymon_id")

    try:
        catalog = find_catalog()
    except Exception:
        catalog = {}

    buddy_data = (catalog.get("buddymon", {}).get(buddy_id)
                  or catalog.get("evolutions", {}).get(buddy_id) or {})
    buddy_level = roster.get("owned", {}).get(buddy_id, {}).get("level", 1)
    weakness_bonus = (100 - final_strength) / 100 * 0.4
    player_elems = get_player_elements(roster)
    elem_mult = element_multiplier(enc, player_elems)

    if is_mascot:
        # Mascot formula: base catch from mascot catalog + affinity bonus (6% per level)
        mascot_data = catalog.get("language_mascots", {}).get(enc.get("id", ""), {})
        lang = enc.get("language") or mascot_data.get("language", "")
        lang_affinity = roster.get("language_affinities", {}).get(lang, {})
        affinity_level = lang_affinity.get("level", 0)
        base_catch = mascot_data.get("base_stats", {}).get("catch_rate", 0.35)
        affinity_bonus = affinity_level * 0.06
        catch_rate = min(0.95, (base_catch + affinity_bonus + weakness_bonus + buddy_level * 0.01) * elem_mult)
    else:
        base_catch = buddy_data.get("base_stats", {}).get("catch_rate", 0.4)
        catch_rate = min(0.95, (base_catch + weakness_bonus + buddy_level * 0.02) * elem_mult)

    success = random.random() < catch_rate

    if success:
        xp = int(enc.get("xp_reward", 50) * 1.5)

        if is_mascot:
            lang = enc.get("language", "")
            caught_entry = {
                "id": enc["id"],
                "display": enc["display"],
                "type": "caught_language_mascot",
                "language": lang,
                "level": 1,
                "xp": 0,
                "caught_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            caught_entry = {
                "id": enc["id"],
                "display": enc["display"],
                "type": "caught_bug_monster",
                "level": 1,
                "xp": 0,
                "caught_at": datetime.now(timezone.utc).isoformat(),
            }

        roster.setdefault("owned", {})[enc["id"]] = caught_entry
        if buddy_id and buddy_id in roster.get("owned", {}):
            roster["owned"][buddy_id]["xp"] = roster["owned"][buddy_id].get("xp", 0) + xp
        save(BUDDYMON_DIR / "roster.json", roster)

        add_xp(xp)

        enc["outcome"] = "caught"
        enc["timestamp"] = datetime.now(timezone.utc).isoformat()
        enc_data.setdefault("history", []).append(enc)
        enc_data["active_encounter"] = None
        save(BUDDYMON_DIR / "encounters.json", enc_data)

        elem_hint = ""
        if elem_mult > 1.0:
            if is_mascot:
                elem_hint = " ⚡ Affinity resonance!"
            else:
                elem_hint = " ⚡ Super effective!"
        elif elem_mult < 0.85:
            elem_hint = " 🛡️  Resistant."

        if is_mascot:
            lang_disp = enc.get("language", "")
            print(f"🎉 Caught {display}!{elem_hint} +{xp} XP")
            if lang_disp:
                print(f"   Now assign it as your buddy to unlock {lang_disp} challenges.")
        else:
            print(f"🎉 Caught {display}!{elem_hint} +{xp} XP (1.5× catch bonus)")
    else:
        enc_data["active_encounter"] = enc
        save(BUDDYMON_DIR / "encounters.json", enc_data)
        if is_mascot:
            lang = enc.get("language", "this language")
            print(f"💨 {display} slipped away! Keep coding in {lang} to weaken it further. ({int(catch_rate * 100)}% catch rate)")
        else:
            print(f"💨 {display} broke free! Weaken it further and try again. ({int(catch_rate * 100)}% catch rate)")


def cmd_roster():
    roster = load(BUDDYMON_DIR / "roster.json")
    owned = roster.get("owned", {})

    try:
        catalog = find_catalog()
    except Exception:
        catalog = {}
    mascot_catalog = catalog.get("language_mascots", {})

    core_buddymon = {k: v for k, v in owned.items()
                     if v.get("type") not in ("caught_bug_monster", "caught_language_mascot")}
    mascots_owned = {k: v for k, v in owned.items() if v.get("type") == "caught_language_mascot"}
    caught = {k: v for k, v in owned.items() if v.get("type") == "caught_bug_monster"}

    print("🐾 Your Buddymon")
    print("─" * 44)
    for bid, b in core_buddymon.items():
        lvl = b.get("level", 1)
        total_xp = b.get("xp", 0)
        max_xp = lvl * 100
        xp_in_level = total_xp % max_xp if max_xp else 0
        bar = xp_bar(xp_in_level, max_xp)
        display = b.get("display", bid)
        affinity = b.get("affinity", "")
        evo_note = f"  → {b['evolved_into']}" if b.get("evolved_into") else ""
        print(f"  {display}  Lv.{lvl}  {affinity}{evo_note}")
        print(f"     XP: [{bar}] {xp_in_level}/{max_xp}")

    if mascots_owned:
        print()
        print("🦎 Language Mascots")
        print("─" * 44)
        for bid, b in sorted(mascots_owned.items(), key=lambda x: x[1].get("caught_at", ""), reverse=True):
            display = b.get("display", bid)
            lang = b.get("language", "")
            caught_at = b.get("caught_at", "")[:10]
            lvl = b.get("level", 1)
            mc = mascot_catalog.get(bid, {})
            assignable = mc.get("assignable", False)
            assign_note = "  ✓ assignable as buddy" if assignable else ""
            evo_chains = mc.get("evolutions", [])
            evo_note = f"  → evolves at Lv.{evo_chains[0]['level']}" if evo_chains else ""
            print(f"  {display}  [{lang}]  Lv.{lvl}{assign_note}{evo_note}")
            print(f"     caught {caught_at}")

    if caught:
        print()
        print("🏆 Caught Bug Monsters")
        print("─" * 44)
        for bid, b in sorted(caught.items(), key=lambda x: x[1].get("caught_at", ""), reverse=True):
            display = b.get("display", bid)
            caught_at = b.get("caught_at", "")[:10]
            print(f"  {display}  — caught {caught_at}")

    affinities = roster.get("language_affinities", {})
    if affinities:
        print()
        print("🗺️  Language Affinities")
        print("─" * 44)
        for lang, data in sorted(affinities.items(), key=lambda x: -x[1].get("xp", 0)):
            tier = data.get("tier", "discovering")
            level = data.get("level", 0)
            xp = data.get("xp", 0)
            emoji = TIER_EMOJI.get(tier, "🔭")
            elem = LANGUAGE_ELEMENTS.get(lang, "")
            elem_tag = f"  [{elem}]" if elem else ""
            # Flag languages that have a spawnable mascot
            has_mascot = any(m.get("language") == lang for m in mascot_catalog.values())
            mascot_tag = "  🦎" if has_mascot and level >= 1 else ""
            print(f"  {emoji}  {lang:<12} {tier:<12} (Lv.{level}  · {xp} XP){elem_tag}{mascot_tag}")

    bug_total = len(catalog.get("bug_monsters", {}))
    mascot_total = len(mascot_catalog)
    missing_bugs = bug_total - len(caught)
    missing_mascots = mascot_total - len(mascots_owned)
    if missing_bugs + missing_mascots > 0:
        parts = []
        if missing_bugs > 0:
            parts.append(f"{missing_bugs} bug monsters")
        if missing_mascots > 0:
            parts.append(f"{missing_mascots} language mascots")
        print(f"\n❓ ??? — {' and '.join(parts)} still to discover...")


def cmd_start(choice: str | None = None):
    roster = load(BUDDYMON_DIR / "roster.json")
    if roster.get("starter_chosen"):
        print("Starter already chosen! Run `/buddymon status` or `/buddymon roster`.")
        return

    starters = {
        "1": ("Pyrobyte",  "🔥", "Speedrunner — loves tight deadlines and feature sprints"),
        "2": ("Debuglin",  "🔍", "Tester — patient, methodical, ruthless bug hunter"),
        "3": ("Minimox",   "✂️",  "Cleaner — obsessed with fewer lines and zero linter runs"),
    }

    if choice is None:
        print("╔══════════════════════════════════════════════════════════╗")
        print("║  🐾 Choose Your Starter Buddymon                        ║")
        print("╠══════════════════════════════════════════════════════════╣")
        for num, (name, emoji, desc) in starters.items():
            print(f"║  [{num}] {emoji} {name:<10} — {desc:<36}║")
        print("╚══════════════════════════════════════════════════════════╝")
        print("\n[INPUT_NEEDED: Choose 1, 2, or 3]")
        return

    # Normalize choice
    key = choice.strip().lower()
    name_map = {v[0].lower(): k for k, v in starters.items()}
    if key in name_map:
        key = name_map[key]
    if key not in starters:
        print(f"Invalid choice '{choice}'. Please choose 1, 2, or 3.")
        return

    bid, emoji, _ = starters[key]
    try:
        catalog = find_catalog()
    except Exception:
        catalog = {}

    buddy_cat = catalog.get("buddymon", {}).get(bid, {})
    challenges = buddy_cat.get("challenges", [])

    roster.setdefault("owned", {})[bid] = {
        "id": bid,
        "display": f"{emoji} {bid}",
        "affinity": buddy_cat.get("affinity", ""),
        "level": 1,
        "xp": 0,
    }
    roster["starter_chosen"] = True
    save(BUDDYMON_DIR / "roster.json", roster)

    active = load(BUDDYMON_DIR / "active.json")
    active["buddymon_id"] = bid
    active["session_xp"] = 0
    active["challenge"] = challenges[0] if challenges else None
    save(BUDDYMON_DIR / "active.json", active)

    sf = session_file()
    try:
        ss = load(sf)
    except Exception:
        ss = {}
    ss["buddymon_id"] = bid
    ss["session_xp"] = 0
    ss["challenge"] = active["challenge"]
    save(sf, ss)

    print(f"✨ You chose {emoji} {bid}!")
    if challenges:
        ch = challenges[0]
        ch_name = ch.get("name", str(ch)) if isinstance(ch, dict) else str(ch)
        print(f"   First challenge: {ch_name}")
    print("\nBug monsters will appear when errors occur in your terminal.")
    print("Run `/buddymon` any time to check your status.")


def cmd_assign(args: list[str]):
    """
    assign            → list roster + [INPUT_NEEDED]
    assign <name>     → fuzzy match → show challenge → [INPUT_NEEDED: accept/decline/reroll]
    assign <name> --accept
    assign <name> --reroll
    assign <name> --resolved <buddy_id>   (Haiku resolved ambiguity)
    """
    roster = load(BUDDYMON_DIR / "roster.json")
    owned = roster.get("owned", {})
    buddymon_ids = [k for k, v in owned.items() if v.get("type") != "caught_bug_monster"]

    if not buddymon_ids:
        print("No Buddymon owned yet. Run `/buddymon start` first.")
        return

    # No name given
    if not args or args[0].startswith("--"):
        print("Your Buddymon:")
        for bid in buddymon_ids:
            b = owned[bid]
            print(f"  {b.get('display', bid)}  Lv.{b.get('level', 1)}")
        print("\n[INPUT_NEEDED: Which buddy do you want for this session?]")
        return

    name_input = args[0]
    rest_flags = args[1:]

    # --resolved bypasses fuzzy match (Haiku already picked)
    if "--resolved" in rest_flags:
        idx = rest_flags.index("--resolved")
        try:
            resolved_id = rest_flags[idx + 1]
        except IndexError:
            resolved_id = name_input
        return cmd_assign([resolved_id] + [f for f in rest_flags if f != "--resolved" and f != resolved_id])

    # Fuzzy match
    query = name_input.lower()
    matches = [bid for bid in buddymon_ids if query in bid.lower()]

    if not matches:
        print(f"No Buddymon matching '{name_input}'. Your roster:")
        for bid in buddymon_ids:
            print(f"  {owned[bid].get('display', bid)}")
        return

    if len(matches) > 1:
        # Emit Haiku marker to resolve ambiguity
        candidates = [owned[m].get("display", m) for m in matches]
        haiku_task = json.dumps({
            "task": "fuzzy_match",
            "input": name_input,
            "candidates": candidates,
            "instruction": "The user typed a partial buddy name. Which candidate do they most likely mean? Reply with ONLY the exact candidate string.",
        })
        print(f"[HAIKU_NEEDED: {haiku_task}]")
        return

    bid = matches[0]
    b = owned[bid]
    display = b.get("display", bid)

    try:
        catalog = find_catalog()
    except Exception:
        catalog = {}

    buddy_cat = (catalog.get("buddymon", {}).get(bid)
                 or catalog.get("evolutions", {}).get(bid) or {})
    challenges = buddy_cat.get("challenges", [])

    if "--accept" in rest_flags:
        # Write session state
        sf = session_file()
        try:
            ss = load(sf)
        except Exception:
            ss = {}

        chosen_challenge = None
        if challenges:
            # Pick randomly unless a specific index was passed
            if "--challenge-idx" in rest_flags:
                idx = rest_flags.index("--challenge-idx")
                try:
                    ci = int(rest_flags[idx + 1])
                    chosen_challenge = challenges[ci % len(challenges)]
                except (IndexError, ValueError):
                    chosen_challenge = random.choice(challenges)
            else:
                chosen_challenge = random.choice(challenges)

        ss["buddymon_id"] = bid
        ss["session_xp"] = ss.get("session_xp", 0)
        ss["challenge"] = chosen_challenge
        save(sf, ss)

        # Also update global default
        active = load(BUDDYMON_DIR / "active.json")
        active["buddymon_id"] = bid
        active["challenge"] = chosen_challenge
        save(BUDDYMON_DIR / "active.json", active)

        ch_name = ""
        if chosen_challenge:
            ch_name = chosen_challenge.get("name", str(chosen_challenge)) if isinstance(chosen_challenge, dict) else str(chosen_challenge)

        print(f"✅ {display} assigned to this session!")
        if ch_name:
            print(f"   Challenge: {ch_name}")
        return

    if "--reroll" in rest_flags:
        # Pick a different challenge and re-show the proposal
        if not challenges:
            print(f"No challenges available for {display}.")
            return
        challenge = random.choice(challenges)
    elif challenges:
        challenge = challenges[0]
    else:
        challenge = None

    ch_name = ""
    ch_desc = ""
    ch_stars = ""
    if challenge:
        if isinstance(challenge, dict):
            ch_name = challenge.get("name", "")
            ch_desc = challenge.get("description", "")
            difficulty = challenge.get("difficulty", 1)
            ch_stars = "★" * difficulty + "☆" * (5 - difficulty)
        else:
            ch_name = str(challenge)

    print(f"🐾 Assign {display} to this session?")
    if ch_name:
        print(f"\n   Challenge: {ch_name}")
        if ch_desc:
            print(f"   {ch_desc}")
        if ch_stars:
            print(f"   Difficulty: {ch_stars}")

    print("\n[INPUT_NEEDED: accept / decline / reroll]")


def cmd_evolve(confirmed: bool = False):
    roster = load(BUDDYMON_DIR / "roster.json")
    active = load(BUDDYMON_DIR / "active.json")
    buddy_id = get_buddy_id() or active.get("buddymon_id")

    if not buddy_id:
        print("No buddy assigned.")
        return

    try:
        catalog = find_catalog()
    except Exception:
        catalog = {}

    owned = roster.get("owned", {})
    buddy = owned.get(buddy_id, {})
    display = buddy.get("display", buddy_id)
    level = buddy.get("level", 1)

    catalog_entry = (catalog.get("buddymon", {}).get(buddy_id)
                     or catalog.get("evolutions", {}).get(buddy_id) or {})
    evolutions = catalog_entry.get("evolutions", [])
    evo = next((e for e in evolutions if level >= e.get("level", 999)), None)

    if not evo:
        target_level = min((e.get("level", 100) for e in evolutions), default=100)
        levels_to_go = max(0, target_level - level)
        print(f"{display} is Lv.{level}. Evolution requires Lv.{target_level} ({levels_to_go} more levels).")
        return

    into_id = evo["into"]
    into_data = catalog.get("evolutions", {}).get(into_id, {})
    into_display = into_data.get("display", into_id)

    old_catch = catalog_entry.get("base_stats", {}).get("catch_rate", 0.4)
    new_catch = into_data.get("base_stats", {}).get("catch_rate", old_catch)
    old_mult = catalog_entry.get("base_stats", {}).get("xp_multiplier", 1.0)
    new_mult = into_data.get("base_stats", {}).get("xp_multiplier", old_mult)

    if not confirmed:
        print("╔══════════════════════════════════════════════════════════╗")
        print("║  ✨ Evolution Ready!                                    ║")
        print("╠══════════════════════════════════════════════════════════╣")
        print(f"║  {display}  Lv.{level}  →  {into_display}")
        print(f"║  catch_rate: {old_catch:.2f} → {new_catch:.2f}  ·  xp_multiplier: {old_mult} → {new_mult}")
        print("║  ⚠️  Resets to Lv.1. Caught monsters stay.")
        print("╚══════════════════════════════════════════════════════════╝")
        print("\n[INPUT_NEEDED: Evolve? (y/n)]")
        return

    # Execute evolution
    now = datetime.now(timezone.utc).isoformat()
    owned[buddy_id]["evolved_into"] = into_id
    owned[buddy_id]["evolved_at"] = now

    challenges = catalog_entry.get("challenges") or into_data.get("challenges", [])
    owned[into_id] = {
        "id": into_id,
        "display": into_display,
        "affinity": into_data.get("affinity", catalog_entry.get("affinity", "")),
        "level": 1,
        "xp": 0,
        "evolved_from": buddy_id,
        "evolved_at": now,
    }
    roster["owned"] = owned
    save(BUDDYMON_DIR / "roster.json", roster)

    sf = session_file()
    try:
        ss = load(sf)
    except Exception:
        ss = {}
    ss["buddymon_id"] = into_id
    ss["session_xp"] = 0
    ss["challenge"] = challenges[0] if challenges else None
    save(sf, ss)

    active["buddymon_id"] = into_id
    active["session_xp"] = 0
    active["challenge"] = ss["challenge"]
    save(BUDDYMON_DIR / "active.json", active)

    ch_name = ""
    if ss["challenge"]:
        ch = ss["challenge"]
        ch_name = ch.get("name", str(ch)) if isinstance(ch, dict) else str(ch)

    print(f"✨ {display} evolved into {into_display}!")
    print("   Starting fresh at Lv.1 — the second climb is faster.")
    if ch_name:
        print(f"   New challenge: {ch_name}")


def cmd_statusline():
    settings_path = Path.home() / ".claude" / "settings.json"
    script_candidates = [
        Path.home() / ".claude/buddymon/statusline.sh",
        Path(os.environ.get("CLAUDE_PLUGIN_ROOT", "")) / "lib/statusline.sh",
        Path.home() / ".claude/plugins/cache/circuitforge/buddymon/0.1.0/lib/statusline.sh",
    ]
    script_path = next((str(p) for p in script_candidates if p.exists()), None)
    if not script_path:
        print("❌ statusline.sh not found. Re-run install.sh.")
        return

    settings = load(settings_path)
    if settings.get("statusLine"):
        existing = settings["statusLine"].get("command", "")
        print(f"⚠️  A statusLine is already configured:\n   {existing}")
        print("\n[INPUT_NEEDED: Replace it? (y/n)]")
        return

    settings["statusLine"] = {"type": "command", "command": f"bash {script_path}"}
    save(settings_path, settings)
    print(f"✅ Buddymon statusline installed. Reload Claude Code to activate.")


def cmd_help():
    print("""/buddymon             — status panel
/buddymon start       — choose starter (first run)
/buddymon assign <n>  — assign buddy to session
/buddymon fight       — fight active encounter
/buddymon catch       — catch active encounter
/buddymon roster      — view full roster
/buddymon evolve      — evolve buddy (Lv.100)
/buddymon statusline  — install statusline widget
/buddymon help        — this list""")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    cmd = args[0].lower() if args else ""
    rest = args[1:]

    dispatch = {
        "":           lambda: cmd_status(),
        "status":     lambda: cmd_status(),
        "fight":      lambda: cmd_fight(confirmed="--confirmed" in rest),
        "catch":      lambda: cmd_catch(rest),
        "roster":     lambda: cmd_roster(),
        "start":      lambda: cmd_start(rest[0] if rest else None),
        "assign":     lambda: cmd_assign(rest),
        "evolve":     lambda: cmd_evolve(confirmed="--confirm" in rest),
        "statusline": lambda: cmd_statusline(),
        "help":       lambda: cmd_help(),
    }

    handler = dispatch.get(cmd)
    if handler:
        handler()
    else:
        print(f"Unknown subcommand '{cmd}'. Run `/buddymon help` for the full list.")
        sys.exit(1)


if __name__ == "__main__":
    main()
