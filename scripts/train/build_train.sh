#!/usr/bin/env bash
# build_train.sh <branch> <pr:sha10>...  — merge frozen PR heads --no-ff onto the current branch.
# Fetches each PR head by SHA (pr-sha); creates no refs. Stops at the first conflict (left in place) for manual resolution.
set -u
branch=$1; shift
[ "$(git rev-parse --abbrev-ref HEAD)" = "$branch" ] || { echo "not on $branch"; exit 2; }
git rev-parse -q --verify MERGE_HEAD >/dev/null && { echo "MERGE_HEAD pending; resolve first"; exit 2; }
for spec in "$@"; do
  n=${spec%%:*}; sha=${spec#*:}
  c=$(~/.claude/scripts/pr-sha $n) || { echo "#$n fetch failed"; exit 2; }
  head=$(git rev-parse --short=10 "$c")
  [ "$head" = "$sha" ] || { echo "#$n head moved: $head != $sha"; exit 2; }
  if git merge --no-ff --no-edit -q -m "Merge #$n @ $sha into $branch" "$c" >/dev/null 2>&1; then
    echo "#$n clean $(git rev-parse --short=10 HEAD)"
  else
    u=$(git diff --name-only --diff-filter=U)
    # BUILD_RESOLVE=1: take the mechanical resolutions (floors, size lists, registries); anything else stops.
    if [ -n "${BUILD_RESOLVE:-}" ] && python3 "$(dirname "$0")/res_conflicts.py"; then
      git add $u; git commit -q --no-edit >/dev/null 2>&1 && { echo "#$n resolved: $(echo $u | tr '\n' ' ')"; continue; }
    fi
    echo "#$n CONFLICT: $(echo $u | tr '\n' ' ')"; exit 1
  fi
done
