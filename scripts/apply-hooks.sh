#!/usr/bin/env bash
# apply-hooks.sh — wire the two new guard hooks, and repair one dead matcher.
#
# Three changes to ~/.claude/settings.json, all idempotent:
#
#   1. REPAIR: the worktree-guard commit hook is declared with
#      matcher "Bash(git commit)". `matcher` is a tool-name pattern, not
#      permission-rule syntax (that is what the separate `if` field is for), so
#      as a regex it wants the literal string "Bashgit commit" and never matches
#      the tool name "Bash". The hook has been silently dead. Verified: a
#      `git commit` in the MAIN tree on Dev_new_gui — which the script blocks
#      with exit 1 — was not blocked; git answered instead. Rewritten to
#      matcher "Bash" + if "Bash(git commit *)", which is the documented pairing.
#
#   2. ADD: commit-subject-format.sh, so a malformed subject is caught locally
#      rather than by the PR issue-link gate.
#
#   3. ADD: py-size-warn.sh, so a Python file crossing its size ratchet is
#      reported at edit time rather than by CI.
set -euo pipefail

S="$HOME/.claude/settings.json"
[ -f "$S" ] || { echo "no $S"; exit 1; }

BAK="$S.bak.$(date +%s)"
cp "$S" "$BAK"

jq '
  # 1. repair the dead matcher (no-op once matcher is already "Bash")
  (.hooks.PreToolUse[] | select(.matcher == "Bash(git commit)")) |=
    (.matcher = "Bash"
     | .hooks |= map(if has("if") then . else . + {if: "Bash(git commit *)"} end))
  |
  # 2. add the commit-subject guard to the general Bash group
  (.hooks.PreToolUse[] | select(.matcher == "Bash" and (.hooks | any(.command | test("worktree-cap")))) | .hooks) |=
    (if any(.[]; .command | test("commit-subject-format")) then .
     else . + [{
       type: "command",
       command: "exec \"$HOME/.claude/scripts/commit-subject-format.sh\"",
       if: "Bash(git commit *)",
       statusMessage: "Checking commit subject format..."
     }] end)
  |
  # 3. add the size-ratchet warning after the Python formatter
  (.hooks.PostToolUse[] | select(.matcher == "Edit|Write") | .hooks) |=
    (if any(.[]; .command | test("py-size-warn")) then .
     else . + [{
       type: "command",
       command: "exec \"$HOME/.claude/scripts/py-size-warn.sh\"",
       statusMessage: "Checking Python file size ratchet..."
     }] end)
' "$S" > "$S.new"

jq -e . "$S.new" > /dev/null
mv "$S.new" "$S"

echo "backup: $BAK"
echo
echo "repaired matchers (should be no 'Bash(git commit)' left):"
jq -r '.hooks.PreToolUse[].matcher' "$S" | sed 's/^/  /'
echo
echo "wired:"
jq -r '.hooks.PreToolUse[].hooks[].command, .hooks.PostToolUse[].hooks[].command' "$S" \
  | grep -E 'commit-subject-format|py-size-warn|worktree-cap|git_dir' | sed 's/^/  /'
