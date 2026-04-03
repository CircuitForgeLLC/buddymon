---
name: buddymon
description: Buddymon companion game — status, roster, encounters, and session management
argument-hint: [start|assign <name>|fight|catch|roster]
allowed-tools: [Bash, Read]
---

# /buddymon — Buddymon Companion

The main Buddymon command. Route based on the argument provided.

**Invoked with:** `/buddymon $ARGUMENTS`

---

## Subcommand Routing

Parse `$ARGUMENTS` (trim whitespace, lowercase the first word) and dispatch:

| Argument | Action |
|----------|--------|
| _(none)_ | Show status panel |
| `start` | Choose starter (first-run) |
| `assign <name>` | Assign buddy to this session |
| `fight` | Fight active encounter |
| `catch` | Catch active encounter |
| `roster` | Full roster view |
| `statusline` | Install Buddymon statusline into settings.json |
| `help` | Show command list |

---

## No argument — Status Panel

Read state files and display:

```
╔══════════════════════════════════════════╗
║  🐾 Buddymon                             ║
╠══════════════════════════════════════════╣
║  Active: [display]  Lv.[n]              ║
║  XP: [████████████░░░░░░░░] [n]/[max]  ║
║                                          ║
║  Challenge: [name]                       ║
║  [description]  [★★☆☆☆]  [XP] XP     ║
╚══════════════════════════════════════════╝
```

If an encounter is active, show it below the panel.
If no buddy assigned, prompt `/buddymon assign`.
If no starter chosen, prompt `/buddymon start`.

State files:
- `~/.claude/buddymon/active.json` — active buddy + session XP
- `~/.claude/buddymon/roster.json` — all owned Buddymon
- `~/.claude/buddymon/encounters.json` — active encounter
- `~/.claude/buddymon/session.json` — session stats

---

## `start` — Choose Starter (first-run only)

Check `roster.json` → `starter_chosen`. If already true, show current buddy status instead.

If false, present:
```
╔══════════════════════════════════════════════════════════╗
║  🐾 Choose Your Starter Buddymon                        ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  [1] 🔥 Pyrobyte  — Speedrunner                        ║
║      Moves fast, thinks faster. Loves tight deadlines.  ║
║      Challenges: speed runs, feature sprints            ║
║                                                         ║
║  [2] 🔍 Debuglin  — Tester                            ║
║      Patient, methodical, ruthless.                     ║
║      Challenges: test coverage, bug hunts               ║
║                                                         ║
║  [3] ✂️  Minimox  — Cleaner                            ║
║      Obsessed with fewer lines.                         ║
║      Challenges: refactors, zero-linter runs            ║
║                                                         ║
╚══════════════════════════════════════════════════════════╝
```

Ask for 1, 2, or 3. On choice, write to roster + active:

```python
import json, os

BUDDYMON_DIR = os.path.expanduser("~/.claude/buddymon")
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
catalog = json.load(open(f"{PLUGIN_ROOT}/lib/catalog.json"))

starters = ["Pyrobyte", "Debuglin", "Minimox"]
choice = starters[0]  # replace with user's choice (index 0/1/2)
buddy = catalog["buddymon"][choice]

roster = json.load(open(f"{BUDDYMON_DIR}/roster.json"))
roster["owned"][choice] = {
    "id": choice, "display": buddy["display"],
    "affinity": buddy["affinity"], "level": 1, "xp": 0,
}
roster["starter_chosen"] = True
json.dump(roster, open(f"{BUDDYMON_DIR}/roster.json", "w"), indent=2)

active = json.load(open(f"{BUDDYMON_DIR}/active.json"))
active["buddymon_id"] = choice
active["session_xp"] = 0
active["challenge"] = buddy["challenges"][0] if buddy.get("challenges") else None
json.dump(active, open(f"{BUDDYMON_DIR}/active.json", "w"), indent=2)
```

Greet them and explain the encounter system.

---

## `assign <name>` — Assign Buddy

Fuzzy-match `<name>` against owned Buddymon (case-insensitive, partial).
If ambiguous, list matches and ask which.
If no name given, list roster and ask.

