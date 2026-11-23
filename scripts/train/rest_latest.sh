#!/bin/bash
# Usage: rest_latest.sh SHA -- prints "fail=N pending=N" (the ONE definition of "pending" for land_when_green.sh and
# rerun_infra_failures.sh). fail = latest check run per name with a non-success conclusion. pending = MAX of:
#  (a) check runs without a conclusion (latest per name);
#  (b) workflow runs of the head whose status != completed (a queued run has created no check runs yet; MAX, not sum,
#      so a run and its own check runs are not double counted);
#  (c) required contexts of main with no check run at this head - but only while some workflow run of the head is not
#      completed OR the head commit is < 20 min old; otherwise (CI parked/cancelled) it reports 0 so the caller's own
#      REQUIRED-MISSING / IDLE gate fires instead of polling forever.
# On an API error prints "ERR ..." (never matches pending=0).
R=mrveiss/AutoBot-AI
sha=$1; [ -n "$sha" ] || { echo "ERR no-sha"; exit 2; }
rows=$(gh api --paginate "repos/$R/commits/$sha/check-runs?per_page=100" \
  --jq '.check_runs[]|{n:.name,t:(.started_at//""),c:(.conclusion//"")}' 2>/dev/null) || { echo "ERR api"; exit 1; }
# 2026-11-14: a CANCELLED check run whose name still carries an unexpanded "${{ ... }}" is a matrix placeholder of a
# superseded run (e.g. the draft-time pipeline replaced when a train is marked ready). It never ran and is not a
# failure; the real shards report under their expanded names. Any other cancelled run still counts as a failure.
cr=$(jq -rs '(group_by(.n)|map(max_by(.t))) as $l
  | "\([$l[]|select(.c!="" and (.c|IN("success","skipped","neutral")|not) and ((.c=="cancelled" and (.n|contains("${{")))|not))]|length) \([$l[]|select(.c=="")]|length)"' <<< "$rows") || { echo "ERR parse"; exit 1; }
read -r fail pend <<< "$cr"
runs=$(gh api --paginate "repos/$R/actions/runs?head_sha=$sha&per_page=100" --jq '.workflow_runs[]|select(.status!="completed")|.id' 2>/dev/null) || { echo "ERR api"; exit 1; }
rnp=0; [ -n "$runs" ] && rnp=$(grep -c . <<< "$runs")
[ "$rnp" -gt "$pend" ] && pend=$rnp
ctx=$(gh api "repos/$R/branches/main/protection/required_status_checks" -q '.contexts[]' 2>/dev/null) || { echo "ERR api"; exit 1; }
miss=0; names=$(jq -rs '.[].n' <<< "$rows" 2>/dev/null)
while IFS= read -r c; do [ -n "$c" ] && ! grep -qxF -- "$c" <<< "$names" && miss=$((miss+1)); done <<< "$ctx"
if [ "$miss" -gt 0 ]; then
  gate=0; [ "$rnp" -gt 0 ] && gate=1
  if [ "$gate" = 0 ]; then
    cd=$(gh api "repos/$R/commits/$sha" --jq .commit.committer.date 2>/dev/null) || { echo "ERR api"; exit 1; }
    age=$(( $(date +%s) - $(date -d "$cd" +%s 2>/dev/null || echo 0) )); [ "$age" -lt 1200 ] && gate=1
  fi
  [ "$gate" = 1 ] && [ "$miss" -gt "$pend" ] && pend=$miss
fi
#  (d) 2026-11-13: a named slow NON-required job must not hold a green head (test-durations ran 70+ min on a train whose
#      11 required contexts were green). When fail=0, no required context is missing, and EVERY still-pending check run
#      and workflow run is on the allow-list below and is not a required context, pending is reported as 0. The
#      allow-list is by exact name; anything else pending still blocks.
NB_CHECKS=${REST_LATEST_NONBLOCKING_CHECKS:-"Measure per-test durations"}
NB_RUNS=${REST_LATEST_NONBLOCKING_RUNS:-"test-durations"}
if [ "$fail" = 0 ] && [ "$pend" -gt 0 ] && [ "$miss" = 0 ]; then
  pc=$(jq -rs '(group_by(.n)|map(max_by(.t)))[]|select(.c=="")|.n' <<< "$rows" 2>/dev/null)
  pr=$(gh api --paginate "repos/$R/actions/runs?head_sha=$sha&per_page=100" --jq '.workflow_runs[]|select(.status!="completed")|.name' 2>/dev/null) || { echo "ERR api"; exit 1; }
  ok=1
  while IFS= read -r n; do [ -z "$n" ] && continue; grep -qxF -- "$n" <<< "$NB_CHECKS" || ok=0; grep -qxF -- "$n" <<< "$ctx" && ok=0; done <<< "$pc"
  while IFS= read -r n; do [ -z "$n" ] && continue; grep -qxF -- "$n" <<< "$NB_RUNS" || ok=0; done <<< "$pr"
  # every required context must have a green latest run, not merely exist
  while IFS= read -r c; do [ -z "$c" ] && continue
    jq -es --arg n "$c" '(group_by(.n)|map(max_by(.t)))[]|select(.n==$n and (.c|IN("success","skipped","neutral")))' <<< "$rows" >/dev/null 2>&1 || ok=0
  done <<< "$ctx"
  [ "$ok" = 1 ] && { echo "$(date +%H:%M) rest_latest: only non-blocking jobs pending ($(tr '\n' ',' <<< "$pc$pr")) -> pending=0" >&2; pend=0; }
fi
echo "fail=$fail pending=$pend"
