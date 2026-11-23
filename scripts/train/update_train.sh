#!/bin/bash
# Usage: update_train.sh WAIT_OUTPUT BRANCH LABEL ISSUE "TITLE" PR NUMBER [sha:pr ...]
# After WAIT_OUTPUT's push finishes: merge main and any new member heads into the train, then ship it.
~/.claude/scripts/ledger claim task trainmaster --ttl 4h >/dev/null 2>&1
S="${TRAIN_WORK:-$HOME/.claude/state/train/work}"; mkdir -p "$S"; D="$(cd "$(dirname "$0")" && pwd)"
W=${TRAIN_W:-${TRAIN_W:?set TRAIN_W to the train worktree}}
WAIT=$1; BR=$2; LABEL=$3; ISSUE=$4; TITLE=$5; PR=$6; shift 6
if [ -n "$WAIT" ]; then
  until grep -qE '^updated #|^HOLD ci-slot|push rc=[1-9]|^GUARDS-RED|^LOST-WORK|^WRONG-BRANCH|^OVER|^STOP|^HOOK' "$WAIT"; do sleep 30; done
  grep -E '^updated #|^HOLD ci-slot|push rc=[1-9]|^GUARDS-RED|^LOST-WORK|^WRONG-BRANCH|^OVER|^STOP|^HOOK' "$WAIT" | tail -1 | cut -c1-90
  sleep 10
fi
cd "$W" || exit 1
git fetch -q origin 2>/dev/null
git checkout -q -f "$BR" || exit 1
git log -1 --format='%h'
mg() {
  if ! git merge -q --no-ff -m "$2" "$1" >"$S/$LABEL.log" 2>&1; then
    u=$(git status --short | grep -E '^(UU|AA|DU|UD)')
    [ -n "$u" ] || { tail -6 "$S/$LABEL.log" | cut -c1-150; echo HOOK; exit 1; }
    echo "$u" | cut -c1-80
    python3 "$D/res_conflicts.py" || { echo "STOP $1"; exit 1; }
    git add -u
    git commit -q -m "$2" >"$S/$LABEL.log" 2>&1 || { git add -u; git commit -q -m "$2" >"$S/$LABEL.log" 2>&1 || { tail -5 "$S/$LABEL.log" | cut -c1-140; exit 1; }; }
  fi
}
[ "$(git rev-list --count HEAD..origin/main)" = 0 ] || mg origin/main "Merge main into the merge train (#$PR)"
for x in "$@"; do
  h=${x%:*}; p=${x#*:}
  case " $REVIEW_OK " in *" $p "*) ;; *) python3 "$D/reviewed_head.py" "$p" "$h" || { echo "$p NOT-CLEARED STOP"; exit 1; };; esac
  git fetch -q origin "pull/$p/head" 2>/dev/null
  mg "$h" "Merge #$p @ $h into the merge train"
  [ -n "$(git diff --name-only HEAD^1 HEAD)" ] || { echo "$p EMPTY"; exit 1; }
done
if [ -n "$TYPES_RUN" ]; then D="$S/p_$LABEL"; rm -rf "$D"; mkdir "$D"; (cd "$D" && gh run download "$TYPES_RUN" --repo mrveiss/AutoBot-AI --pattern '*patch*' >/dev/null 2>&1); P=$(find "$D" -name '*.patch' | head -1); [ -n "$P" ] && { git apply "$P" && echo types_applied || echo types_apply_failed; }; if [ -n "$(git status --short)" ]; then git add -u; m="fix(train): generated types follow the merged API (#$PR)"; git commit -q -m "$m" >"$S/c.log" 2>&1 || { git add -u; git commit -q -m "$m" >"$S/c.log" 2>&1 || { tail -5 "$S/c.log" | cut -c1-140; exit 1; }; }; fi; fi
n=$(git diff --name-only origin/main...HEAD | wc -l); echo "files=$n"
[ "$n" -le 100 ] || { echo OVER; exit 1; }
ISSUE=$ISSUE bash "$D/ship.sh" "$W" "$BR" "$TITLE" "$S/${LABEL}_body.md" "$LABEL"
