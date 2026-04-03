#!/usr/bin/env bash
# Buddymon install script
# Registers the plugin with Claude Code via symlink (dev-friendly — edits are live).
#
# Usage:
#   bash install.sh          # install
#   bash install.sh --uninstall  # remove

set -euo pipefail

PLUGIN_NAME="buddymon"
MARKETPLACE="circuitforge"
VERSION="0.1.1"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

PLUGINS_DIR="${HOME}/.claude/plugins"
CACHE_DIR="${PLUGINS_DIR}/cache/${MARKETPLACE}/${PLUGIN_NAME}/${VERSION}"
INSTALLED_FILE="${PLUGINS_DIR}/installed_plugins.json"
SETTINGS_FILE="${HOME}/.claude/settings.json"
PLUGIN_KEY="${PLUGIN_NAME}@${MARKETPLACE}"

# ── Helpers ──────────────────────────────────────────────────────────────────

die() { echo "❌ $*" >&2; exit 1; }
info() { echo "   $*"; }
ok() { echo "✓  $*"; }

require_python3() {
    python3 -c "import json" 2>/dev/null || die "python3 required"
}

json_get() {
    python3 -c "
import json, sys
try:
    d = json.load(open('$1'))
    keys = '$2'.split('.')
    for k in keys:
        d = d[k] if isinstance(d, dict) else d[int(k)]
    print(json.dumps(d) if isinstance(d, (dict,list)) else d)
except (KeyError, IndexError, FileNotFoundError):
    print('')
" 2>/dev/null
}

# ── Uninstall ─────────────────────────────────────────────────────────────────

uninstall() {
    echo "🗑  Uninstalling ${PLUGIN_KEY}..."

    # Remove symlink / dir from cache
    if [[ -L "${CACHE_DIR}" ]] || [[ -d "${CACHE_DIR}" ]]; then
        rm -rf "${CACHE_DIR}"
        ok "Removed cache entry"
    fi

    # Remove from installed_plugins.json
    if [[ -f "${INSTALLED_FILE}" ]]; then
        python3 << PYEOF
import json
f = '${INSTALLED_FILE}'
d = json.load(open(f))
key = '${PLUGIN_KEY}'
if key in d.get('plugins', {}):
    del d['plugins'][key]
    json.dump(d, open(f, 'w'), indent=2)
    print("   Removed from installed_plugins.json")
PYEOF
    fi

    # Remove from settings.json enabledPlugins
    if [[ -f "${SETTINGS_FILE}" ]]; then
        python3 << PYEOF
import json
f = '${SETTINGS_FILE}'
d = json.load(open(f))
key = '${PLUGIN_KEY}'
if key in d.get('enabledPlugins', {}):
    del d['enabledPlugins'][key]
    json.dump(d, open(f, 'w'), indent=2)
    print("   Removed from enabledPlugins")
PYEOF
    fi

    # Remove from known_marketplaces.json
    KNOWN_MARKETPLACES="${PLUGINS_DIR}/known_marketplaces.json"
    if [[ -f "${KNOWN_MARKETPLACES}" ]]; then
        python3 << PYEOF
import json
f = '${KNOWN_MARKETPLACES}'
d = json.load(open(f))
if '${MARKETPLACE}' in d:
    del d['${MARKETPLACE}']
    json.dump(d, open(f, 'w'), indent=2)
    print("   Removed '${MARKETPLACE}' from known_marketplaces.json")
PYEOF
    fi

    # Remove marketplace plugin symlink (leave marketplace dir in case other CF plugins exist)
    MARKETPLACE_PLUGIN_LINK="${PLUGINS_DIR}/marketplaces/${MARKETPLACE}/plugins/${PLUGIN_NAME}"
    if [[ -L "${MARKETPLACE_PLUGIN_LINK}" ]]; then
        rm "${MARKETPLACE_PLUGIN_LINK}"
        ok "Removed marketplace plugin symlink"
    fi

    echo ""
    echo "✓  ${PLUGIN_KEY} uninstalled. Restart Claude Code to apply."
}