On match, update `active.json` (buddy_id, reset session_xp, set challenge).
Show challenge proposal with Accept / Decline / Reroll.

---

## `fight` — Fight Encounter

**Note:** Encounters auto-resolve when a clean Bash run (no matching error patterns) is detected.
Use `/buddymon fight` when the error was fixed outside Bash (e.g., in a config file) or to manually confirm a fix.

Read `encounters.json` → `active_encounter`. If none: "No active encounter — it may have already been auto-resolved."

Show encounter state. Confirm the user has fixed the bug.

On confirm:
```python
import json, os
from datetime import datetime, timezone

BUDDYMON_DIR = os.path.expanduser("~/.claude/buddymon")

enc_file = f"{BUDDYMON_DIR}/encounters.json"
active_file = f"{BUDDYMON_DIR}/active.json"
roster_file = f"{BUDDYMON_DIR}/roster.json"

encounters = json.load(open(enc_file))
active = json.load(open(active_file))
roster = json.load(open(roster_file))

enc = encounters.get("active_encounter")
if enc and enc.get("defeatable", True):
    xp = enc.get("xp_reward", 50)
    buddy_id = active.get("buddymon_id")
    active["session_xp"] = active.get("session_xp", 0) + xp
    json.dump(active, open(active_file, "w"), indent=2)
    if buddy_id and buddy_id in roster.get("owned", {}):
        roster["owned"][buddy_id]["xp"] = roster["owned"][buddy_id].get("xp", 0) + xp
        json.dump(roster, open(roster_file, "w"), indent=2)
    enc["outcome"] = "defeated"
    enc["timestamp"] = datetime.now(timezone.utc).isoformat()
    encounters.setdefault("history", []).append(enc)
    encounters["active_encounter"] = None
    json.dump(encounters, open(enc_file, "w"), indent=2)
    print(f"+{xp} XP")
```

ShadowBit (🔒) cannot be defeated — redirect to catch.

---

## `catch` — Catch Encounter

Read active encounter. If none: "No active encounter."

**Immediately set `catch_pending = True`** on the encounter to suppress auto-resolve
while the weakening Q&A is in progress:

```python
import json, os
BUDDYMON_DIR = os.path.expanduser("~/.claude/buddymon")
enc_file = f"{BUDDYMON_DIR}/encounters.json"
encounters = json.load(open(enc_file))
enc = encounters.get("active_encounter")
if enc:
    enc["catch_pending"] = True
    encounters["active_encounter"] = enc
    json.dump(encounters, open(enc_file, "w"), indent=2)
```

Show strength and weakening status. If `enc.get("wounded")` is True, note that
it's already at 5% and a catch is near-guaranteed. Explain weaken actions:
- Write a failing test → -20% strength
- Isolate reproduction case → -20% strength
- Add documenting comment → -10% strength

Ask which weakening actions have been done. Apply reductions to `current_strength`.

