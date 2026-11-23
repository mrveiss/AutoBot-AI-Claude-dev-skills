#!/usr/bin/env bash
# git reference-transaction hook: refuse NEW refs outside the standard namespaces.
# Updates and deletes always pass, so cleanup is never blocked.
[ "$1" = prepared ] || exit 0
z=0000000000000000000000000000000000000000
bad=()
while read -r old new ref; do
  [ "$old" = "$z" ] && [ "$new" != "$z" ] || continue
  case "$ref" in
    refs/heads/pr[-/][0-9]*|refs/heads/rv[0-9-]*|refs/heads/review[-/]*|refs/heads/tmp[-/]*) bad+=("$ref") ;;
    refs/heads/*|refs/tags/*|refs/remotes/origin/*|refs/stash|refs/bisect/*|refs/notes/*) ;;
    refs/rewritten/*|refs/worktree/*|refs/original/*|refs/replace/*|refs/prefetch/*) ;;
    refs/*) bad+=("$ref") ;;
  esac
done
[ ${#bad[@]} -eq 0 ] && exit 0
{ echo "ref-guard: refused to create ${bad[*]}"
  echo "Scratch refs pile up in the shared .git of every worktree. Use the commit instead:"
  echo "  sha=\$(~/.claude/scripts/pr-sha <N>)    # fetches pull/<N>/head, prints its SHA, leaves no ref"
} >&2
exit 1
