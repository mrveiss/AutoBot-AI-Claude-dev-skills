#!/usr/bin/env bash
# worktree-refresh.sh — keep every worktree current with the PR base.
#
# A branch 460 commits behind is not "waiting", it is decaying: its overlap with
# base grows daily until landing it costs a conflict-resolution session nobody
# schedules. Measured 2026-08-29: 21 parked branches, median 460 behind, oldest
# 839. This keeps that from accruing.
#
#   status    show every worktree's distance from base, change nothing
#   refresh   merge base into each clean, behind worktree
#
# MERGE, NEVER REBASE. Most worktrees belong to other sessions. A rebase
# rewrites history under a live session, orphaning its HEAD and making its next
# push non-fast-forward. A merge commit keeps every existing commit reachable,
# so a session that pulls gets a clean fast-forward and loses nothing. Rebase is
# correct only for a branch you own, which session-lifecycle already handles.
#
# Refuses to touch: a dirty tree, a tree mid-merge/rebase/bisect, the base
# branch itself, and any worktree whose merge conflicts. Each is reported, never
# forced — a tree that will not update is information about live work.

set -uo pipefail

BASE="${REFRESH_BASE:-}"
DRY=0
case "${1:-status}" in
  status)  DRY=1 ;;
  refresh) DRY=0 ;;
  -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
  *) echo "usage: $(basename "$0") {status|refresh}" >&2; exit 2 ;;
esac

git rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git repo" >&2; exit 1; }

if [ -z "$BASE" ]; then
  for c in develop main master Dev_new_gui; do
    git rev-parse --verify --quiet "origin/$c" >/dev/null 2>&1 && { BASE="origin/$c"; break; }
  done
fi
[ -n "$BASE" ] || { echo "no base branch found" >&2; exit 1; }

git fetch origin --quiet 2>/dev/null || echo "warning: fetch failed, using cached refs" >&2

updated=0; skipped_dirty=0; skipped_conflict=0; skipped_busy=0; current=0; behindclean=0

# Parse worktree list into "path<TAB>branch<TAB>locked" records.
WTLIST=$(git worktree list --porcelain 2>/dev/null | python3 -c "
import sys
wt=br=lock=None
def flush():
    if wt: print('\t'.join([wt, br or '', '1' if lock else '']))
for line in sys.stdin.read().split('\n'):
    if line.startswith('worktree '):
        flush(); wt=line[9:]; br=None; lock=None
    elif line.startswith('branch '): br=line[7:].replace('refs/heads/','')
    elif line.startswith('locked'): lock=True
flush()
")
while IFS=$'\t' read -r path branch locked; do
  [ -n "$branch" ] || continue
  short="${branch:0:44}"

  # Never touch the base branch's own checkout — it tracks base by definition.
  if [ "origin/$branch" = "$BASE" ]; then
    continue
  fi

  behind=$(git -C "$path" rev-list --count "$branch..$BASE" 2>/dev/null || echo 0)
  case "$behind" in ''|*[!0-9]*) behind=0 ;; esac
  if [ "$behind" -eq 0 ]; then
    current=$((current+1)); continue
  fi

  gitdir=$(git -C "$path" rev-parse --git-path . 2>/dev/null)
  if [ -e "$path/$(git -C "$path" rev-parse --git-path MERGE_HEAD 2>/dev/null)" ] \
     || [ -d "$path/$(git -C "$path" rev-parse --git-path rebase-merge 2>/dev/null)" ] \
     || [ -d "$path/$(git -C "$path" rev-parse --git-path rebase-apply 2>/dev/null)" ]; then
    printf '  BUSY      %-44s %5s behind (merge/rebase in progress)\n' "$short" "$behind"
    skipped_busy=$((skipped_busy+1)); continue
  fi

  # Mode-only churn is a known worktree artifact (#15253) and is not real work,
  # but anything with content changes is somebody's uncommitted work.
  dirty=$(git -C "$path" status --porcelain 2>/dev/null \
            | grep -vE '(node_modules|__pycache__|\.pyc$)' | wc -l)
  content=$(git -C "$path" diff --numstat 2>/dev/null | awk '{a+=$1+$2} END{print a+0}')
  if [ "${dirty:-0}" -gt 0 ] && [ "${content:-0}" -gt 0 ]; then
    printf '  DIRTY     %-44s %5s behind (uncommitted work, untouched)\n' "$short" "$behind"
    skipped_dirty=$((skipped_dirty+1)); continue
  fi

  if [ "$DRY" -eq 1 ]; then
    printf '  BEHIND    %-44s %5s behind%s\n' "$short" "$behind" "${locked:+  [locked]}"
    behindclean=$((behindclean+1))
    continue
  fi

  if git -C "$path" merge --no-edit "$BASE" >/dev/null 2>&1; then
    printf '  UPDATED   %-44s was %5s behind\n' "$short" "$behind"
    updated=$((updated+1))
  else
    git -C "$path" merge --abort >/dev/null 2>&1
    printf '  CONFLICT  %-44s %5s behind (left untouched)\n' "$short" "$behind"
    skipped_conflict=$((skipped_conflict+1))
  fi
done <<< "$WTLIST"

echo
printf 'current: %s | behind-clean: %s | dirty: %s | busy: %s | conflict: %s | updated: %s\n' \
  "$current" "$behindclean" "$skipped_dirty" "$skipped_busy" "$skipped_conflict" "$updated"
if [ "$DRY" -eq 1 ]; then
  echo "status only — run '$(basename "$0") refresh' to merge $BASE into the clean behind trees."
fi
