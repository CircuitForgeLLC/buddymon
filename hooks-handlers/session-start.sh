#!/usr/bin/env bash
# Buddymon SessionStart hook
# Initializes state, loads active buddy, injects session context via additionalContext

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(realpath "$0")")")}"
source "${PLUGIN_ROOT}/lib/state.sh"

buddymon_init

ACTIVE_ID=$(buddymon_get_active)
SESSION_XP=$(buddymon_get_session_xp)

# Load catalog for buddy display info
CATALOG="${PLUGIN_ROOT}/lib/catalog.json"

build_context() {
    local ctx=""

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