# ── Install ───────────────────────────────────────────────────────────────────

install() {
    echo "🐾 Installing ${PLUGIN_KEY}..."
    echo ""

    require_python3

    # Validate plugin structure
    [[ -f "${REPO_DIR}/.claude-plugin/plugin.json" ]] \
        || die "Missing .claude-plugin/plugin.json — run from the buddymon repo root"
    [[ -f "${REPO_DIR}/hooks/hooks.json" ]] \
        || die "Missing hooks/hooks.json"

    # Create circuitforge marketplace (CC validates plugin name against marketplace index)
    MARKETPLACE_DIR="${PLUGINS_DIR}/marketplaces/${MARKETPLACE}"
    mkdir -p "${MARKETPLACE_DIR}/.claude-plugin"
    mkdir -p "${MARKETPLACE_DIR}/plugins"

    if [[ ! -f "${MARKETPLACE_DIR}/.claude-plugin/marketplace.json" ]]; then
        python3 << PYEOF
import json
f = '${MARKETPLACE_DIR}/.claude-plugin/marketplace.json'
d = {
    "\$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
    "name": "${MARKETPLACE}",
    "description": "CircuitForge LLC Claude Code plugins",
    "owner": {"name": "CircuitForge LLC", "email": "hello@circuitforge.tech"},
    "plugins": [{
        "name": "${PLUGIN_NAME}",
        "description": "Collectible creatures discovered through coding — commit streaks, bug fights, and session challenges",
        "author": {"name": "CircuitForge LLC", "email": "hello@circuitforge.tech"},
        "source": "./plugins/${PLUGIN_NAME}",
        "category": "productivity",
        "homepage": "https://git.opensourcesolarpunk.com/Circuit-Forge/buddymon"
    }]
}
json.dump(d, open(f, 'w'), indent=2)
PYEOF
        ok "Created ${MARKETPLACE} marketplace"
    fi

    # Symlink repo into marketplace plugins dir
    if [[ ! -L "${MARKETPLACE_DIR}/plugins/${PLUGIN_NAME}" ]]; then
        ln -sf "${REPO_DIR}" "${MARKETPLACE_DIR}/plugins/${PLUGIN_NAME}"
        ok "Linked into marketplace plugins dir"
    fi

    # Register marketplace in known_marketplaces.json
    python3 << PYEOF
import json, os
from datetime import datetime, timezone
f = '${PLUGINS_DIR}/known_marketplaces.json'
try:
    d = json.load(open(f))
except FileNotFoundError:
    d = {}
if '${MARKETPLACE}' not in d:
    d['${MARKETPLACE}'] = {
        "source": {"source": "local", "path": '${MARKETPLACE_DIR}'},
        "installLocation": '${MARKETPLACE_DIR}',
        "lastUpdated": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'),
    }
    json.dump(d, open(f, 'w'), indent=2)
    print("   Registered '${MARKETPLACE}' in known_marketplaces.json")
else:
    print("   '${MARKETPLACE}' marketplace already registered")
PYEOF

    # Create cache parent dir
    mkdir -p "$(dirname "${CACHE_DIR}")"

    # Symlink repo into cache (idempotent)
    if [[ -L "${CACHE_DIR}" ]]; then
        existing=$(readlink "${CACHE_DIR}")
        if [[ "${existing}" == "${REPO_DIR}" ]]; then
            info "Cache symlink already points to ${REPO_DIR}"
        else
            rm "${CACHE_DIR}"
            ln -s "${REPO_DIR}" "${CACHE_DIR}"
            ok "Updated cache symlink → ${REPO_DIR}"
        fi
    elif [[ -d "${CACHE_DIR}" ]]; then
        die "${CACHE_DIR} exists as a real directory. Remove it first or run --uninstall."
    else
        ln -s "${REPO_DIR}" "${CACHE_DIR}"
        ok "Created cache symlink → ${REPO_DIR}"
    fi

    # Register in installed_plugins.json
    python3 << PYEOF
import json, os
from datetime import datetime, timezone

f = '${INSTALLED_FILE}'
try:
    d = json.load(open(f))
except FileNotFoundError:
    d = {"version": 2, "plugins": {}}

key = '${PLUGIN_KEY}'
now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')

d.setdefault('plugins', {})[key] = [{
    "scope": "user",
    "installPath": '${CACHE_DIR}',
    "version": '${VERSION}',
    "installedAt": now,
    "lastUpdated": now,
    "gitCommitSha": "local",
}]

json.dump(d, open(f, 'w'), indent=2)
print("   Registered in installed_plugins.json")
PYEOF

    # Enable in settings.json
    python3 << PYEOF
import json, os

f = '${SETTINGS_FILE}'
try:
    d = json.load(open(f))
except FileNotFoundError:
    d = {}

key = '${PLUGIN_KEY}'
d.setdefault('enabledPlugins', {})[key] = True
json.dump(d, open(f, 'w'), indent=2)
print("   Enabled in settings.json")
PYEOF

    # Init state dir
    BUDDYMON_DIR="${HOME}/.claude/buddymon"
    mkdir -p "${BUDDYMON_DIR}"
    ok "Created ${BUDDYMON_DIR}/"

    # Write initial state files if missing
    python3 << PYEOF
import json, os
from datetime import datetime, timezone

d = os.path.expanduser('~/.claude/buddymon')
now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

files = {
    'roster.json': {"_version": 1, "owned": {}, "starter_chosen": False},
    'encounters.json': {"_version": 1, "history": [], "active_encounter": None},
    'active.json': {"_version": 1, "buddymon_id": None, "challenge": None, "session_xp": 0},
    'session.json': {
        "_version": 1, "started_at": now, "xp_earned": 0, "tools_used": 0,
        "files_touched": [], "languages_seen": [], "errors_encountered": [],
        "commits_this_session": 0, "challenge_accepted": False, "challenge_completed": False,
    },
}

for name, default in files.items():
    path = os.path.join(d, name)
    if not os.path.exists(path):
        json.dump(default, open(path, 'w'), indent=2)
        print(f"   Created {name}")
    else:
        print(f"   {name} already exists — kept")

# Pre-create hook_debug.log so the hook sandbox can write to it
log_path = os.path.join(d, 'hook_debug.log')
if not os.path.exists(log_path):
    open(log_path, 'w').close()
    print("   Created hook_debug.log")
PYEOF

    # Copy statusline script to stable user-local path
    cp "${REPO_DIR}/lib/statusline.sh" "${BUDDYMON_DIR}/statusline.sh"
    chmod +x "${BUDDYMON_DIR}/statusline.sh"
    ok "Installed statusline.sh → ${BUDDYMON_DIR}/statusline.sh"

    # Install statusline into settings.json if not already configured
    python3 << PYEOF
import json
f = '${SETTINGS_FILE}'
d = json.load(open(f))
if 'statusLine' not in d:
    d['statusLine'] = {"type": "command", "command": "bash ${BUDDYMON_DIR}/statusline.sh"}
    json.dump(d, open(f, 'w'), indent=2)
    print("   Installed Buddymon statusline in settings.json")
else:
    print("   statusLine already configured — skipped (run /buddymon statusline to install manually)")
PYEOF

    echo ""
    echo "✓  ${PLUGIN_KEY} installed!"
    echo ""
    echo "   Restart Claude Code, then run: /buddymon start"
    echo ""
    echo "   State: ~/.claude/buddymon/"
    echo "   Logs:  hooks write to ~/.claude/buddymon/ JSON — inspect anytime"
    echo ""
    echo "   To uninstall: bash ${REPO_DIR}/install.sh --uninstall"
}

# ── Entry point ───────────────────────────────────────────────────────────────

case "${1:-}" in
    --uninstall|-u) uninstall ;;
    --help|-h)
        echo "Usage: bash install.sh [--uninstall]"
        echo ""
        echo "  (no args)    Install buddymon plugin (symlink, dev-friendly)"
        echo "  --uninstall  Remove plugin and clean up settings"
        ;;
    *) install ;;
esac
