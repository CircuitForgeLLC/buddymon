#!/usr/bin/env bash
# Buddymon state management — read/write ~/.claude/buddymon/ JSON files
# Source this file from hook handlers: source "${CLAUDE_PLUGIN_ROOT}/lib/state.sh"

BUDDYMON_DIR="${HOME}/.claude/buddymon"
ROSTER_FILE="${BUDDYMON_DIR}/roster.json"
ENCOUNTERS_FILE="${BUDDYMON_DIR}/encounters.json"
ACTIVE_FILE="${BUDDYMON_DIR}/active.json"
SESSION_FILE="${BUDDYMON_DIR}/session.json"

buddymon_init() {
    mkdir -p "${BUDDYMON_DIR}"

    if [[ ! -f "${ROSTER_FILE}" ]]; then
        cat > "${ROSTER_FILE}" << 'EOF'
{
  "_version": 1,
  "owned": {},
  "starter_chosen": false
}
EOF
    fi

    if [[ ! -f "${ENCOUNTERS_FILE}" ]]; then
        cat > "${ENCOUNTERS_FILE}" << 'EOF'
{
  "_version": 1,
  "history": [],
  "active_encounter": null
}
EOF
    fi

    if [[ ! -f "${ACTIVE_FILE}" ]]; then
        cat > "${ACTIVE_FILE}" << 'EOF'
{
  "_version": 1,
  "buddymon_id": null,
  "challenge": null,
  "session_xp": 0
}
EOF
    fi

    if [[ ! -f "${SESSION_FILE}" ]]; then
        buddymon_session_reset
    fi
}

buddymon_session_reset() {
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    cat > "${SESSION_FILE}" << EOF
{
  "_version": 1,
  "started_at": "${ts}",
  "xp_earned": 0,
  "tools_used": 0,
  "files_touched": [],
  "languages_seen": [],
  "errors_encountered": [],
  "commits_this_session": 0,
  "challenge_accepted": false,
  "challenge_completed": false
}
EOF
}

buddymon_get_active() {
    if [[ -f "${ACTIVE_FILE}" ]]; then
        python3 -c "import json; d=json.load(open('${ACTIVE_FILE}')); print(d.get('buddymon_id',''))" 2>/dev/null
    fi
}

buddymon_get_session_xp() {
    if [[ -f "${ACTIVE_FILE}" ]]; then
        python3 -c "import json; d=json.load(open('${ACTIVE_FILE}')); print(d.get('session_xp', 0))" 2>/dev/null
    else
        echo "0"
    fi
}

buddymon_get_roster_entry() {
    local id="$1"
    if [[ -f "${ROSTER_FILE}" ]]; then
        python3 -c "
import json
d=json.load(open('${ROSTER_FILE}'))
entry=d.get('owned',{}).get('${id}')
if entry: print(json.dumps(entry))
" 2>/dev/null
    fi
}

buddymon_add_xp() {
    local amount="$1"
    python3 << EOF
import json, os

active_file = '${ACTIVE_FILE}'
roster_file = '${ROSTER_FILE}'

# Update session XP
with open(active_file) as f:
    active = json.load(f)

active['session_xp'] = active.get('session_xp', 0) + ${amount}
buddy_id = active.get('buddymon_id')

with open(active_file, 'w') as f:
    json.dump(active, f, indent=2)

# Update roster
if buddy_id and os.path.exists(roster_file):
    with open(roster_file) as f:
        roster = json.load(f)
    if buddy_id in roster.get('owned', {}):
        roster['owned'][buddy_id]['xp'] = roster['owned'][buddy_id].get('xp', 0) + ${amount}
        with open(roster_file, 'w') as f:
            json.dump(roster, f, indent=2)
EOF
}

buddymon_set_active_encounter() {
    local encounter_json="$1"
    python3 << EOF
import json
enc_file = '${ENCOUNTERS_FILE}'
with open(enc_file) as f:
    data = json.load(f)
data['active_encounter'] = ${encounter_json}
with open(enc_file, 'w') as f:
    json.dump(data, f, indent=2)
EOF
}

buddymon_clear_active_encounter() {
    python3 << EOF
import json
enc_file = '${ENCOUNTERS_FILE}'
with open(enc_file) as f:
    data = json.load(f)
data['active_encounter'] = None
with open(enc_file, 'w') as f:
    json.dump(data, f, indent=2)
EOF
}

buddymon_log_encounter() {
    local encounter_json="$1"
    python3 << EOF
import json
from datetime import datetime, timezone
enc_file = '${ENCOUNTERS_FILE}'
with open(enc_file) as f:
    data = json.load(f)
entry = ${encounter_json}
entry['timestamp'] = datetime.now(timezone.utc).isoformat()
data.setdefault('history', []).append(entry)
with open(enc_file, 'w') as f:
    json.dump(data, f, indent=2)
EOF
}

buddymon_get_active_encounter() {
    if [[ -f "${ENCOUNTERS_FILE}" ]]; then
        python3 -c "
import json
d=json.load(open('${ENCOUNTERS_FILE}'))
e=d.get('active_encounter')
if e: print(json.dumps(e))
" 2>/dev/null
    fi
}

buddymon_starter_chosen() {
    python3 -c "import json; d=json.load(open('${ROSTER_FILE}')); print('true' if d.get('starter_chosen') else 'false')" 2>/dev/null
}

buddymon_add_to_roster() {
    local buddy_json="$1"
    python3 << EOF
import json
roster_file = '${ROSTER_FILE}'
with open(roster_file) as f:
    roster = json.load(f)
entry = ${buddy_json}
bid = entry.get('id')
if bid and bid not in roster.get('owned', {}):
    entry.setdefault('xp', 0)
    entry.setdefault('level', 1)
    roster.setdefault('owned', {})[bid] = entry
    with open(roster_file, 'w') as f:
        json.dump(roster, f, indent=2)
    print('added')
else:
    print('exists')
EOF
}
