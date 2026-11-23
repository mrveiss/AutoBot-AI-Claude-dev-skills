#!/bin/bash
# Usage: land_when_green.sh [--dry-run] PR  -- waits until every check's latest run settles, then merges only if all green, 0 unresolved threads, 0 behind.
# pending=0 with fail>0 while a rerun_infra_failures.sh watcher for the same PR is alive => keeps polling (waiting-on-infra-rerun); no watcher => RED.
# REQUIRED-MISSING with workflow runs of the head still queued/in progress -> logs 'required checks not created yet', re-polls (restart of this script); exits only when none is active.
# --dry-run: one pass, prints the decision (poll|waiting-on-infra-rerun|RED|NOT-READY|REQUIRED-MISSING|would-merge), never merges.
S="$(cd "$(dirname "$0")" && pwd)"; DRY=0; [ "$1" = "--dry-run" ] && { DRY=1; shift; }; PR=$1; [ "$2" = "--dry-run" ] && DRY=1
rerun_alive() { ps -eo args | awk -v pr="$PR" '{for(i=1;i<=2&&i<NF;i++) if ($i ~ /(^|\/)rerun_infra_failures\.sh$/ && (i==1||$1 ~ /(^|\/)bash$/)) {for(j=i+1;j<=NF;j++) if ($j !~ /^--/) {if ($j==pr) f=1; break}}} END{exit !f}'; }
rerun_note() { local f l; for f in "rerun_$PR.log" "${TRAIN_WORK:-$HOME/.claude/state/train/work}/rerun_$PR.log"; do [ -f "$f" ] && { l=$(grep -E "(REAL-FAILURE|ATTEMPTS-EXHAUSTED) #$PR" "$f" | tail -n 1); [ -n "$l" ] && { echo " ($l)"; return; }; }; done; }
# From the retired automerge.sh: a PR already MERGED is done, a CLOSED one stops the watcher (an empty state is a failed API call: keep going).
pst=$(gh pr view "$PR" -R mrveiss/AutoBot-AI --json state -q .state 2>/dev/null)
[ "$pst" = MERGED ] && { echo "#$PR already MERGED"; exit 0; }
[ "$pst" = CLOSED ] && { echo "#$PR is CLOSED, stopping"; exit 1; }
while :; do sha=$(gh api repos/mrveiss/AutoBot-AI/pulls/$PR -q .head.sha); r=$($S/rest_latest.sh $sha); echo "$(date +%H:%M) #$PR ${sha:0:10} $r"
  case "$r" in
    *" pending=0") case "$r" in fail=0*) break;; esac
      if rerun_alive; then echo "$(date +%H:%M) #$PR ${sha:0:10} $r waiting-on-infra-rerun"; [ "$DRY" = 1 ] && { echo "DECISION: waiting-on-infra-rerun"; exit 0; }
      else break; fi;;
    *) [ "$DRY" = 1 ] && { echo "DECISION: poll"; exit 0; };;
  esac
  sleep 120; done
case "$r" in fail=0*) ;; *) echo "RED #$PR$(rerun_note)"; [ "$DRY" = 1 ] && echo "DECISION: RED"; exit 1;; esac
beh=$(gh api repos/mrveiss/AutoBot-AI/compare/main...$sha -q .behind_by); th=$(gh api graphql -f query="{repository(owner:\"mrveiss\",name:\"AutoBot-AI\"){pullRequest(number:$PR){reviewThreads(first:100){nodes{isResolved}}}}}" -q '[.data.repository.pullRequest.reviewThreads.nodes[]|select(.isResolved==false)]|length')
echo "behind=$beh threads=$th"; [ "$beh" = 0 ] && [ "$th" = 0 ] || { echo "NOT-READY #$PR"; [ "$DRY" = 1 ] && echo "DECISION: NOT-READY"; exit 1; }
# 2026-11-14: paginated - a head with more than 100 check runs (a superseded first run doubles them) hid required contexts on page 2.
ok=$(gh api --paginate "repos/mrveiss/AutoBot-AI/commits/$sha/check-runs?per_page=100" -q '.check_runs[]|{n:.name,t:(.started_at//""),c:(.conclusion//"")}' | jq -rs 'group_by(.n)|map(max_by(.t))|map(select(.c=="success" or .c=="skipped" or .c=="neutral"))|.[].n')
miss=""; while read -r ctx; do [ -n "$ctx" ] && ! grep -qxF "$ctx" <<< "$ok" && miss="$miss [$ctx]"; done < <(gh api repos/mrveiss/AutoBot-AI/branches/main/protection/required_status_checks -q '.contexts[]')
[ -z "$miss" ] || { nq=$(gh api --paginate "repos/mrveiss/AutoBot-AI/actions/runs?head_sha=$sha&per_page=100" -q '.workflow_runs[]|select(.status!="completed")|.id' | grep -c .)
  if [ "${nq:-0}" -gt 0 ]; then echo "$(date +%H:%M) #$PR ${sha:0:10} required checks not created yet (queued runs: $nq)"; [ "$DRY" = 1 ] && { echo "DECISION: poll"; exit 0; }; sleep 120; exec bash "$S/land_when_green.sh" "$PR"; fi
  echo "REQUIRED-MISSING #$PR:$miss"; [ "$DRY" = 1 ] && echo "DECISION: REQUIRED-MISSING"; exit 1; }
[ "$DRY" = 1 ] && { echo "DECISION: would-merge #$PR $sha"; exit 0; }
m=$(gh api -X PUT "repos/mrveiss/AutoBot-AI/pulls/$PR/merge" -f merge_method=merge -f sha="$sha" -q .sha) && { echo "MERGED #$PR as $m"; ~/.claude/scripts/ledger claim task trainmaster --ttl 4h >/dev/null 2>&1; } || { echo "merge refused #$PR"; exit 1; }
