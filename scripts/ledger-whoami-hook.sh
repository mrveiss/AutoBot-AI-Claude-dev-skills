#!/usr/bin/env bash
# SessionStart hook (#19452): tell a starting or resumed session its ledger identity and claims,
# so a session renamed on restart picks up its own work without asking anyone. Never blocks start.
sid=$(jq -r '.session_id // empty' 2>/dev/null)
[ -n "$sid" ] || exit 0
msg=$(CLAUDE_CODE_SESSION_ID="$sid" timeout 10 "$HOME/.claude/scripts/ledger" whoami 2>/dev/null) || exit 0
[ -n "$msg" ] || exit 0
jq -n --arg m "$msg" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $m}}'
