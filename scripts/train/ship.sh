#!/bin/bash
# Usage: ship.sh WORKTREE BRANCH "TITLE" BODY LABEL [WAIT_FILE]
# Pre-check, repin and push a train, then open it, hold its slot and arm the watcher.
export AUTOBOT_MACHINE_SLOTS=2  # shared 2-slot machine queue with session pushes (#21098)
W=$1; BR=$2; TITLE=$3; BODY=$4; LABEL=$5; WAIT=$6
L=~/.claude/scripts/ledger; PY=${AUTOBOT_REPO:-$HOME/AutoBot-Ai/AutoBot-AI}/venv/bin/python
S="${TRAIN_WORK:-$HOME/.claude/state/train/work}"; D="$(cd "$(dirname "$0")" && pwd)"; TRAIN_STATE="${TRAIN_STATE:-$HOME/.claude/state/train}"; mkdir -p "$S"
R=mrveiss/AutoBot-AI
G='workflow_concurrency_guard|enum_union_guard|access_control_enforcement_provisioning|router_auth_coverage|isolated_git_env_guard_18940|test_durations_represent_the_tree_17886|docstring_restatement_guard_17165|audit_action_vocabulary_18716|reach_floor_migration|ceiling_record_parity_17872|one_claim_registry_16653|guard_reach_floor_window_17818|one_comment_stripper_17941|kb_read_visibility_guard|embedding_model_one_resolver_19377|glob_declared_reads_15900|one_repo_root_spelling_15925|workflow_planner_deprecation|python_file_size_ratchet|env_var_bare_cast|uninstall_covers_role_packages_18653|no_tracked_key_material|threat_model_anchors_resolve|reach_roots_record_18808|reach_scope_claim_17844|raw_palette_class_ratchet_14580|kit_loading_ratchet|kit_export_shadow|changes_job_equivalence_15360|source_scoping_guard_17758|i18n_untranslated_ratchet|frontend_file_size|frontend_fragmentation|duplicate_names_ratchet|local_date|conftest_stub_no_autovivify|fixed_sleep_then_call_assertion|unconnected_code_gate|inline_lazy_singleton|parse_cache_test|env_registry_is_extensible|prepush_stages'
cd "$W" || exit 1
# A train member's merge must change files and its own lines must survive.
python3 "$D/lostcheck.py" --at-merge HEAD "origin/main..HEAD" > "$S/lost_$BR.txt"; cut -c1-160 "$S/lost_$BR.txt"
if grep -vE "${LOST_OK:-^$}" "$S/lost_$BR.txt" | grep -qE '^EMPTY|low_survival=[1-9]'; then echo "LOST-WORK: not pushing"; exit 1; fi
if [ -n "$WAIT" ]; then until grep -q 'push rc' "$WAIT"; do sleep 60; done; fi
until $L hold machine:heavy-run "$LABEL pre-check" --ttl 40m 2>&1 | head -1 | grep -q '^HOLD'; do sleep 60; done
$PY scripts/repin_reach_floors.py 2>&1 | grep -E '^PIN' | cut -c1-90
$PY "$D/repin_named.py" 2>/dev/null | grep -E '^PIN' | cut -c1-90
F="$(ls repo_tests/ | grep -E "$G" | grep -v '^_' | sed 's#^#repo_tests/#') autobot_shared/node_proxy_test.py"
$PY -m pytest -q --no-header -p no:cacheprovider $F 2>&1 | grep -E '^(FAILED|ERROR)|^E +Assert|passed|failed' | cut -c1-320 | head -12 | tee "$S/$LABEL.g"
$L unhold machine:heavy-run | head -1
~/.venv-python-suite/bin/python scripts/lift_locale_translations.py --app autobot-slm-frontend/src/locales 2>&1 | tail -1 | cut -c1-80
grep -qE '^(FAILED|ERROR)' "$S/$LABEL.g" && { echo GUARDS-RED; exit 1; }
# The train-content gate CI runs: merge subjects, member content, declared drops (caught locally, not after an hour of CI).
~/.venv-python-suite/bin/python pipeline-scripts/train_content_gate.py --range "origin/main..HEAD" --title "$TITLE" --body "$(cat "$BODY")" > "$S/$LABEL.tc" 2>&1 || { tail -5 "$S/$LABEL.tc" | cut -c1-200; echo TRAIN-CONTENT-RED; exit 1; }
# One alembic head on the merged tree (#15899): two members off one parent pass alone, fail together (T96).
heads=$(cd autobot-backend && PYTHONPATH=.:.. ~/.venv-python-suite/bin/python -c "from alembic.script import ScriptDirectory; print(len(ScriptDirectory(\"migrations\").get_heads()))" 2>&1 | tail -1); [ "$heads" = 1 ] || { echo "ALEMBIC-HEADS=$heads: re-chain a member migration"; exit 1; }
# Duplication pins are exact (#20294): measure every scope the way CI does, before the push (T98 lost a CI run to +24 clones).
bash "$D/dup_precheck.sh" "$W" > "$S/$LABEL.dup" 2>&1 || { grep -E 'DUP-OVER|OVER BY|measured|pin:' "$S/$LABEL.dup" | head -8; echo DUP-OVER; exit 1; }
if [ -n "$(git status --short)" ]; then
  m="fix(train): reach floors return to mid-window on the merged tree (#${ISSUE:-17844})"
  git add -u; git commit -q -m "$m" >"$S/c.log" 2>&1 || { git add -u; git commit -q -m "$m" >"$S/c.log" 2>&1 || { grep -E 'Failed$' "$S/c.log" | cut -c1-80; exit 1; }; }
fi
git fetch -q origin main 2>/dev/null
H=$(git rev-parse HEAD); n=$(git diff --name-only origin/main...HEAD | wc -l)
echo "behind=$(git rev-list --count HEAD..origin/main) files=$n"
[ "$n" -le 100 ] || { echo OVER-LIMIT; exit 1; }
[ "$(git branch --show-current)" = "$BR" ] || { echo "WRONG-BRANCH: $(git branch --show-current) is checked out, not $BR"; exit 1; }
# Slot gate (owner: 3 CI slots): never push a 4th train. Count admitted branches other than this one.
used=$(grep -vx "$BR" "$TRAIN_STATE/ci-admitted.txt" 2>/dev/null | grep -c .); [ "$used" -lt 3 ] || { echo "SLOTS-FULL: $used admitted, not pushing $BR"; exit 1; }
# Admit the train to a CI slot BEFORE its first push, or ci-enforce cancels its runs (T96 08:01).
A="$TRAIN_STATE/ci-admitted.txt"; grep -qx "$BR" "$A" || echo "$BR" >> "$A"
git push origin "$H:refs/heads/$BR" >"$S/$LABEL.p" 2>&1; rc=$?
echo "push rc=$rc $H"; grep -E 'FAIL|STALE' "$S/$LABEL.p" | cut -c1-220
[ $rc = 0 ] || exit 1
N=$(gh pr list --repo $R --head "$BR" --state open --json number -q ".[0].number")
if [ -n "$N" ]; then gh pr edit "$N" --repo $R --title "$TITLE" --body-file "$BODY" >/dev/null; echo "updated #$N"; else
U=$(gh pr create --repo $R --base main --head "$BR" --title "$TITLE" --body-file "$BODY"); echo "$U"; N=${U##*/}
fi
$L hold ci-slot:$N "$LABEL" --ttl 24h | head -1
[ -n "$NO_AUTOMERGE" ] && { echo "HELD: no automerge for #$N"; exit 0; }
"$D/land_when_green.sh" "$N"
