#!/bin/bash
# Usage: realmerge.sh BASE_REF PR — real git merge of a PR head onto BASE_REF in the scratch worktree; prints merge-base count and conflicted files.
W="${TRAIN_WORK:-$HOME/.claude/state/train/work}/clashwt"
cd "$W" || exit 1
git checkout -q -f --detach "$1"
echo "merge-bases=$(git merge-base --all HEAD $(~/.claude/scripts/pr-sha $2) | wc -l)"
git -c core.hooksPath=/dev/null merge --no-ff --no-edit $(~/.claude/scripts/pr-sha $2) >/dev/null 2>&1; echo "merge rc=$?"
git diff --name-only --diff-filter=U
git merge --abort 2>/dev/null; git checkout -q -f --detach origin/main
