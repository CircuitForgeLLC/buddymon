#!/usr/bin/env bash
# Buddymon statusline — displays active buddy + encounter in the CC status bar.
# Install: add to ~/.claude/settings.json → "statusLine" → "command"
# Or run: /buddymon statusline   (installs automatically)

B="$HOME/.claude/buddymon"

# Bail fast if no state directory or no starter chosen
[[ -d "$B" ]] || exit 0
STARTER=$(jq -r '.starter_chosen // false' "$B/roster.json" 2>/dev/null)
[[ "$STARTER" == "true" ]] || exit 0

# Read state
ID=$(jq -r '.buddymon_id // ""' "$B/active.json" 2>/dev/null)
[[ -n "$ID" ]] || exit 0

LVL=$(jq -r ".owned[\"$ID\"].level // 1" "$B/roster.json" 2>/dev/null)

# Per-session XP (accurate for multi-window setups); fall back to active.json
PGRP=$(python3 -c "import os; print(os.getpgrp())" 2>/dev/null)
SESSION_FILE="$B/sessions/${PGRP}.json"
if [[ -f "$SESSION_FILE" ]]; then
    XP=$(jq -r '.session_xp // 0' "$SESSION_FILE" 2>/dev/null)
else
    XP=$(jq -r '.session_xp // 0' "$B/active.json" 2>/dev/null)
fi

ENC_JSON=$(jq -c '.active_encounter // null' "$B/encounters.json" 2>/dev/null)
ENC_DISPLAY=$(echo "$ENC_JSON" | jq -r '.display // ""' 2>/dev/null)
ENC_STRENGTH=$(echo "$ENC_JSON" | jq -r '.current_strength // 0' 2>/dev/null)

# ANSI colors
CY='\033[38;2;23;146;153m'   # cyan  — buddy
GR='\033[38;2;64;160;43m'    # green — xp
RD='\033[38;2;203;60;51m'    # red   — encounter
DM='\033[38;2;120;120;120m'  # dim   — separators
RS='\033[0m'

printf "${CY}🐾 ${ID} Lv.${LVL}${RS}"
printf " ${DM}·${RS} ${GR}+${XP}xp${RS}"

if [[ "$ENC_JSON" != "null" ]] && [[ -n "$ENC_DISPLAY" ]]; then
    printf "  ${RD}⚔  ${ENC_DISPLAY} [${ENC_STRENGTH}%%]${RS}"
fi

echo
