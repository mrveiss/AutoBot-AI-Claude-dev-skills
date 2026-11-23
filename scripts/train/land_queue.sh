#!/bin/bash
# Usage: land_queue.sh PR [PR...]  -- lands PRs one at a time, in order.
# Owner rule (2026-11-18): every PR branch is brought up to date with main BEFORE its CI run.
# Per PR: if behind main, merge main into the head (GitHub update-branch), then wait for CI on
# that synced head and land via land_when_green.sh. If main moves while CI runs, re-sync and retry.
# A red result stops the queue: red is fixed in the PR, never retried blind.
R=mrveiss/AutoBot-AI; L=~/.claude/scripts/ledger; D="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${LOG_DIR:-$HOME/.claude/state/m4b}"; mkdir -p "$LOG_DIR"
behind() { gh api "repos/$R/compare/main...$(gh api repos/$R/pulls/$1 -q .head.sha)" -q .behind_by; }
for pr in "$@"; do
  $L hold "ci-slot:$pr" "land_queue" | head -1
  for attempt in 1 2 3; do
    b=$(behind "$pr")
    if [ "${b:-1}" != 0 ]; then
      echo "$(date +%H:%M) #$pr behind=$b -> merging main into the head"
      gh api -X PUT "repos/$R/pulls/$pr/update-branch" -q .message || { echo "#$pr update-branch failed (conflict?)"; exit 2; }
      sleep 90
    fi
    bash "$D/land_when_green.sh" "$pr" > "$LOG_DIR/land_$pr.log" 2>&1; rc=$?
    tail -2 "$LOG_DIR/land_$pr.log"
    [ "$(gh pr view "$pr" --json state -q .state)" = MERGED ] && { echo "#$pr MERGED"; break; }
    if grep -q "NOT-READY" "$LOG_DIR/land_$pr.log" && [ "$(behind "$pr")" != 0 ]; then continue; fi
    echo "#$pr STOP rc=$rc (red or not ready for another reason)"; $L unhold "ci-slot:$pr" | head -1; exit 1
  done
  $L unhold "ci-slot:$pr" | head -1
  [ "$(gh pr view "$pr" --json state -q .state)" = MERGED ] || { echo "#$pr not merged after 3 syncs"; exit 1; }
done
echo "QUEUE DONE: $*"
