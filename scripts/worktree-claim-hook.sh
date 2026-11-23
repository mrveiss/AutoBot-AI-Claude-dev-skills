#!/usr/bin/env bash
# PostToolUse hook: claim a worktree the moment a session creates one.
#
# Provenance recorded by hand is provenance recorded sometimes. This fires on
# every successful `git worktree add`, so the record exists before the session
# has a chance to be interrupted — which is precisely the case it is for.
#
# Fails OPEN and silent: a hook that blocks or complains on the happy path is
# worse than absent provenance.

set -uo pipefail
payload="$(cat 2>/dev/null)" || exit 0
cmd="$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null)" || exit 0
printf '%s' "$cmd" | grep -q 'git .*worktree add' || exit 0

# The path is the first non-flag argument after `add`. -b/-B take a value, so
# skip theirs rather than mistaking a branch name for a directory.
path="$(printf '%s' "$cmd" | tr ' ' '\n' | awk '
  /^add$/      { seen=1; next }
  seen && skip { skip=0; next }
  seen && /^-(b|B)$/ { skip=1; next }
  seen && /^-/ { next }
  seen         { print; exit }
')"
[ -n "$path" ] || exit 0
[ -d "$path" ] || exit 0

"$HOME/.claude/scripts/worktree-claim.sh" claim "$path" >/dev/null 2>&1 || true
exit 0
