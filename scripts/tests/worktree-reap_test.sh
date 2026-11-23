#!/usr/bin/env bash
# Regression test for worktree-reap.sh counters (#17862).
#
# The reaper once printed "reapable/reaped: 2" while removing nothing: one
# counter covered a verdict and a removal, a status pass did not say it was one,
# and on the merge-only path a refused or skipped removal was counted as done.
# Each case builds a throwaway repo with a bare origin, runs the real script,
# and checks the summary counters against what is actually left on disk.
#
# Isolation: HOME points at a temp dir (no ledger is found) and a fake `gh` sits
# first on PATH -- FAKE_GH=fail makes the open-PR lookup fail (the reaper must
# then keep the worktree), anything else reports no open PR.
set -uo pipefail

REAPER="${REAPER:-$HOME/.claude/scripts/worktree-reap.sh}"
fails=0

setup() {
  T="$(mktemp -d)"
  export HOME="$T/home"; mkdir -p "$HOME" "$T/bin"
  printf '#!/bin/sh\n[ "${FAKE_GH:-}" = fail ] && exit 1\nexit 0\n' >"$T/bin/gh"; chmod +x "$T/bin/gh"
  export PATH="$T/bin:$PATH"
  git init -q --bare "$T/origin.git"
  git init -q -b main "$T/repo"; cd "$T/repo" || exit 1
  git config user.email t@t; git config user.name t
  git commit -q --allow-empty -m base; git remote add origin "$T/origin.git"; git push -q -u origin main
  git worktree add -q .worktrees/issue-1 -b issue-1
  git -C .worktrees/issue-1 commit -q --allow-empty -m work
  git -C .worktrees/issue-1 push -q -u origin issue-1
  git fetch -q origin
}

# Main moves on, and the worktree takes a refresh merge it never pushed: the
# "unpushed, but nothing original" path where removals were miscounted.
merge_only() {
  git commit -q --allow-empty -m "main moves" && git push -q origin main && git fetch -q origin
  git -C .worktrees/issue-1 merge -q --no-edit origin/main
}

run() { REAP_IDLE_HOURS=0 REAP_REPO="$T/repo" bash "$REAPER" "$@" 2>&1; }

check() {  # name, output, expected summary fragment, expect worktree present (yes/no)
  local name="$1" out="$2" want="$3" present="$4" have=no
  [ -d "$T/repo/.worktrees/issue-1" ] && have=yes
  if ! grep -qF -- "$want" <<<"$out" || [ "$have" != "$present" ]; then
    echo "FAIL $name: want '$want', worktree present=$present (was $have)"; echo "$out" | sed 's/^/    /'
    fails=$((fails + 1))
  else
    echo "ok   $name"
  fi
}

cleanup() { cd / && rm -rf "$T"; }

setup; out="$(run)"
check "status pass removes nothing and says so" "$out" "removed: 0   reapable, not removed: 1" yes
grep -q "NOTHING is removed" <<<"$out" || { echo "FAIL status pass does not name its mode"; fails=$((fails + 1)); }
cleanup

setup; out="$(FAKE_GH=fail run reap)"
check "protected worktree is kept, not counted removed" "$out" "removed: 0" yes
cleanup

setup; out="$(run reap)"
check "reap removes and counts it" "$out" "removed: 1   reapable, not removed: 0   refused: 0" no
cleanup

setup; git worktree lock .worktrees/issue-1; out="$(run reap)"
check "a refused removal is reported, not counted" "$out" "removed: 0   reapable, not removed: 0   refused: 1" yes
grep -q "^REFUSED" <<<"$out" || { echo "FAIL refused row missing"; fails=$((fails + 1)); }
cleanup

setup; merge_only; git worktree lock .worktrees/issue-1; out="$(run reap)"
check "merge-only path: refused removal is not counted" "$out" "removed: 0   reapable, not removed: 0   refused: 1" yes
cleanup

setup; merge_only; out="$(FAKE_GH=fail run reap)"
check "merge-only path: protected is kept, not counted" "$out" "removed: 0" yes
cleanup

[ "$fails" -eq 0 ] && echo "all passed" || { echo "$fails failed"; exit 1; }
