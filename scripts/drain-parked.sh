#!/usr/bin/env bash
# drain-parked.sh — rank worktree branches that hold unlanded commits.
#
# Parallel agents produce concurrently and merge serially, so finished work
# accumulates on branches nobody returns to. A parked branch is not debris: it
# is work already paid for that returns nothing until it lands. This ranks what
# to land next, cheapest first — it never deletes, rebases, or pushes anything.
#
#   (default)   ranked table of branches with commits ahead of the base
#   --json      same data as JSON
#   --top N     only the N best candidates (default 20)
#
# Cheapest first = fewest commits, no PR yet, and a clean rebase onto the base.

set -uo pipefail

BASE="${DRAIN_BASE:-}"
TOP=20
FORMAT=table

while [ $# -gt 0 ]; do
  case "$1" in
    --json)  FORMAT=json; shift ;;
    --top)   TOP="${2:-20}"; shift 2 ;;
    --base)  BASE="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

git rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git repo" >&2; exit 1; }

# The base is the branch PRs target, which is not necessarily the remote HEAD.
if [ -z "$BASE" ]; then
  BASE=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null)
  for candidate in develop main master Dev_new_gui "$BASE"; do
    if git rev-parse --verify --quiet "origin/$candidate" >/dev/null 2>&1; then
      BASE="origin/$candidate"; break
    fi
  done
fi
git rev-parse --verify --quiet "$BASE" >/dev/null 2>&1 || { echo "base '$BASE' not found" >&2; exit 1; }

# Branches that currently have a PR, so a parked branch is not double-counted.
OPEN_PRS=$(gh pr list --state open --limit 200 --json headRefName -q '.[].headRefName' 2>/dev/null | sort -u)
MERGED_PRS=$(gh pr list --state merged --limit 400 --json headRefName -q '.[].headRefName' 2>/dev/null | sort -u)
CLOSED_PRS=$(gh pr list --state closed --limit 400 --json headRefName -q '.[].headRefName' 2>/dev/null | sort -u)

rows=""
while IFS= read -r line; do
  branch="${line#branch refs/heads/}"
  [ "$branch" = "$line" ] && continue
  git merge-base --is-ancestor "$branch" "$BASE" 2>/dev/null && continue

  ahead=$(git rev-list --count "$BASE".."$branch" 2>/dev/null || echo 0)
  [ "$ahead" -gt 0 ] 2>/dev/null || continue

  last=$(git log -1 --format=%cs "$branch" 2>/dev/null)
  age=$(( ( $(date +%s) - $(git log -1 --format=%ct "$branch" 2>/dev/null || date +%s) ) / 86400 ))

  if printf '%s\n' "$OPEN_PRS" | grep -qx -- "$branch"; then pr="open"
  elif printf '%s\n' "$MERGED_PRS" | grep -qx -- "$branch"; then pr="merged"
  elif printf '%s\n' "$CLOSED_PRS" | grep -qx -- "$branch"; then pr="closed"
  else pr="none"; fi

  # Conflict risk, without git>=2.38's merge-tree: count the files this branch
  # touched that the base has also moved since they diverged.
  mb=$(git merge-base "$BASE" "$branch" 2>/dev/null)
  if [ -n "$mb" ]; then
    overlap=$(comm -12 \
      <(git diff --name-only "$mb".."$branch" 2>/dev/null | sort -u) \
      <(git diff --name-only "$mb".."$BASE"   2>/dev/null | sort -u) | wc -l)
  else
    overlap=0
  fi

  # Lower score = land this sooner.
  # A branch whose PR already merged is a rebase leftover, not parked work.
  [ "$pr" = "merged" ] && continue

  score=$(( ahead + overlap ))
  [ "$pr" = "open" ] && score=$(( score - 100 ))
  [ "$pr" = "none" ] && score=$(( score + 10 ))

  rows+="$score|$branch|$ahead|$pr|$overlap|$last|$age"$'\n'
done < <(git worktree list --porcelain 2>/dev/null | grep '^branch ')

rows=$(printf '%s' "$rows" | grep -v '^$' | sort -t'|' -k1,1n | head -n "$TOP")

if [ -z "$rows" ]; then
  echo "No parked branches: every worktree branch is merged into $BASE."
  exit 0
fi

total=$(printf '%s\n' "$rows" | awk -F'|' '{s+=$3} END {print s+0}')

if [ "$FORMAT" = "json" ]; then
  printf '%s\n' "$rows" | awk -F'|' 'BEGIN{print "["; sep=""} {printf "%s  {\"branch\":\"%s\",\"commits\":%s,\"pr\":\"%s\",\"files_also_moved_on_base\":%s,\"last_commit\":\"%s\",\"age_days\":%s}\n", sep, $2, $3, $4, $5, $6, $7; sep=","} END{print "]"}'
  exit 0
fi

printf '%-46s %8s %8s %8s %12s %6s\n' BRANCH COMMITS PR OVERLAP LAST AGE
printf '%-46s %8s %8s %8s %12s %6s\n' "----------------------------------------------" -------- -------- -------- ------------ ------
printf '%s\n' "$rows" | awk -F'|' '{printf "%-46s %8s %8s %8s %12s %5sd\n", $2, $3, $4, $5, $6, $7}'
echo
echo "$(printf '%s\n' "$rows" | wc -l) branches shown, $total unlanded commits."
echo "Land the top row first: it is the cheapest finished work still earning nothing."
