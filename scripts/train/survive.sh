#!/usr/bin/env bash
# survive.sh <pr>... : report member added lines missing from the working tree
S="${TRAIN_WORK:-$HOME/.claude/state/train/work}"; mkdir -p "$S"; D="$(cd "$(dirname "$0")" && pwd)"
for n in "$@"; do miss=0; c=$(~/.claude/scripts/pr-sha $n) || continue
  for f in $(git diff --name-only origin/main...$c); do [ -f "$f" ] || continue
    git diff -U0 origin/main...$c -- "$f" | grep '^+[^+]' | sed 's/^+//' | grep -v '^\s*$' | sort -u > $S/add.txt
    while IFS= read -r l; do grep -qF -- "$l" "$f" || { miss=$((miss+1)); echo "  #$n $f: ${l:0:110}"; }; done < $S/add.txt
  done; echo "#$n missing=$miss"; done
