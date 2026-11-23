#!/usr/bin/env bash
# PreToolUse(Bash) advisory: before `gh issue comment|edit|close|reopen N`,
# show who N is assigned to. Never blocks.
#
# The payload is built with jq, never printf: a command touching several
# issues yields several numbers, and a raw newline inside a printf-built JSON
# string made every such run fail to parse (502 errors in one 14-day window).
set -uo pipefail

cmd=$(jq -r '.tool_input.command // empty' 2>/dev/null) || exit 0
[ -n "$cmd" ] || exit 0

mapfile -t issues < <(printf '%s' "$cmd" \
  | grep -oP 'gh issue (?:comment|edit|close|reopen)\s+\K[0-9]+' 2>/dev/null | sort -un)
[ "${#issues[@]}" -gt 0 ] || exit 0

# Honour an explicit -R/--repo in the command; otherwise gh resolves the
# repo from the working directory.
repo=$(printf '%s' "$cmd" | grep -oP '(?:-R|--repo)[= ]\K[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+' | head -1)
repo_args=()
[ -n "$repo" ] && repo_args=(-R "$repo")

lines=()
for n in "${issues[@]}"; do
  if who=$(gh issue view "$n" "${repo_args[@]}" --json assignees \
             -q '[.assignees[].login] | join(",")' 2>/dev/null); then
    if [ -n "$who" ]; then
      lines+=("Issue #$n assigned to: $who — verify this is your issue before posting.")
    else
      lines+=("Issue #$n has no assignees — verify this is the right issue before posting.")
    fi
  else
    # Distinguish "no assignee" from "could not look".
    lines+=("Issue #$n: could not read assignees (gh lookup failed) — verify ownership manually.")
  fi
done

printf '%s\n' "${lines[@]}" | jq -Rs '{systemMessage: (rtrimstr("\n"))}'
