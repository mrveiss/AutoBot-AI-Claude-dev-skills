#!/usr/bin/env bash
# PostToolUse hook: activity is liveness (#19452). Refresh this session's ledger
# claims at most once per LEDGER_BEAT_EVERY seconds; never block or fail a tool call.
sid=$(jq -r '.session_id // empty' 2>/dev/null)
[ -n "$sid" ] || exit 0
stamp="$HOME/.claude/state/ledger-beat/$sid"
every="${LEDGER_BEAT_EVERY:-300}"
if [ -f "$stamp" ] && [ $(( $(date +%s) - $(stat -c %Y "$stamp") )) -lt "$every" ]; then exit 0; fi
mkdir -p "${stamp%/*}" && touch "$stamp"
CLAUDE_CODE_SESSION_ID="$sid" timeout 10 "$HOME/.claude/scripts/ledger" beat --quiet >/dev/null 2>&1 &
exit 0
