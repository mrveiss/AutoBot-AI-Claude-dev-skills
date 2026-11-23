#!/bin/bash
# Usage: sync_pr.sh PR:BRANCH[:main] ...  Merge main into each PR branch. Floor conflicts take main's value;
# ":main" takes main's side in every conflict. Non-mechanical conflicts stop that PR. Repins, then pushes.
S="${TRAIN_WORK:-$HOME/.claude/state/train/work}"; mkdir -p "$S"; D="$(cd "$(dirname "$0")" && pwd)"
L=~/.claude/scripts/ledger; PY=${AUTOBOT_REPO:-$HOME/AutoBot-Ai/AutoBot-AI}/venv/bin/python
cd ${SYNC_W:?set SYNC_W to the sync worktree} || exit 1
commit(){ git add -u; git commit -q -m "$1" >"$S/c.log" 2>&1 || { git add -u; git commit -q -m "$1" >"$S/c.log" 2>&1 || { grep -E 'Failed$' -A6 "$S/c.log" | cut -c1-160; return 1; }; }; }
floors_only(){ awk '/^<<<<<<< /{p=1;next} /^=======$/{next} /^>>>>>>> /{p=0;next} p' "$1" | grep -vE '^\s*floor=' | grep -q . && return 1; return 0; }
for x in "$@"; do
  IFS=: read -r p b mode <<<"$x"
  git merge --abort 2>/dev/null; git fetch -q origin 2>/dev/null
  git checkout -q -f --detach "origin/$b" || { echo "$p no branch"; continue; }
  before=$(git rev-parse --short=10 HEAD); m="Merge main into the branch (#$p)"; stop=
  if ! git merge -q --no-edit -m "$m" origin/main >"$S/s.log" 2>&1; then
    git status --short | grep -E '^(UU|AA|DU|UD)' > "$S/c_$p.txt"
    [ -s "$S/c_$p.txt" ] || { grep -E 'Failed$' -A5 "$S/s.log" | cut -c1-150; }
    while read -r st f; do
      case "$st$mode" in
        UDmain) git rm -q -- "$f";;
        *main) git checkout --theirs -- "$f"; git add -- "$f";;
        UU) if floors_only "$f" || [[ "$f" == *_known_large.py ]]; then git checkout --theirs -- "$f"; git add -- "$f"; else echo "$p NONMECHANICAL $f"; stop=1; fi;;
        *) echo "$p NONMECHANICAL $st $f"; stop=1;;
      esac
    done < "$S/c_$p.txt"
    if [ -n "$stop" ]; then git merge --abort; continue; fi
    commit "$m" || { echo "$p STOP hook"; git merge --abort 2>/dev/null; continue; }
  fi
  if [ "$mode" != main ]; then
    until $L hold machine:heavy-run "sync $p repin" --ttl 20m 2>&1 | head -1 | grep -q '^HOLD'; do sleep 60; done
    $PY scripts/repin_reach_floors.py 2>&1 | grep -cE '^PIN' | sed "s/^/$p pins: /"; $L unhold machine:heavy-run >/dev/null
    python3 scripts/lift_locale_translations.py --app autobot-slm-frontend/src/locales >/dev/null 2>&1
    if [ -n "$(git status --short)" ]; then commit "chore(guards): reach floors on the merged tree (#$p)" || { echo "$p STOP repin commit"; continue; }; fi
  fi
  echo "$p vs main: $(git diff --name-only origin/main HEAD | wc -l) files; PR changes: $(git diff --name-only origin/main...HEAD | wc -l)"
  H=$(git rev-parse HEAD); git fetch -q origin 2>/dev/null
  [ "$(git rev-parse "origin/$b" | cut -c1-10)" = "$before" ] || { echo "$p branch moved while merging; rerun"; continue; }
  git push origin "$H:refs/heads/$b" >"$S/s_$p.p" 2>&1; rc=$?; echo "$p $before -> ${H:0:10} push rc=$rc"
  grep -E 'FAIL|STALE|rejected|cannot lock' "$S/s_$p.p" | cut -c1-220
done
echo ALLDONE
