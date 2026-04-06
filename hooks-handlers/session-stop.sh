#!/usr/bin/env bash
# Buddymon Stop hook — tally session XP, check challenge, print summary

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(realpath "$0")")")}"
source "${PLUGIN_ROOT}/lib/state.sh"

buddymon_init

SESSION_KEY=$(python3 -c "import os; print(os.getpgrp())")
SESSION_FILE="${BUDDYMON_DIR}/sessions/${SESSION_KEY}.json"

ACTIVE_ID=$(python3 -c "
import json, sys
try:
    d = json.load(open('${SESSION_FILE}'))
    print(d.get('buddymon_id', ''))
except Exception:
    print('')
" 2>/dev/null)

SESSION_XP=$(python3 -c "
import json, sys
try:
    d = json.load(open('${SESSION_FILE}'))
    print(d.get('session_xp', 0))
except Exception:
    print(0)
" 2>/dev/null)

if [[ -z "${ACTIVE_ID}" ]] || [[ "${SESSION_XP}" -eq 0 ]]; then
    [[ -f "${SESSION_FILE}" ]] && rm -f "${SESSION_FILE}"
    exit 0
fi

# Load catalog for display info
CATALOG="${PLUGIN_ROOT}/lib/catalog.json"

SUMMARY=$(python3 << PYEOF
import json, os

catalog_file = '${CATALOG}'
session_state_file = '${SESSION_FILE}'
roster_file = '${BUDDYMON_DIR}/roster.json'
session_file = '${BUDDYMON_DIR}/session.json'  # SESSION_DATA_FILE from state.sh

catalog = json.load(open(catalog_file))
session_state = json.load(open(session_state_file))
roster = json.load(open(roster_file))
session = {}
try:
    session = json.load(open(session_file))
except Exception:
    pass

buddy_id = session_state.get('buddymon_id')
if not buddy_id:
    print('')
    exit()

b = (catalog.get('buddymon', {}).get(buddy_id)
     or catalog.get('evolutions', {}).get(buddy_id) or {})
display = b.get('display', buddy_id)

xp_earned = session_state.get('session_xp', 0)
level = roster.get('owned', {}).get(buddy_id, {}).get('level', 1)
total_xp = roster.get('owned', {}).get(buddy_id, {}).get('xp', 0)
xp_needed = level * 100

# Check level up
leveled_up = False
new_level = level
while total_xp >= new_level * 100:
    new_level += 1
    leveled_up = True

if leveled_up:
    # Save new level
    roster['owned'][buddy_id]['level'] = new_level
    json.dump(roster, open(roster_file, 'w'), indent=2)

# Session stats
commits = session.get('commits_this_session', 0)
tools = session.get('tools_used', 0)
langs = session.get('languages_seen', [])
challenge_completed = session.get('challenge_completed', False)
challenge = session_state.get('challenge')

lines = [f"\n## 🐾 Session complete — {display}"]
lines.append(f"**+{xp_earned} XP earned** this session")
if commits:
    lines.append(f"  · {commits} commit{'s' if commits != 1 else ''}")
if langs:
    lines.append(f"  · New languages: {', '.join(langs)}")

if leveled_up:
    lines.append(f"\n✨ **LEVEL UP!** {display} is now Lv.{new_level}!")
    # Check if evolution is now available
    catalog_entry = (catalog.get('buddymon', {}).get(buddy_id)
                     or catalog.get('evolutions', {}).get(buddy_id) or {})
    evolutions = catalog_entry.get('evolutions', [])
    evo = next((e for e in evolutions if new_level >= e.get('level', 999)), None)
    if evo:
        into = catalog.get('evolutions', {}).get(evo['into'], {})
        lines.append(f"\n⭐ **EVOLUTION READY!** {display} can evolve into {into.get('display', evo['into'])}!")
        lines.append(f"   Run `/buddymon evolve` to prestige — resets to Lv.1 with upgraded stats.")
else:
    filled = min(20, total_xp * 20 // xp_needed)
    bar = '█' * filled + '░' * (20 - filled)
    lines.append(f"XP: [{bar}] {total_xp}/{xp_needed}")
    # Remind if already at evolution threshold but hasn't evolved yet
    catalog_entry = (catalog.get('buddymon', {}).get(buddy_id)
                     or catalog.get('evolutions', {}).get(buddy_id) or {})
    evolutions = catalog_entry.get('evolutions', [])
    evo = next((e for e in evolutions if level >= e.get('level', 999)), None)
    if evo:
        into = catalog.get('evolutions', {}).get(evo['into'], {})
        lines.append(f"\n⭐ **Evolution available:** `/buddymon evolve` → {into.get('display', evo['into'])}")

if challenge:
    if challenge_completed:
        lines.append(f"\n🏆 **Challenge complete:** {challenge.get('name','?')} — bonus XP awarded!")
    else:
        lines.append(f"\n⏳ Challenge in progress: {challenge.get('name','?')}")

print('\n'.join(lines))
PYEOF
)

# Write handoff.json for next session to pick up
python3 << PYEOF
import json, os
from datetime import datetime, timezone

session_state_file = '${SESSION_FILE}'
session_file = '${BUDDYMON_DIR}/session.json'  # SESSION_DATA_FILE from state.sh
encounters_file = '${BUDDYMON_DIR}/encounters.json'
handoff_file = '${BUDDYMON_DIR}/handoff.json'

session_state = {}
try:
    session_state = json.load(open(session_state_file))
except Exception:
    pass
session_data = {}
try:
    session_data = json.load(open(session_file))
except Exception:
    pass
encounters = {}
try:
    encounters = json.load(open(encounters_file))
except Exception:
    pass

# Collect caught monsters from this session
caught_this_session = [
    e.get('display', e.get('id', '?'))
    for e in encounters.get('history', [])
    if e.get('outcome') == 'caught'
    and e.get('timestamp', '') >= datetime.now(timezone.utc).strftime('%Y-%m-%d')
]

# Carry over any existing handoff notes (user-added via /buddymon note)
existing = {}
try:
    existing = json.load(open(handoff_file))
except Exception:
    pass

handoff = {
    "date": datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    "buddy_id": session_state.get('buddymon_id'),
    "xp_earned": session_state.get('session_xp', 0),
    "commits": session_data.get('commits_this_session', 0),
    "languages": session_data.get('languages_seen', []),
    "caught": caught_this_session,
    "challenge": session_state.get('challenge'),
    "challenge_completed": session_data.get('challenge_completed', False),
    "active_encounter": encounters.get('active_encounter'),
    "notes": existing.get('notes', []),  # preserve any manual notes
}

json.dump(handoff, open(handoff_file, 'w'), indent=2)
PYEOF

# Clean up this session's state file — each session is ephemeral
rm -f "${SESSION_FILE}"

# Reset shared session.json for legacy compatibility
buddymon_session_reset

SUMMARY_JSON=$(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "${SUMMARY}" 2>/dev/null)
[[ -z "${SUMMARY_JSON}" ]] && SUMMARY_JSON='""'

cat << EOF
{"systemMessage": ${SUMMARY_JSON}}
EOF

exit 0
