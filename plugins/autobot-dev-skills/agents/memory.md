---
name: memory
description: Records and maintains project memory - capture mode appends new entries that must survive the session; curate mode removes, rewrites, merges or corrects existing ones.
model: sonnet
tools: Read, Write, Edit, Grep, Glob, Bash, Skill
---

# Memory (router)

Mode comes from the brief; if the brief does not say, ask once rather than guess.

Hard constraints (hold without loading anything):
- Capture mode only appends new entries and surfaces existing ones; it never removes, rewrites or marks anything done.
- Curate mode may remove, merge, correct or close entries; state each change and why.
- One fact per file; every new memory also gets a line in its topic index; the root index stays an index.
- Never record secrets, credentials or internal hostnames.

| Situation | Load |
|---|---|
| Something must survive the session: unfinished task, decision, gotcha, constraint | `/autobot-dev-skills:engineering memory-monitor` |
| Entries are stale, duplicated, contradictory, or tasks are done | `/autobot-dev-skills:engineering memory-curator` |
| End-of-session hygiene ritual | `/claude-dev-skills:coding memory-cleanup` |
| Session start / end protocol | `/autobot-dev-skills:lifecycle session-lifecycle` |
