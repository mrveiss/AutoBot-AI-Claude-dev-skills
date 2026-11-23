#!/usr/bin/env bash
# preflight.sh — run INSIDE a train worktree before pushing. Catches the failures that keep
# costing a full CI round on merged trains (owner 2026-10-24): stale reach floors/records,
# job-hash drift, filter coverage, hand-rolled fakes, ratchets, semgrep, hardcoded baseline.
# Not the full suite (owner ban). Holds machine:heavy-run for the test part. Exit 0 = clean.
set -u
L="$HOME/.claude/scripts/ledger"
PY="${PREFLIGHT_PY:-$HOME/.venv-python-suite/bin/python}"
root=$(git rev-parse --show-toplevel) || exit 2
cd "$root" || exit 2
base=$(git merge-base HEAD origin/main)
fail=0

echo "== preflight on $(git rev-parse --abbrev-ref HEAD) @ $(git rev-parse --short=10 HEAD) (base ${base:0:10})"

until "$L" hold machine:heavy-run "train preflight $(basename "$root")" --ttl 20m >/dev/null 2>&1; do
  echo "   waiting for machine:heavy-run ..."; sleep 30
done
trap '"$L" unhold machine:heavy-run >/dev/null 2>&1' EXIT

echo "== 1/7 reach floors (repin --check)"
"$PY" scripts/repin_reach_floors.py --check 2>&1 | grep -E '^(STALE|PIN|OK)' | head -20
# exit 2 = some guard modules not importable locally (expected); stale floors print STALE/PIN.
if "$PY" scripts/repin_reach_floors.py --check 2>&1 | grep -qE '^(STALE|PIN)'; then
  echo "   FIX: python3 scripts/repin_reach_floors.py && commit"; fail=1
fi

echo "== 2/7 record / equivalence / ratchet guards"
tests=(
  repo_tests/reach_declarations_test.py repo_tests/reach_roots_record_18808_test.py
  repo_tests/reach_scope_claim_17844_test.py repo_tests/guard_reach_meta_test.py
  repo_tests/changes_job_equivalence_15360_test.py repo_tests/python_filter_covers_its_guards_test.py
  repo_tests/one_fake_async_session_18883_test.py repo_tests/one_git_enumeration_15926_test.py
  repo_tests/frontend_file_size_ratchet_test.py repo_tests/frontend_fragmentation_ratchet_test.py
  repo_tests/i18n_untranslated_ratchet_test.py repo_tests/hardcoded_ui_literal_ratchet_12732_test.py
  repo_tests/threat_model_anchors_resolve_test.py scripts/check_nosec_format_test.py
  repo_tests/symbol_fork_ratchet_17312_test.py repo_tests/frontend_api_contract_ratchet_test.py
  repo_tests/migration_gate_filter_covers_what_its_tests_import_test.py
)
present=(); for t in "${tests[@]}"; do [ -f "$t" ] && present+=("$t"); done
"$PY" -m pytest -q -p no:cacheprovider -n 4 --tb=line "${present[@]}" 2>&1 | tail -15
[ "${PIPESTATUS[0]}" -eq 0 ] || fail=1

echo "== 3/7 tests changed by the train (python, *_test.py / test_*.py)"
changed_tests=$(git diff --name-only "$base"...HEAD -- '*_test.py' '*/test_*.py' | while read -r f; do [ -f "$f" ] && echo "$f"; done)
if [ -n "$changed_tests" ]; then
  # repo_tests and autobot-backend share one interpreter; slm runs from its own dir (pytest.ini #13084)
  rt=$(echo "$changed_tests" | grep -v '^autobot-slm-backend/' || true)
  st=$(echo "$changed_tests" | grep '^autobot-slm-backend/' | sed 's#^autobot-slm-backend/##' || true)
  [ -n "$rt" ] && { "$PY" -m pytest -q -p no:cacheprovider -n 4 --tb=line $rt 2>&1 | tail -6; [ "${PIPESTATUS[0]}" -eq 0 ] || fail=1; }
  [ -n "$st" ] && { (cd autobot-slm-backend && "$PY" -m pytest -q -p no:cacheprovider --tb=line $st) 2>&1 | tail -6; [ "${PIPESTATUS[0]}" -eq 0 ] || fail=1; }
else echo "   none"; fi

echo "== 4/7 semgrep (repo rules, changed python files)"
changed_py=$(git diff --name-only --diff-filter=AM "$base"...HEAD -- '*.py')
if [ -n "$changed_py" ] && command -v semgrep >/dev/null; then
  # --baseline-commit: only findings the train ADDS (a touched file keeps its pre-existing ones, as CI does)
  out=$(semgrep --config .semgrep/rules.yaml --error --quiet --baseline-commit "$base" $changed_py 2>&1); rc=$?
  [ $rc -eq 0 ] && echo "   clean" || { echo "$out" | head -20; fail=1; }
else echo "   skipped (no changed python or semgrep missing)"; fi

echo "== 5/7 hardcoded-values baseline"
if [ -x ./pipeline-scripts/detect-hardcoded-values.sh ]; then
  ./pipeline-scripts/detect-hardcoded-values.sh --prune-baseline >/dev/null 2>&1
  if ! git diff --quiet -- pipeline-scripts/hardcoded_values_baseline.txt; then
    echo "   baseline pruned (stale keys) — review and commit pipeline-scripts/hardcoded_values_baseline.txt"; fail=1
  else echo "   clean"; fi
fi

echo "== 6/7 flake8 on files the train changed (a hook failure otherwise only appears at commit time)"
py_changed=$( { git diff --name-only "$base"...HEAD -- '*.py'; git diff --name-only -- '*.py'; git diff --cached --name-only -- '*.py'; } | sort -u | while read -r f; do [ -f "$f" ] && echo "$f"; done)
if [ -n "$py_changed" ]; then
  fl=$("$PY" -m flake8 --config=.flake8 $py_changed 2>&1); frc=$?
  [ $frc -eq 0 ] && echo "   clean ($(printf '%s\n' "$py_changed" | wc -l) files)" || { echo "$fl" | head -10; fail=1; }
else echo "   no changed .py files"; fi

echo "== 7/7 generated-types risk (static; CI's autofix-types is authoritative)"
api_changed=$(git diff --name-only "$base"...HEAD -- 'autobot-backend/api/*.py' 'autobot-backend/**/schemas*.py' 'autobot-slm-backend/api/*.py' | wc -l)
ts_changed=$(git diff --name-only "$base"...HEAD -- '*types/generated/api.ts' 'autobot-slm-frontend/openapi.json' | wc -l)
echo "   route/schema files changed: $api_changed; generated files changed: $ts_changed"

echo "== NOT covered locally: generated api.ts (needs CI deps), docker smoke (needs Docker)."
[ $fail -eq 0 ] && echo "PREFLIGHT: CLEAN" || echo "PREFLIGHT: FIX ABOVE BEFORE PUSHING"
exit $fail
