#!/bin/bash
# Usage: next_train.sh BRANCH LABEL ISSUE "THINKING" pr pr ...  Build on current main in the shared worktree, then ship.
# TRAIN_CONTINUE=1 [PREV="sha:pr ..."]: add members to the branch already checked out instead of creating it.
# TRAIN_RATCHET_THEIRS="pr ...": for these PRs the i18n ratchet conflict takes THEIR side (default: ours).
~/.claude/scripts/ledger claim task trainmaster --ttl 4h >/dev/null 2>&1
S="${TRAIN_WORK:-$HOME/.claude/state/train/work}"; mkdir -p "$S"; D="$(cd "$(dirname "$0")" && pwd)"
R=mrveiss/AutoBot-AI; W=${TRAIN_W:-${TRAIN_W:?set TRAIN_W to the train worktree}}
BR=$1; LABEL=$2; ISSUE=$3; THINK=$4; shift 4
cd "$W" || exit 1
git fetch -q origin 2>/dev/null
if [ -n "$TRAIN_CONTINUE" ]; then [ "$(git branch --show-current)" = "$BR" ] || exit 1; M="$PREV"
else git checkout -q -f -b "$BR" origin/main || exit 1; M=""; fi
for p in "$@"; do
  case " $REVIEW_OK " in *" $p "*) ;; *) python3 "$D/reviewed_head.py" "$p" || { echo "$p NOT-CLEARED STOP"; exit 1; };; esac
  h=$(gh pr view "$p" --repo $R --json headRefOid -q .headRefOid | cut -c1-10)
  git fetch -q origin "pull/$p/head" 2>/dev/null
  m="Merge #$p @ $h into the merge train"
  if git merge -q --no-ff -m "$m" "$h" >"$S/$LABEL.log" 2>&1; then echo "$p clean"
  else
    u=$(git status --short | grep -E '^(UU|AA|DU|UD)')
    if [ -z "$u" ]; then tail -6 "$S/$LABEL.log" | cut -c1-140; echo "$p HOOK-NOT-CONFLICT STOP"; exit 1; fi
    echo "$u" | cut -c1-80
    F=repo_tests/i18n_untranslated_ratchet_test.py
    if echo "$u" | grep -q "$F"; then
      if case " $TRAIN_RATCHET_THEIRS " in *" $p "*) true;; *) false;; esac; then git checkout --theirs -- "$F"; else git checkout --ours -- "$F"; fi; git add "$F"
      u=$(git status --short | grep -E '^(UU|AA|DU|UD)')
    fi
    python3 "$D/res_union.py" | cut -c1-90; git add docs/developer/ENV_VARS.md 2>/dev/null; git status --short | grep -E '^(UU|AA)' | grep -vE 'env_registry_|ENV_VARS' >/dev/null && u=$(git status --short | grep -E '^(UU|AA|DU|UD)' | grep -vE 'env_registry_|ENV_VARS') || u=""
    [ -z "$u" ] || python3 "$D/res_conflicts.py" || { echo "$p STOP"; exit 1; }
    git add -u
    git commit -q -m "$m" >"$S/$LABEL.log" 2>&1 || { git add -u; git commit -q -m "$m" >"$S/$LABEL.log" 2>&1 || { tail -5 "$S/$LABEL.log" | cut -c1-140; exit 1; }; }
    echo "$p floors"
  fi
  [ -n "$(git diff --name-only HEAD^1 HEAD)" ] || { echo "$p EMPTY-MERGE STOP"; exit 1; }
  M="$M $h:$p"
done
n=$(git diff --name-only origin/main...HEAD | wc -l); echo "files=$n"
[ "$n" -le 95 ] || { echo OVER; exit 1; }
bash "$D/mk_body.sh" "$S/${LABEL}_body.md" "$THINK" "$n files, under the 100-file limit. Oldest first among approved PRs with no conflict and no open thread." $M
ISSUE=$ISSUE bash "$D/ship.sh" "$W" "$BR" "chore(merge-train):$(for x in $M; do printf ' #%s' "${x#*:}"; done)" "$S/${LABEL}_body.md" "$LABEL"
