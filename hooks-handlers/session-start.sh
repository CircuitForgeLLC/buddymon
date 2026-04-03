#!/usr/bin/env bash
# Buddymon SessionStart hook
# Initializes state, loads active buddy, injects session context via additionalContext

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(realpath "$0")")")}"
source "${PLUGIN_ROOT}/lib/state.sh"

buddymon_init

# Per-session state — keyed by process group ID so parallel sessions are isolated.
SESSION_KEY=$(python3 -c "import os; print(os.getpgrp())")
SESSION_FILE="${BUDDYMON_DIR}/sessions/${SESSION_KEY}.json"
mkdir -p "${BUDDYMON_DIR}/sessions"

# Create session file if missing, inheriting buddy from global active.json
if [[ ! -f "${SESSION_FILE}" ]]; then
    python3 << PYEOF
import json, os
active = {}
try:
    active = json.load(open('${BUDDYMON_DIR}/active.json'))
except Exception:
    pass
session_state = {
    "buddymon_id": active.get("buddymon_id"),
    "challenge": active.get("challenge"),
    "session_xp": 0,
}
json.dump(session_state, open('${SESSION_FILE}', 'w'), indent=2)
PYEOF
fi

ACTIVE_ID=$(python3 -c "import json; d=json.load(open('${SESSION_FILE}')); print(d.get('buddymon_id',''))" 2>/dev/null)
SESSION_XP=$(python3 -c "import json; d=json.load(open('${SESSION_FILE}')); print(d.get('session_xp',0))" 2>/dev/null)

# Load catalog for buddy display info
CATALOG="${PLUGIN_ROOT}/lib/catalog.json"

