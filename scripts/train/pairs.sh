#!/bin/bash
# Usage: pairs.sh OUT "A B" ... — for each pair, merge A onto main (list/ratchet conflicts take main), then list B's conflicts against that.
S="${TRAIN_WORK:-$HOME/.claude/state/train/work}"; mkdir -p "$S"; D="$(cd "$(dirname "$0")" && pwd)"; OUT=$1; shift
W=$S/clashwt; cd "${AUTOBOT_REPO:-$HOME/AutoBot-Ai/AutoBot-AI}" || exit 1
[ -d "$W" ] || git worktree add -q --detach "$W" origin/main 2>/dev/null
cd "$W" || exit 1; : > "$OUT"
for pr in "$@"; do
  set -- $pr; A=$1; B=$2
  git checkout -q -f --detach origin/main; git clean -qfd >/dev/null
  if ! git -c core.hooksPath=/dev/null merge -q --no-ff --no-edit $(~/.claude/scripts/pr-sha $A) >/dev/null 2>&1; then
    u=$(git diff --name-only --diff-filter=U); for f in $u; do git checkout -q --ours -- "$f"; git add "$f"; done
    git -c core.hooksPath=/dev/null commit -q --no-edit >/dev/null 2>&1 || { echo -e "$A>$B\tA-MERGE-FAIL" >> "$OUT"; continue; }
  fi
  echo -e "$A>$B\t$(python3 $D/mt_conflicts.py HEAD $(~/.claude/scripts/pr-sha $B))" >> "$OUT"
done
git checkout -q -f --detach origin/main
