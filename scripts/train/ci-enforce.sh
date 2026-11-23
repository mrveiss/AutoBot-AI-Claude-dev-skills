#!/usr/bin/env bash
# ci-enforce.sh — owner 2026-11-06: only the PRs being landed next run CI (3 slots, owner 2026-11-08; was 2); everything else is
# cancelled. Every 60 s, cancel via ci-cancel (attributed) every active run whose branch is not in
# ci-admitted.txt. One exception: CodeQL Analysis on a push to main (needed to close alerts on main).
# Also exempt: "Issue landing notes" and "train-content-gate", which run when a PR closes (post-merge
# bookkeeping, no test load) -- cancelling them silently lost landing notes (2026-11-06).
# Runs older than 2026-11-05 are stale ghosts with no live jobs and are ignored.
R=mrveiss/AutoBot-AI; A="${TRAIN_STATE:-$HOME/.claude/state/train}/ci-admitted.txt"
while :; do
  for s in in_progress queued waiting pending requested; do
    gh run list -R $R --status $s --limit 200 --json databaseId,headBranch,createdAt,workflowName,event \
      -q '.[]|select(.createdAt>="2026-11-05")|select(.event=="push" or .event=="pull_request" or .event=="merge_group")|select((.headBranch=="main" and .event=="push")|not)|select(.workflowName!="Issue landing notes" and .workflowName!="train-content-gate")|"\(.databaseId) \(.headBranch)"' 2>/dev/null
  done | sort -u | while read -r id br; do
    grep -qxF "$br" "$A" && continue
    r=$(~/.claude/scripts/ci-cancel "$id" hand "owner 2026-11-06: only the admitted PRs (max 3, owner 2026-11-08) run CI; not admitted" "$br")
    echo "$(date '+%T') cancel $id $br $r"
  done
  sleep 60
done
