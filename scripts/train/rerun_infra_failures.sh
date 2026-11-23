#!/bin/bash
# Usage: rerun_infra_failures.sh [--dry-run] [--once] [--no-cancel] PR [MAX_ATTEMPTS=8] [INTERVAL_SECONDS=150]
#        rerun_infra_failures.sh --classify JOB   -- print INFRA|REAL|UNKNOWN for one job and exit
# Reruns (gh run rerun --failed) only runs whose failed jobs at the PR head ALL fail on runner DNS/apt-mirror
# resolution (issue #21325). Never reruns green jobs, never touches other PRs.
# Owner rule 2026-11-11 "PRs become red, cancel immediately": a job classed REAL on TWO consecutive passes (same job id)
# cancels every queued/in-progress run of that head via ~/.claude/scripts/ci-cancel, prints REAL-FAILURE and exits 1; no
# reruns in a pass that found a REAL. 1st pass logs REAL(pending-confirm). INFRA/UNKNOWN never cancel.
# --no-cancel / RERUN_NO_CANCEL=1: report only (old behaviour). --once: report only, never cancels.
# --dry-run prints the cancels it would make (also with --once, as DRY-RUN lines).
# Apt-style first error with no DNS text in the failed step -> the full job log is searched (INFRA(full-log)).
# Runs at attempt>=3 are not rerun until 10 min after that attempt completed (wait(backoff)).
# DONE #PR clean needs pending=0 (shared rest_latest.sh definition) AND all required contexts present+green; else "IDLE #PR: required checks absent" and keep looping.
# Exit: 0 "DONE #PR clean" | 1 "REAL-FAILURE #PR: names" | 2 "ATTEMPTS-EXHAUSTED #PR: names"
R=mrveiss/AutoBot-AI; DRY=0; ONCE=0; NOCANCEL=0; [ "${RERUN_NO_CANCEL:-0}" = 1 ] && NOCANCEL=1; CLS=""; LOGFILE=""; FULLFILE=""; BACKOFF=600
while [ $# -gt 0 ]; do case "$1" in --dry-run) DRY=1; shift;; --once) ONCE=1; shift;; --no-cancel) NOCANCEL=1; shift;; --classify) CLS=$2; shift 2;; --classify-file) LOGFILE=$2; CLS=file; shift 2;; --full-log-file) FULLFILE=$2; shift 2;; *) break;; esac; done
PR=$1; MAXA=${2:-8}; INT=${3:-150}
T=$(mktemp -d "${TMPDIR:-/tmp}/rerun_infra.XXXXXX") || exit 3; trap 'rm -rf "$T"' EXIT
S="$(cd "$(dirname "$0")" && pwd)"; : "$S"
now() { date +%H:%M; }
# ONE list of DNS/name-resolution signatures; add future wordings here only.
DNS_SIGS=("Temporary failure resolving" "Could not resolve '" "Unable to find the server at" "Temporary failure in name resolution" "(HTTP 502)" "(HTTP 503)" "(HTTP 504)")
dns_args=(); for _s in "${DNS_SIGS[@]}"; do dns_args+=(-e "$_s"); done
# ONE list of stall/timeout signatures (ERE): a stalled step is infrastructure unless a REAL signature came earlier -> INFRA(timeout).
# STALL_CANCEL_SIG ("operation was canceled") also needs a silent gap >= STALL_GAP_S in the raw timestamps (else it is just a cancel).
STALL_SIGS=("installer timed out" "has timed out after [0-9]+ minutes" "The job running on runner .* has exceeded the maximum execution time")
STALL_CANCEL_SIG='The operation was canceled\.'; STALL_GAP_S=600
ANSIBLE_FATAL_RE='^[ \t]*(fatal|failed): [[]'   # an Ansible task failure line; ignored ones are removed by norm_log
APPLOG_RE='\[(WARN|WARNING|ERROR)\]'            # application log lines (e.g. from a passing test): never evidence
ERR_RE='##\[error\]|E: |ERROR:|FAILED|[A-Za-z_.]+(Error|Exception|gaierror):'   # real error lines (a bare Traceback header is not one)

# Log-fetch + REAL-signature knobs (2026-11-12). LOGEMPTY_MAX: consecutive empty/failed fetches of one job before "UNKNOWN -> skip".
LOGEMPTY_MAX=3; declare -A EMPTYN=()
ESCFLAG=(); gh api --help 2>&1 | grep -q -e '--allow-escape-sequences' && ESCFLAG=(--allow-escape-sequences)   # detected once; older gh lacks the flag
PY_SUM_RE='\b[0-9]+ (failed|errors?)\b.* in [0-9.]+s'; FAILED_RE='^FAILED [^ ]+::'
VITEST_RE='Test Files +[0-9]+ failed|Tests +[0-9]+ failed'; TS_RE='error TS[0-9]+'
GUARD_RE='(ratchet|guard)[^|]*(violation|exceed|regress|increase|must not)|^E +AssertionError'
STRONG_RE="$PY_SUM_RE|$FAILED_RE|$VITEST_RE|$TS_RE|$GUARD_RE"

# norm_log RAW OUT: drop echoed script source lines, strip ANSI, the "job<TAB>step<TAB>" columns and the leading timestamp
norm_log() {
  grep -v -F '[36;1m' "$1" | sed -E -e 's/(\x1b|\^\[)\[[0-9;]*[A-Za-z]//g' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
    -e 's/^[^\t]+\t[^\t]+\t//' -e 's/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+Z ?//' -e 's/\r$//' > "$2.n"
  drop_ignored "$2.n" > "$2"; rm -f "$2.n"
}
# drop_ignored F: Ansible ignored/rescued failures are not failure evidence. A fatal:/failed: line is dropped when
# (a) "...ignoring" appears before the next "TASK [" / "PLAY " header, or (b) the SAME host reports ok:/changed:/skipping:
# later in the log (a host with a real failure is removed from the play; the CI callback may not print "...ignoring").
drop_ignored() {
  awk -v fre="$ANSIBLE_FATAL_RE" '
    function host(l) { match(l, /[[][^] ]+/); return substr(l, RSTART + 1, RLENGTH - 1) }
    function flush(  i) { for (i = 1; i <= n; i++) if (!((ign || later[i]) && (b[i] ~ fre || b[i] ~ /\.\.\.ignoring/))) print b[i]; n = 0; ign = 0 }
    FNR == NR { if ($0 ~ /^(ok|changed|skipping): [[]/) last[host($0)] = FNR; next }   # pass 1: last live line per host
    /^(TASK \[|PLAY )/ { flush(); print; next }
    n > 0 || $0 ~ fre { b[++n] = $0; later[n] = ($0 ~ fre && last[host($0)] > FNR); if ($0 ~ /\.\.\.ignoring/) ign = 1; next }
    { print }
    END { flush() }' "$1" "$1"
}
# max_gap_s RAW: largest silent gap (seconds) between consecutive timestamps in the raw log
max_gap_s() {
  grep -o -E '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}' "$1" | awk -F'[T:]' '
    { t = $2 * 3600 + $3 * 60 + $4; if (NR > 1) { d = t - p; if (d < 0) d += 86400; if (d > m) m = d } p = t } END { print m + 0 }'
}
# trim_failed_step: full job logs hold every step; keep only the group of the first failed step (up to its ##[error])
trim_failed_step() {
  local n g; n=$(grep -n -m1 -F '##[error]' "$1" | cut -d: -f1); [ -n "$n" ] || { cat "$1"; return; }
  g=$(head -n "$n" "$1" | grep -n -F '##[group]' | tail -1 | cut -d: -f1); sed -n "${g:-1},$((n+3))p" "$1"
}
# fetch_log JOB RAWFILE: failed-step log via gh run view; falls back to the job-logs API (works while the run is still going).
fetch_log() {
  gh run view --job "$1" -R $R --log-failed > "$2" 2>/dev/null && [ -s "$2" ] && return 0
  gh api "${ESCFLAG[@]}" "repos/$R/actions/jobs/$1/logs" > "$2.api" 2>/dev/null && [ -s "$2.api" ] || return 1
  grep -v -F '[36;1m' "$2.api" | sed -E 's/\x1b\[[0-9;]*[A-Za-z]//g' > "$2.api2"; trim_failed_step "$2.api2" > "$2"; [ -s "$2" ]
}
# best_err F: decisive evidence, in order: pytest/vitest summary (+ first FAILED line) | TS/guard error | last (non-ignored)
# Ansible fatal | text right before the final ##[error] | first ERR_RE line | last line. Never an [WARN]/[ERROR] app log line.
best_err() {
  local s fl n; s=$(grep -E -m1 "$PY_SUM_RE|$VITEST_RE" "$1" | sed -E 's/^=+ *//; s/ *=+$//')
  fl=$(grep -E -m1 "$FAILED_RE" "$1")
  [ -z "$s" ] && [ -z "$fl" ] && s=$(grep -E -m1 "$TS_RE|$GUARD_RE" "$1")
  [ -z "$s$fl" ] && s=$(grep -E "$ANSIBLE_FATAL_RE" "$1" | tail -n 1)
  if [ -z "$s$fl" ]; then
    n=$(grep -n -F '##[error]' "$1" | tail -n 1 | cut -d: -f1)
    if [ -n "$n" ]; then
      s=$(head -n "$((n-1))" "$1" | grep -v -E "$APPLOG_RE|^##\[(end)?group\]|^[[:space:]]*$" | tail -n 1)
      s="$s | $(sed -n "${n}p" "$1")"
    fi
  fi
  [ -z "$s$fl" ] && s=$(grep -v -E "Traceback \(most recent call last\):|$APPLOG_RE" "$1" | grep -m1 -E "$ERR_RE")
  [ -n "$s$fl" ] || s=$(tail -n 1 "$1")
  { [ -n "$s" ] && [ -n "$fl" ] && echo "$s | $fl" || echo "$s$fl"; } | tr '\t' ' ' | cut -c1-200
}

# stall_infra F: true (and sets ERRL) when the log holds a stall/timeout signature and NO REAL signature (test summary,
# FAILED line, TS/guard error, non-ignored Ansible fatal) precedes it.
stall_infra() {
  local sn cn n pat; pat=$(IFS='|'; echo "${STALL_SIGS[*]}")
  sn=$(grep -n -m1 -E "$pat" "$1" | cut -d: -f1)
  if [ -z "$sn" ] && grep -qE "$STALL_CANCEL_SIG" "$1" && [ "$(max_gap_s "$1.raw")" -ge "$STALL_GAP_S" ]; then
    sn=$(grep -n -m1 -E "$STALL_CANCEL_SIG" "$1" | cut -d: -f1); fi
  [ -n "$sn" ] || return 1
  head -n "$((sn-1))" "$1" | grep -qE "$STRONG_RE|$ANSIBLE_FATAL_RE" && return 1
  ERRL=$(sed -n "${sn}p" "$1"); n=$(grep -n -F '##[error]' "$1" | tail -n 1 | cut -d: -f1)
  [ -n "$n" ] && [ "$n" -gt "$sn" ] && ERRL="$ERRL | $(sed -n "${n}p" "$1")"
  ERRL=$(tr '\t' ' ' <<< "$ERRL" | cut -c1-200); return 0
}

# classify JOB -> sets C (INFRA|REAL|UNKNOWN|LOG-EMPTY) and ERRL (best error line for REAL)
classify() {
  local job=$1 f="$T/log.$1" dns err
  C=UNKNOWN; ERRL=""
  if [ -n "$LOGFILE" ]; then cp "$LOGFILE" "$f.raw"
  else fetch_log "$job" "$f.raw" || { C=LOG-EMPTY; return; }; fi
  norm_log "$f.raw" "$f"
  [ -s "$f" ] || { [ -n "$LOGFILE" ] || C=LOG-EMPTY; return; }
  dns=$(grep -n -F "${dns_args[@]}" "$f" | head -1 | cut -d: -f1)
  if [ -z "$dns" ]; then
    if ! grep -qE "$STRONG_RE|##\[error\]|$ANSIBLE_FATAL_RE" "$f" && { grep -qE '[0-9]+ passed' "$f" || ! grep -qE "$ERR_RE" "$f"; }; then return; fi   # no failure evidence (ignored Ansible failures were dropped): not a verdict
    if stall_infra "$f"; then C="INFRA(timeout)"; return; fi
    C=REAL; ERRL=$(best_err "$f")
    if grep -qE 'exit 100|Unable to fetch some archives|FAILED: Installing base packages|FAILED: Adding .* PPA' <<< "$ERRL"; then
      if [ -n "$FULLFILE" ]; then cp "$FULLFILE" "$f.full" 2>/dev/null
      else { gh run view --job "$job" -R $R --log || gh api "${ESCFLAG[@]}" "repos/$R/actions/jobs/$job/logs"; } > "$f.full" 2>/dev/null; fi
      if [ -s "$f.full" ] && grep -q -F "${dns_args[@]}" "$f.full"; then C="INFRA(full-log)"; fi
    fi
    return
  fi
  err=$(grep -n -E "$ERR_RE" "$f" | grep -v -E 'Traceback \(most recent call last\):' | head -1)
  local en=${err%%:*} et=${err#*:}
  if [ -z "$err" ] || [ "$en" -ge "$dns" ] || grep -qF "${dns_args[@]}" <<< "$et" || grep -qE 'Failed to fetch|^E: |apt|Could not resolve|Temporary failure' <<< "$et"; then C=INFRA
  else C=REAL; ERRL=$(best_err "$f"); fi
}

# cancel_active: cancel (or, with DRY, list) every non-completed run of the head via the attributed ci-cancel tool.
# Needs PR sha s10 fname ferr; sets CANCELLED.
cancel_active() {
  local runs br r n=0
  runs=$(gh api --paginate "repos/$R/actions/runs?head_sha=$sha&per_page=100" --jq '.workflow_runs[]|select(.status!="completed")|.id' 2>/dev/null) || runs=""
  br=$(gh api "repos/$R/pulls/$PR" -q .head.ref 2>/dev/null)
  CANCELLED=0; [ -n "$runs" ] && n=$(grep -c . <<< "$runs")
  echo "$(now) #$PR $s10 REAL-RED -> cancelling $n active run(s): $fname: ${ferr:0:120}"
  for r in $runs; do
    if [ "$DRY" = 1 ]; then echo "$(now) #$PR $s10 run=$r DRY-RUN would: ci-cancel $r rerun_infra_failures \"red PR #$PR: $fname failed at $s10\" $br $PR"; CANCELLED=$((CANCELLED+1))
    elif "$HOME/.claude/scripts/ci-cancel" "$r" rerun_infra_failures "red PR #$PR: $fname failed at $s10" "$br" "$PR" >/dev/null; then CANCELLED=$((CANCELLED+1))
    else echo "$(now) #$PR $s10 run=$r ERR cancel"; fi
  done
}

# rest_missing: required contexts of main that have no successful/skipped/neutral check run at $sha (prints " [ctx]..."; empty = all present and green)
rest_missing() {
  local ok m="" c
  ok=$(jq -r '.[]|select(.c|IN("success","skipped","neutral"))|.n' <<< "$latest")
  while read -r c; do [ -n "$c" ] && ! grep -qxF -- "$c" <<< "$ok" && m="$m [$c]"; done < <(gh api "repos/$R/branches/main/protection/required_status_checks" -q '.contexts[]' 2>/dev/null)
  echo "$m"
}

[ -n "$CLS" ] && { classify "$CLS"; echo "job=$CLS $C ${ERRL}"; exit 0; }
[ -n "$PR" ] || { echo "usage: $0 [--dry-run] [--once] [--no-cancel] PR [MAX_ATTEMPTS] [INTERVAL]"; exit 64; }

declare -A FIRST=(); LASTSHA=""   # job id -> epoch of first REAL sighting (confirmation needs >= INTERVAL later)
while :; do
  st=$(gh api repos/$R/pulls/$PR -q '[.state,.merged,.head.sha]|@tsv' 2>/dev/null) || { echo "$(now) #$PR ERR api"; sleep "$INT"; continue; }
  read -r state merged sha <<< "$st"
  if [ "$merged" = true ] || [ "$state" = closed ]; then echo "DONE #$PR clean (state=$state merged=$merged)"; exit 0; fi
  [ -n "${RERUN_HEAD_SHA:-}" ] && sha=$RERUN_HEAD_SHA   # test hook: inspect an older head
  s10=${sha:0:10}
  [ "$sha" = "$LASTSHA" ] || FIRST=(); LASTSHA=$sha
  rows=$(gh api --paginate "repos/$R/commits/$sha/check-runs?per_page=100" \
    --jq '.check_runs[]|{n:.name,id:.id,u:(.details_url//""),t:(.started_at//""),c:(.conclusion//"")}' 2>/dev/null) \
    || { echo "$(now) #$PR $s10 ERR api"; sleep "$INT"; continue; }
  [ -n "$rows" ] || { echo "$(now) #$PR $s10 ERR empty"; sleep "$INT"; continue; }
  latest=$(jq -s 'group_by(.n)|map(max_by(.t))' <<< "$rows" 2>/dev/null) || { echo "$(now) #$PR $s10 ERR parse"; sleep "$INT"; continue; }
  [ -n "$latest" ] || { sleep "$INT"; continue; }
  pending=$(jq '[.[]|select(.c=="")]|length' <<< "$latest")
  rl=$("$D/rest_latest.sh" "$sha"); case "$rl" in ERR*) echo "$(now) #$PR $s10 $rl"; sleep "$INT"; continue;; esac
  rp=${rl##*pending=}; [ "$rp" -gt "$pending" ] 2>/dev/null && pending=$rp   # shared definition: queued runs / not-yet-created required checks count
  fails=$(jq -c '.[]|select(.c!="" and (.c|IN("success","skipped","neutral")|not))' <<< "$latest")
  infra=0; real=0; unk=0; reruns=0; waits=0; exh=0; realnames=""; exhnames=""
  declare -A RUNJOBS=() RUNALL=() ; : > "$T/jobs"
  while IFS= read -r row; do
    [ -n "$row" ] || continue
    name=$(jq -r .n <<< "$row"); id=$(jq -r .id <<< "$row"); url=$(jq -r .u <<< "$row")
    if [[ "$url" != *"/actions/runs/"* ]]; then unk=$((unk+1)); realnames="$realnames [$name]"
      echo "$(now) #$PR $s10 run=- attempt=- job=\"$name\" UNKNOWN(non-actions) -> skip"; continue; fi
    run=${url#*/actions/runs/}; run=${run%%/*}
    classify "$id"
    if [ "$C" = LOG-EMPTY ]; then EMPTYN[$id]=$(( ${EMPTYN[$id]:-0} + 1 ))
      echo "$(now) #$PR $s10 run=$run job=\"$name\" LOG-EMPTY (${EMPTYN[$id]}/$LOGEMPTY_MAX) -> retry next poll"
      if [ "${EMPTYN[$id]}" -ge "$LOGEMPTY_MAX" ]; then C=UNKNOWN; echo "$(now) #$PR $s10 run=$run job=\"$name\" UNKNOWN -> skip (log-empty x${EMPTYN[$id]})"; fi
    else EMPTYN[$id]=0; fi
    printf '%s\t%s\t%s\t%s\t%s\n' "$run" "$id" "$C" "$name" "$ERRL" >> "$T/jobs"
  done <<< "$fails"
  realrows=$(awk -F'\t' '$3=="REAL"' "$T/jobs")
  if [ -z "$realrows" ]; then FIRST=()
  elif [ "$NOCANCEL" = 0 ]; then
    declare -A NEXT=(); conf=0; tnow=$(date +%s); fname=""; ferr=""; rnames=""; lbl="REAL(pending-confirm)"
    while IFS=$'\t' read -r _ id _ name errl; do
      NEXT[$id]=${FIRST[$id]:-$tnow}; rnames="$rnames [$name]"; [ -n "$fname" ] || { fname=$name; ferr=$errl; }
      [ -n "${FIRST[$id]:-}" ] && [ $((tnow-FIRST[$id])) -ge "$INT" ] && conf=$((conf+1))
    done <<< "$realrows"
    ferr=$(sed -e 's/\(\x1b\|\^\[\)\[[0-9;]*m//g' -e 's/\x1b\[[0-9;]*m//g' -e 's/.*\t//' -e 's/^[0-9T:.Z-]* //' <<< "$ferr")
    FIRST=(); for k in "${!NEXT[@]}"; do FIRST[$k]=${NEXT[$k]}; done; unset NEXT
    if [ "$ONCE" = 1 ]; then lbl="REAL(once: report only)"; elif [ "$conf" -gt 0 ]; then lbl="REAL(confirmed)"; fi
    while IFS=$'\t' read -r run id c name errl; do
      if [ "$c" = REAL ]; then echo "$(now) #$PR $s10 run=$run job=\"$name\" $lbl -> no-rerun err=\"$errl\""
      else echo "$(now) #$PR $s10 run=$run job=\"$name\" $c -> no-rerun(real-red pass)"; fi
    done < "$T/jobs"
    if [ "$ONCE" = 0 ] && [ "$conf" -gt 0 ]; then
      cancel_active
      echo "REAL-FAILURE #$PR:$rnames (cancelled $CANCELLED runs)"; exit 1
    fi
    [ "$ONCE" = 1 ] && [ "$DRY" = 1 ] && cancel_active
    nreal=$(wc -l <<< "$realrows")
    echo "$(now) #$PR $s10 real=$nreal pending=$pending"
    if [ "$ONCE" = 1 ]; then
      [ "$pending" -eq 0 ] && { echo "REAL-FAILURE #$PR:$rnames (cancelled 0 runs)"; exit 1; }
      exit 0
    fi
    sleep "$INT"; continue
  fi
  for run in $(cut -f1 "$T/jobs" | sort -u); do
    ra=$(gh api repos/$R/actions/runs/$run -q '[.status,.run_attempt,.updated_at]|@tsv' 2>/dev/null) || ra=""
    IFS=$'\t' read -r rstatus att rupd <<< "$ra"; [ -n "$ra" ] || { rstatus=unknown; att=0; rupd=""; }
    bo=0
    if [ "$att" -ge 3 ] && [ -n "$rupd" ]; then
      age=$(( $(date +%s) - $(date -d "$rupd" +%s 2>/dev/null || echo 0) ))
      [ "$age" -lt "$BACKOFF" ] && bo=1
    fi
    nonin=$(awk -F'\t' -v r="$run" '$1==r && $3!~/^INFRA/' "$T/jobs" | wc -l)
    while IFS=$'\t' read -r _ id c name errl; do
      case $c in INFRA*) infra=$((infra+1));; REAL) real=$((real+1));; *) unk=$((unk+1));; esac
      [[ "$c" == INFRA* ]] || realnames="$realnames [$name]"
      if [[ "$c" != INFRA* ]] || [ "$nonin" -gt 0 ]; then act=skip
      elif [ "$rstatus" != completed ]; then act=wait; waits=$((waits+1))
      elif [ "$att" -lt $((MAXA+1)) ] && [ "$bo" = 1 ]; then act="wait(backoff)"; waits=$((waits+1))
      elif [ "$att" -ge $((MAXA+1)) ]; then act=attempts-exhausted; exh=$((exh+1)); exhnames="$exhnames [$name]"
      else act=rerun; fi
      extra=""; { [ "$c" = REAL ] || [ "$c" = "INFRA(timeout)" ]; } && extra=" err=\"$errl\""
      echo "$(now) #$PR $s10 run=$run attempt=$att job=\"$name\" $c -> $act$extra"
    done < <(awk -F'\t' -v r="$run" '$1==r' "$T/jobs")
    if [ "$nonin" -eq 0 ] && [ "$rstatus" = completed ] && [ "$att" -lt $((MAXA+1)) ] && [ "$bo" = 0 ]; then
      if [ "$DRY" = 1 ]; then echo "$(now) #$PR $s10 run=$run DRY-RUN would: gh run rerun $run --failed"; reruns=$((reruns+1))
      elif gh run rerun "$run" --failed -R $R >/dev/null 2>&1; then reruns=$((reruns+1)); echo "$(now) #$PR $s10 run=$run RERUN requested"
      else echo "$(now) #$PR $s10 run=$run ERR rerun"; fi
    fi
  done
  empt=$(awk -F'\t' '$3=="LOG-EMPTY"' "$T/jobs" | wc -l)   # empty log reading: not a verdict, re-poll
  echo "$(now) #$PR $s10 infra=$infra real=$real unknown=$unk pending=$pending$([ "$empt" -gt 0 ] && echo " log-empty=$empt")"
  if [ "$pending" -eq 0 ] && [ -z "$fails" ]; then
    absent=$(rest_missing); if [ -n "$absent" ]; then echo "$(now) #$PR $s10 IDLE #$PR: required checks absent:$absent"; [ "$ONCE" = 1 ] && exit 0; sleep "$INT"; continue; fi
    echo "DONE #$PR clean"; exit 0; fi
  if [ "$pending" -eq 0 ] && [ "$empt" -gt 0 ] && [ $((real+unk-empt)) -le 0 ]; then [ "$ONCE" = 1 ] && exit 0; sleep "$INT"; continue; fi
  if [ "$pending" -eq 0 ] && [ $((real+unk)) -gt 0 ]; then echo "REAL-FAILURE #$PR:$realnames"; exit 1; fi
  if [ "$pending" -eq 0 ] && [ "$reruns" -eq 0 ] && [ "$waits" -eq 0 ] && [ "$exh" -gt 0 ]; then echo "ATTEMPTS-EXHAUSTED #$PR:$exhnames"; exit 2; fi
  [ "$ONCE" = 1 ] && exit 0
  sleep "$INT"
done