build_context() {
    local ctx=""

    # ── Session handoff from previous session ──────────────────────────────
    local handoff_file="${BUDDYMON_DIR}/handoff.json"
    if [[ -f "${handoff_file}" ]]; then
        local handoff_block
        handoff_block=$(python3 << PYEOF
import json, os
from datetime import datetime, timezone

try:
    h = json.load(open('${handoff_file}'))
except Exception:
    print('')
    exit()

buddy_id = h.get('buddy_id')
if not buddy_id:
    print('')
    exit()

import json as _json
catalog_file = '${CATALOG}'
try:
    catalog = _json.load(open(catalog_file))
    b = (catalog.get('buddymon', {}).get(buddy_id)
         or catalog.get('evolutions', {}).get(buddy_id) or {})
    display = b.get('display', buddy_id)
except Exception:
    display = buddy_id

lines = [f"### 📬 From your last session ({h.get('date', '?')}) — {display}"]

xp = h.get('xp_earned', 0)
commits = h.get('commits', 0)
langs = h.get('languages', [])
caught = h.get('caught', [])

if xp:
    lines.append(f"- Earned **{xp} XP**")
if commits:
    lines.append(f"- Made **{commits} commit{'s' if commits != 1 else ''}**")
if langs:
    lines.append(f"- Languages touched: {', '.join(langs)}")
if caught:
    lines.append(f"- Caught: {', '.join(caught)}")

challenge = h.get('challenge')
challenge_completed = h.get('challenge_completed', False)
if challenge:
    status = "✅ completed" if challenge_completed else "⏳ still in progress"
    lines.append(f"- Challenge **{challenge.get('name','?')}** — {status}")

enc = h.get('active_encounter')
if enc:
    lines.append(f"- ⚠️  **Unresolved encounter carried over:** {enc.get('display', '?')} (strength: {enc.get('current_strength', 100)}%)")

notes = h.get('notes', [])
if notes:
    lines.append("**Notes:**")
    for n in notes:
        lines.append(f"  · {n}")

print('\n'.join(lines))
PYEOF
        )
        if [[ -n "${handoff_block}" ]]; then
            ctx+="${handoff_block}\n\n"
        fi
        # Archive handoff — consumed for this session
        rm -f "${handoff_file}"
    fi

    # ── No starter chosen yet ─────────────────────────────────────────────
    if [[ "$(buddymon_starter_chosen)" == "false" ]]; then
        ctx="## 🐾 Buddymon — First Encounter!\n\n"
        ctx+="Thrumble here! You don't have a Buddymon yet. Three starters are waiting.\n\n"
        ctx+='Run `/buddymon start` to choose your starter and begin collecting!\n\n'
        ctx+='**Starters available:** 🔥 Pyrobyte (Speedrunner) · 🔍 Debuglin (Tester) · ✂️  Minimox (Cleaner)'
        echo "${ctx}"
        return
    fi

    # ── No buddy assigned to this session ─────────────────────────────────
    if [[ -z "${ACTIVE_ID}" ]]; then
        ctx="## 🐾 Buddymon\n\n"
        ctx+="No buddy assigned to this session. Run \`/buddymon assign <name>\` to assign one.\n"
        ctx+="Run \`/buddymon roster\` to see your roster."
        echo "${ctx}"
        return
    fi

    # ── Active buddy ───────────────────────────────────────────────────────
    local buddy_display buddy_affinity buddy_level buddy_xp
    buddy_display=$(python3 -c "
import json
catalog = json.load(open('${CATALOG}'))
bid = '${ACTIVE_ID}'
b = catalog.get('buddymon', {}).get(bid) or catalog.get('evolutions', {}).get(bid)
if b:
    print(b.get('display', bid))
" 2>/dev/null)

    local roster_entry
    roster_entry=$(buddymon_get_roster_entry "${ACTIVE_ID}")
    if [[ -n "${roster_entry}" ]]; then
        buddy_level=$(echo "${roster_entry}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('level',1))")
        buddy_xp=$(echo "${roster_entry}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('xp',0))")
    else
        buddy_level=1
        buddy_xp=0
    fi

    buddy_display="${buddy_display:-${ACTIVE_ID}}"

    # XP bar (20 chars wide)
    local xp_needed=$(( buddy_level * 100 ))
    local xp_filled=$(( buddy_xp * 20 / xp_needed ))
    [[ ${xp_filled} -gt 20 ]] && xp_filled=20
    local xp_bar=""
    for ((i=0; i<xp_filled; i++)); do xp_bar+="█"; done
    for ((i=xp_filled; i<20; i++)); do xp_bar+="░"; done

    ctx="## 🐾 Buddymon Active: ${buddy_display}\n"
    ctx+="**Lv.${buddy_level}** XP: [${xp_bar}] ${buddy_xp}/${xp_needed}\n\n"

    # Active challenge
    local challenge
    challenge=$(python3 -c "
import json
f = '${ACTIVE_FILE}'
d = json.load(open(f))
ch = d.get('challenge')
if ch:
    print(ch.get('name','?') + ' — ' + ch.get('description',''))
" 2>/dev/null)

    if [[ -n "${challenge}" ]]; then
        ctx+="**Challenge:** 🔥 ${challenge}\n\n"
    fi

    # Active encounter carry-over
    local enc
    enc=$(buddymon_get_active_encounter)
    if [[ -n "${enc}" ]]; then
        local enc_id enc_display enc_strength
        enc_id=$(echo "${enc}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id','?'))")
        enc_display=$(echo "${enc}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('display','?'))")
        enc_strength=$(echo "${enc}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('current_strength',100))")
        ctx+="⚠️  **Unresolved encounter from last session:** ${enc_display} (strength: ${enc_strength}%)\n"
        ctx+="Run \`/buddymon fight\` or \`/buddymon catch\` to resolve it.\n\n"
    fi

    ctx+="*Bug monsters appear from error output. Use \`/buddymon fight\` or \`/buddymon catch\`.*"

    echo "${ctx}"
}

# Assign a fresh challenge if none is set
python3 << PYEOF
import json, random
catalog = json.load(open('${CATALOG}'))
active_file = '${ACTIVE_FILE}'
active = json.load(open(active_file))
buddy_id = active.get('buddymon_id')
if buddy_id and not active.get('challenge'):
    pool = catalog.get('buddymon', {}).get(buddy_id, {}).get('challenges', [])
    if pool:
        active['challenge'] = random.choice(pool)
        json.dump(active, open(active_file, 'w'), indent=2)
PYEOF

CONTEXT=$(build_context)

# Escape for JSON
CONTEXT_JSON=$(python3 -c "
import json, sys
print(json.dumps(sys.argv[1]))" "${CONTEXT}" 2>/dev/null)

if [[ -z "${CONTEXT_JSON}" ]]; then
    CONTEXT_JSON='"🐾 Buddymon loaded."'
fi

cat << EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": ${CONTEXT_JSON}
  }
}
EOF

exit 0
