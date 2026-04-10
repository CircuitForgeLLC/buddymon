---
name: buddymon
description: Buddymon companion game — status, roster, encounters, and session management
argument-hint: [start|assign <name>|fight|catch|roster|evolve|statusline|help]
allowed-tools: [Bash, Agent]
---

# /buddymon

Run the CLI:

```bash
python3 ~/.claude/buddymon/cli.py $ARGUMENTS
```

The PostToolUse hook automatically surfaces the output as an inline system-reminder — no need to echo it yourself. After running, respond with one short line of acknowledgement at most (e.g. "Done." or nothing). Do not repeat the output.

---

## Interactive Markers

### `[INPUT_NEEDED: <prompt>]`

Ask the user the exact prompt. Then re-run with their answer appended:

- `fight` + user says "yes" → `python3 ~/.claude/buddymon/cli.py fight --confirmed`
- `evolve` + user says "y" → `python3 ~/.claude/buddymon/cli.py evolve --confirm`
- `start` + user says "2" → `python3 ~/.claude/buddymon/cli.py start 2`
- `assign <name>` + user says "accept" → `python3 ~/.claude/buddymon/cli.py assign <name> --accept`
- `assign <name>` + user says "reroll" → `python3 ~/.claude/buddymon/cli.py assign <name> --reroll`
- `statusline` + user says "y" → delete existing statusLine key from settings.json, re-run `statusline`
- `catch` + user gives weakening input → see catch flow below

### `[HAIKU_NEEDED: <json>]`

Spawn a Haiku subagent to parse ambiguous natural language. Pass the JSON task as the prompt, get a single-line response, then re-run the CLI with the result.

Example — fuzzy match resolution:
```
Agent(model="haiku", prompt=<json>.instruction + "\n\nRespond with ONLY the matching name.")
→ re-run: python3 ~/.claude/buddymon/cli.py assign <haiku_result> --resolved <haiku_result>
```

---

## Catch Flow

When `[INPUT_NEEDED]` fires during `catch`, the user describes which weakening actions they've done.

**If input is numeric** (e.g. `"1 3"`): calculate inline — 1→-20, 2→-20, 3→-10. Sum reductions. Re-run:
```bash
python3 ~/.claude/buddymon/cli.py catch --strength <100 - total_reduction>
```

**If input is natural language** (e.g. `"wrote a failing test and documented it"`): spawn Haiku:
```
Agent(model="haiku", prompt="""
The user described their catch weakening actions: "<user input>"
Actions available: 1=failing_test (-20%), 2=isolation (-20%), 3=comment (-10%)
Reply with ONLY valid JSON: {"actions": [<numbers>], "reduction": <total_percent>}
""")
```
Parse Haiku's JSON → compute remaining strength → re-run:
```bash
python3 ~/.claude/buddymon/cli.py catch --strength <100 - reduction>
```
