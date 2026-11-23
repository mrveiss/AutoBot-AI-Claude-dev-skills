#!/usr/bin/env bash
# shared-failures.sh — owner 2026-10-24: a failure seen on 2+ PRs is a PRIORITY fix.
# Groups the open PRs' failing checks, and inside python-suite shards their FAILED test ids,
# and prints every signature that 2+ PRs share. Cancelled runs are reported apart (parking
# artifact, #17764), never mixed with real failures. Read-only.
set -u
repo=mrveiss/AutoBot-AI
out=$(mktemp -d)
gh pr list -R $repo --state open --limit 200 --json number -q '.[].number' > "$out/prs"
while read -r pr; do
  # conclusion from GitHub itself: `gh pr checks` renders a CANCELLED (parked) job as "fail" (#17764)
  gh pr view "$pr" -R $repo --json statusCheckRollup -q '.statusCheckRollup[]|select(.conclusion=="FAILURE" or .conclusion=="TIMED_OUT" or .state=="FAILURE" or .state=="ERROR")|[(.name//.context),(.detailsUrl//.targetUrl//"")]|@tsv' 2>/dev/null \
    | sed "s/^/$pr\t/" >> "$out/fails"
done < "$out/prs"
[ -s "$out/fails" ] || { echo "no failing checks on $(wc -l < "$out/prs") open PRs"; exit 0; }
# test-level signatures for python-suite shards (one log fetch per failing shard job)
while IFS=$'\t' read -r pr name url; do
  case "$name" in
    "python-suite shard"*)
      job=${url##*/job/}
      gh run view -R $repo --job "$job" --log-failed 2>/dev/null \
        | grep -oE '(FAILED|ERROR) [A-Za-z0-9_./-]+\.py(::[A-Za-z0-9_\[\]./-]+)?' | sort -u \
        | sed "s/^/$pr\t/" >> "$out/tests" ;;
    *) printf '%s\tCHECK %s\n' "$pr" "$name" >> "$out/tests" ;;
  esac
done < "$out/fails"
echo "== signatures failing on 2+ PRs (priority fixes)"
sort -u "$out/tests" | awk -F'\t' '{n[$2]++; p[$2]=p[$2]" #"$1} END{for(k in n) if(n[k]>1) printf "%3d  %s :%s\n", n[k], k, p[k]}' | sort -rn | head -40
echo "== open PRs scanned: $(wc -l < "$out/prs"); failing check rows: $(wc -l < "$out/fails")"
rm -rf "$out"
