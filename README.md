# 🐾 Buddymon

A Claude Code plugin that turns your coding sessions into a creature-collecting game.

Buddymon are discovered, caught, and leveled up through real development work — not separate from it.

---

## What it does

- **Bug monsters** spawn from error output during your session (TypeErrors, CORS errors, race conditions, etc.)
- **Buddymon** are companions you assign to sessions — they gain XP and propose challenges
- **Challenges** are proactive goals your buddy sets at session start (write 5 tests, implement a feature in 30 min, net-negative lines)
- **Encounters** require you to fight or catch — catch rate improves if you write a failing test, isolate the repro, or add a comment

---

## Requirements

- [Claude Code](https://claude.ai/code) CLI
- Python 3 (already required by Claude Code)
- bash

---

## Install

Clone the repo anywhere and run the install script:

```bash
git clone https://git.opensourcesolarpunk.com/Circuit-Forge/buddymon.git
cd buddymon
bash install.sh
```

Then **restart Claude Code** and run:

```
/buddymon start
```

The install script:
- Symlinks the repo into `~/.claude/plugins/cache/local/buddymon/0.1.0/`
- Registers the plugin in `~/.claude/plugins/installed_plugins.json`
- Enables it in `~/.claude/settings.json`
- Creates `~/.claude/buddymon/` state directory with initial JSON files

Because it uses a symlink, any `git pull` in the repo is immediately live — no reinstall needed.

### Mirrors

You can clone from any of the three remotes:

```bash
# Forgejo (primary)
git clone https://git.opensourcesolarpunk.com/Circuit-Forge/buddymon.git

# GitHub
git clone https://github.com/CircuitForgeLLC/buddymon.git

# Codeberg
git clone https://codeberg.org/CircuitForge/buddymon.git
```

### Uninstall

```bash
bash install.sh --uninstall
```

Removes the symlink, deregisters from `installed_plugins.json`, and removes the `enabledPlugins` entry. Your `~/.claude/buddymon/` state (roster, XP, encounters) is left intact.

---

## Commands

One command, all subcommands:

| Usage | Description |
|-------|-------------|
| `/buddymon` | Status panel — active buddy, XP, challenge, encounter |
| `/buddymon start` | Choose your starter (first run only) |
| `/buddymon assign <name>` | Assign a buddy to this session |
| `/buddymon fight` | Fight the current bug monster |
| `/buddymon catch` | Attempt to catch the current bug monster |
| `/buddymon roster` | View full roster |
| `/buddymon help` | Show command list |

---

## Bug Monsters

Spawned from error output detected by the `PostToolUse` hook:

| Monster | Trigger | Rarity |
|---------|---------|--------|
| 👻 NullWraith | NullPointerException, AttributeError: NoneType | Common |
| 😈 FencepostDemon | IndexError, ArrayIndexOutOfBounds | Common |
| 🔧 TypeGreml | TypeError, type mismatch | Common |
| 🐍 SyntaxSerpent | SyntaxError, parse error | Very common |
| 🌐 CORSCurse | CORS policy blocked | Common |
| ♾️  LoopLich | Timeout, RecursionError, stack overflow | Uncommon |
| 👁️  RacePhantom | Race condition, deadlock, data race | Rare |
| 🗿 FossilGolem | DeprecationWarning, legacy API | Uncommon |
| 🔒 ShadowBit | Security vulnerability patterns | Rare — catch only |
| 🌫️  VoidSpecter | 404, ENOENT, route not found | Common |
| 🩸 MemoryLeech | OOM, memory leak | Uncommon |

---

## Buddymon (Starters)

| Buddy | Affinity | Discover trigger |
|-------|---------|-----------------|
| 🔥 Pyrobyte | Speedrunner | Starter choice |
| 🔍 Debuglin | Tester | Starter choice |
| ✂️  Minimox | Cleaner | Starter choice |
| 🌙 Noctara | Nocturnal | Late-night session (after 10pm, 2+ hours) |
| 🗺️  Explorah | Explorer | First time writing in a new language |

---

## State

All state lives in `~/.claude/buddymon/` — never in the repo.

```
~/.claude/buddymon/
├── roster.json        # owned Buddymon, XP, levels
├── encounters.json    # encounter history + active encounter
├── active.json        # current session assignment + challenge
└── session.json       # session stats (reset each session)
```

---

*A [CircuitForge LLC](https://circuitforge.tech) project. MIT license.*
