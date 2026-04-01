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

## Install

```bash
# From the Claude Code marketplace (once listed):
/install buddymon

# Or manually — clone and add to your project's .claude/settings.json:
git clone https://git.opensourcesolarpunk.com/Circuit-Forge/buddymon.git ~/.claude/plugins/local/buddymon
```

Then add to `~/.claude/settings.json`:
```json
{
  "enabledPlugins": {
    "buddymon@local": true
  }
}
```

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

## Mirrors

- **Primary:** https://git.opensourcesolarpunk.com/Circuit-Forge/buddymon
- **GitHub:** https://github.com/CircuitForgeLLC/buddymon
- **Codeberg:** https://codeberg.org/CircuitForge/buddymon

---

*A [CircuitForge LLC](https://circuitforge.tech) project. MIT license.*
