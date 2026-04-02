#!/usr/bin/env bash
# Buddymon Stop hook — tally session XP, check challenge, print summary

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(realpath "$0")")")}"
source "${PLUGIN_ROOT}/lib/state.sh"

buddymon_init

ACTIVE_ID=$(buddymon_get_active)
SESSION_XP=$(buddymon_get_session_xp)

if [[ -z "${ACTIVE_ID}" ]] || [[ "${SESSION_XP}" -eq 0 ]]; then
    exit 0
fi

# Load catalog for display info
CATALOG="${PLUGIN_ROOT}/lib/catalog.json"

SUMMARY=$(python3 << PYEOF
import json, os

catalog_file = '${CATALOG}'
active_file = '${BUDDYMON_DIR}/active.json'
roster_file = '${BUDDYMON_DIR}/roster.json'
session_file = '${BUDDYMON_DIR}/session.json'
encounters_file = '${BUDDYMON_DIR}/encounters.json'

catalog = json.load(open(catalog_file))
active = json.load(open(active_file))
roster = json.load(open(roster_file))
session = json.load(open(session_file))

buddy_id = active.get('buddymon_id')
if not buddy_id:
    print('')
    exit()

b = (catalog.get('buddymon', {}).get(buddy_id)
     or catalog.get('evolutions', {}).get(buddy_id) or {})
display = b.get('display', buddy_id)

xp_earned = active.get('session_xp', 0)
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
challenge = active.get('challenge')

lines = [f"\n## 🐾 Session complete — {display}"]
lines.append(f"**+{xp_earned} XP earned** this session")
if commits:
    lines.append(f"  · {commits} commit{'s' if commits != 1 else ''}")
if langs:
    lines.append(f"  · New languages: {', '.join(langs)}")

if leveled_up:
    lines.append(f"\n✨ **LEVEL UP!** {display} is now Lv.{new_level}!")
else:
    filled = min(20, total_xp * 20 // xp_needed)
    bar = '█' * filled + '░' * (20 - filled)
    lines.append(f"XP: [{bar}] {total_xp}/{xp_needed}")

if challenge:
    if challenge_completed:
        lines.append(f"\n🏆 **Challenge complete:** {challenge.get('name','?')} — bonus XP awarded!")
    else:
        lines.append(f"\n⏳ Challenge in progress: {challenge.get('name','?')}")

print('\n'.join(lines))
PYEOF
)

# Reset session XP + clear challenge so next session assigns a fresh one
python3 << PYEOF
import json
active_file = '${BUDDYMON_DIR}/active.json'
active = json.load(open(active_file))
active['session_xp'] = 0
active['challenge'] = None
json.dump(active, open(active_file, 'w'), indent=2)
PYEOF

# Reset session file
buddymon_session_reset

SUMMARY_JSON=$(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "${SUMMARY}" 2>/dev/null)
[[ -z "${SUMMARY_JSON}" ]] && SUMMARY_JSON='""'

cat << EOF
{"systemMessage": ${SUMMARY_JSON}}
EOF

exit 0