Catch roll (clear `catch_pending` before rolling — success clears encounter, failure
leaves it active without the flag so auto-resolve resumes naturally):
```python
import json, os, random
from datetime import datetime, timezone

BUDDYMON_DIR = os.path.expanduser("~/.claude/buddymon")
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
catalog = json.load(open(f"{PLUGIN_ROOT}/lib/catalog.json"))

enc_file = f"{BUDDYMON_DIR}/encounters.json"
active_file = f"{BUDDYMON_DIR}/active.json"
roster_file = f"{BUDDYMON_DIR}/roster.json"

encounters = json.load(open(enc_file))
active = json.load(open(active_file))
roster = json.load(open(roster_file))

enc = encounters.get("active_encounter")
buddy_id = active.get("buddymon_id")

# Clear catch_pending before rolling (win or lose)
enc["catch_pending"] = False

buddy_data = (catalog.get("buddymon", {}).get(buddy_id)
              or catalog.get("evolutions", {}).get(buddy_id) or {})
buddy_level = roster.get("owned", {}).get(buddy_id, {}).get("level", 1)
base_catch = buddy_data.get("base_stats", {}).get("catch_rate", 0.4)

current_strength = enc.get("current_strength", 100)
weakness_bonus = (100 - current_strength) / 100 * 0.4
catch_rate = min(0.95, base_catch + weakness_bonus + buddy_level * 0.02)

success = random.random() < catch_rate

if success:
    xp = int(enc.get("xp_reward", 50) * 1.5)
    caught_entry = {
        "id": enc["id"], "display": enc["display"],
        "type": "caught_bug_monster", "level": 1, "xp": 0,
        "caught_at": datetime.now(timezone.utc).isoformat(),
    }
    roster.setdefault("owned", {})[enc["id"]] = caught_entry
    active["session_xp"] = active.get("session_xp", 0) + xp
    json.dump(active, open(active_file, "w"), indent=2)
    if buddy_id and buddy_id in roster.get("owned", {}):
        roster["owned"][buddy_id]["xp"] = roster["owned"][buddy_id].get("xp", 0) + xp
    json.dump(roster, open(roster_file, "w"), indent=2)
    enc["outcome"] = "caught"
    enc["timestamp"] = datetime.now(timezone.utc).isoformat()
    encounters.setdefault("history", []).append(enc)
    encounters["active_encounter"] = None
    json.dump(encounters, open(enc_file, "w"), indent=2)
    print(f"caught:{xp}")
else:
    # Save cleared catch_pending back on failure
    encounters["active_encounter"] = enc
    json.dump(encounters, open(enc_file, "w"), indent=2)
    print(f"failed:{int(catch_rate * 100)}")
```

On success: "🎉 Caught [display]! +[XP] XP (1.5× catch bonus)"
On failure: "💨 Broke free! Weaken it further and try again."

---

## `roster` — Full Roster

Read roster and display:

```
🐾 Your Buddymon
──────────────────────────────────────────
  🔥 Pyrobyte  Lv.3  Speedrunner
     XP: [████████████░░░░░░░░] 450/300

  🔍 Debuglin  Lv.1  Tester
     XP: [████░░░░░░░░░░░░░░░░] 80/100

🏆 Caught Bug Monsters
──────────────────────────────────────────
  👻 NullWraith   — caught 2026-04-01
  🌐 CORSCurse    — caught 2026-03-28

❓ ??? — [n] more creatures to discover...

🗺️ Language Affinities
──────────────────────────────────────────
  🛠️  Python      comfortable  (Lv.2  · 183 XP)
  📖  TypeScript  familiar     (Lv.1  · 72 XP)
  🔭  Rust        discovering  (Lv.0  · 9 XP)
```

Tier emoji mapping:
- 🔭 discovering (0 XP)
- 📖 familiar (50 XP)
- 🛠️  comfortable (150 XP)
- ⚡ proficient (350 XP)
- 🎯 expert (700 XP)
- 👑 master (1200 XP)

Read `roster.json` → `language_affinities`. Skip this section if empty.

---

## `statusline` — Install Buddymon Statusline

Installs the Buddymon statusline into `~/.claude/settings.json`.

The statusline shows active buddy + level + session XP, and highlights any
active encounter in red:

```
🐾 Debuglin Lv.90 · +45xp  ⚔  💀 NullWraith [60%]
```

Run this Python to install:

```python
import json, os, shutil

SETTINGS = os.path.expanduser("~/.claude/settings.json")
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
SCRIPT = os.path.join(PLUGIN_ROOT, "lib", "statusline.sh")

settings = json.load(open(SETTINGS))

if settings.get("statusLine"):
    print("⚠️  A statusLine is already configured. Replace it? (y/n)")
    # ask user — if no, abort
    # if yes, proceed
    pass

settings["statusLine"] = {
    "type": "command",
    "command": f"bash {SCRIPT}",
}
json.dump(settings, open(SETTINGS, "w"), indent=2)
print(f"✅ Buddymon statusline installed. Reload Claude Code to activate.")
```

If a `statusLine` is already set, show the existing command and ask before replacing.

---

## `help`

```
/buddymon             — status panel
/buddymon start       — choose starter (first run)
/buddymon assign <n>  — assign buddy to session
/buddymon fight       — fight active encounter
/buddymon catch       — catch active encounter
/buddymon roster      — view full roster
/buddymon statusline  — install statusline widget
```
