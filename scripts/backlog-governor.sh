#!/usr/bin/env bash
# backlog-governor.sh — generation-rate governor for issue filing.
#
# The backlog grows when issues are filed faster than they are closed. Prose
# rules cannot enforce that; this is the numeric brake.
#
#   verdict   print the current verdict and the numbers behind it
#   check     token-bucket gate for one `gh issue create`; allow or deny
#   status    verdict + current bucket occupancy
#   hook      PreToolUse entry point: reads the tool payload on stdin, gates
#             only real `gh issue create` invocations, ignores everything else
#
# `check`/`hook` emit PreToolUse JSON on deny and stay silent on allow.
# They fail OPEN: if the verdict cannot be computed, filing is never blocked.
#
# Repo is derived from the working directory, never hardcoded.

STATE_DIR="${CLAUDE_STATE_DIR:-$HOME/.claude/state}"
CACHE_TTL="${GOVERNOR_CACHE_TTL:-600}"      # seconds to reuse a computed verdict
PR_DRAIN_LIMIT="${GOVERNOR_PR_LIMIT:-6}"    # open PRs at which the loop must drain
# Six hours, not one: closure runs near 1.3 issues/hour, and an hourly bucket
# cannot express "match that" in whole issues — the integer floor rounded every
# verdict back up to 48/day. A wider window makes the threshold meaningful.
WINDOW="${GOVERNOR_WINDOW:-21600}"          # token-bucket window, seconds
# The advisory threshold is DERIVED from the trailing close rate, not fixed.
# Fixed constants cannot track a backlog: the previous RED of 2/hour permitted
# 48 issues/day against a measured closure of ~19/day, so the strictest setting
# the governor had still described a doubling backlog as acceptable. The budget
# is now "what closure can absorb", scaled per verdict.
FACTOR_GREEN="${GOVERNOR_FACTOR_GREEN:-2.0}" # draining fine — room to explore
FACTOR_AMBER="${GOVERNOR_FACTOR_AMBER:-1.5}" # filing outpaces closing
FACTOR_RED="${GOVERNOR_FACTOR_RED:-1.0}"     # queue jammed — file at most what lands
RATE_FLOOR="${GOVERNOR_RATE_FLOOR:-2}"       # never advise below this, to stay signal not noise
RATE_GREEN="${GOVERNOR_RATE_GREEN:-}"        # set to pin a fixed budget, bypassing the derivation
RATE_AMBER="${GOVERNOR_RATE_AMBER:-}"
RATE_RED="${GOVERNOR_RATE_RED:-}"

mkdir -p "$STATE_DIR" 2>/dev/null

window_label() {
  if [ "$WINDOW" -ge 3600 ]; then printf '%sh' "$(( WINDOW / 3600 ))"
  else printf '%smin' "$(( WINDOW / 60 ))"; fi
}

# True only when `gh issue create` is actually being invoked, not merely quoted
# inside an argument (a PR body, a doc, a commit message, a grep pattern).
# Tokenizes with shlex and requires the three words to sit at a command
# position — statement start, or immediately after a shell separator.
is_invocation() {
  python3 - "$1" <<'PY' 2>/dev/null
import shlex, sys

try:
    lex = shlex.shlex(sys.argv[1], posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    tokens = list(lex)
except ValueError:            # unbalanced quotes — fall back to "not an invocation"
    sys.exit(1)

SEPARATORS = {";", "&&", "||", "|", "&", "\n"}
# Keywords after which the next token is still a command position.
KEYWORDS = {"do", "then", "else", "{", "(", "!"}
# Wrappers that may legitimately precede the real command.
WRAPPERS = {"sudo", "env", "nohup", "time", "timeout", "command", "builtin", "exec"}

at_command_position = True
i = 0
while i < len(tokens):
    tok = tokens[i]
    if tok in SEPARATORS or tok in KEYWORDS:
        at_command_position = True
        i += 1
        continue
    if at_command_position:
        # Skip wrappers and their numeric/VAR=value arguments.
        if tok in WRAPPERS or "=" in tok and not tok.startswith("-"):
            i += 1
            continue
        if tok.isdigit():     # e.g. the N in `timeout N`
            i += 1
            continue
        if tok == "gh" and tokens[i + 1 : i + 3] == ["issue", "create"]:
            sys.exit(0)
        at_command_position = False
    i += 1

sys.exit(1)
PY
}

# Resolve owner/name from the origin remote locally; `gh repo view` is a network
# round-trip, and this runs inside a PreToolUse hook.
repo_slug() {
  local r url
  url=$(git remote get-url origin 2>/dev/null) || url=""
  r=$(printf '%s' "$url" | sed -nE 's#^(https://|ssh://git@|git@)github\.com[:/]([^/]+/[^/]+)$#\2#p')
  r="${r%.git}"
  if [ -z "$r" ]; then
    r=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null) || return 1
  fi
  [ -n "$r" ] || return 1
  printf '%s' "$r"
}

# Recompute the verdict from live GitHub state. Prints: VERDICT|open|unreviewed|red|filed7|closed7
compute_verdict() {
  local repo="$1" prs since filed7 closed7 open_prs unreviewed red verdict

  prs=$(gh pr list --state open --limit 100 \
          --json number,reviewDecision,statusCheckRollup 2>/dev/null) || return 1
  [ -n "$prs" ] || return 1

  open_prs=$(printf '%s' "$prs" | jq 'length')
  unreviewed=$(printf '%s' "$prs" | jq '[.[]|select(.reviewDecision=="REVIEW_REQUIRED")]|length')
  red=$(printf '%s' "$prs" | jq '[.[]|select([.statusCheckRollup[]?|select(.conclusion=="FAILURE")]|length>0)]|length')

  since=$(date -u -d '7 days ago' +%Y-%m-%d 2>/dev/null) || return 1
  filed7=$(gh api -X GET search/issues -f q="repo:$repo is:issue created:>=$since" \
             -f per_page=1 --jq .total_count 2>/dev/null) || return 1
  closed7=$(gh api -X GET search/issues -f q="repo:$repo is:issue closed:>=$since" \
              -f per_page=1 --jq .total_count 2>/dev/null) || return 1

  if [ "$open_prs" -ge "$PR_DRAIN_LIMIT" ] || [ "$red" -ge 1 ]; then
    verdict=RED
  elif [ "$filed7" -gt "$closed7" ]; then
    verdict=AMBER
  else
    verdict=GREEN
  fi

  printf '%s|%s|%s|%s|%s|%s' "$verdict" "$open_prs" "$unreviewed" "$red" "$filed7" "$closed7"
}

# Hook path: never block a tool call on GitHub. Serve whatever verdict is cached
# (stale included) and refresh it in the background when it has expired; the
# inline recompute (100-PR statusCheckRollup query) took ~12s per hook run.
# Empty output = no verdict cached yet (the caller fails open).
get_verdict_cached() {
  local repo="$1" cache age
  cache="$STATE_DIR/governor-verdict.$(printf '%s' "$repo" | tr '/' '_')"
  age=$CACHE_TTL
  [ -f "$cache" ] && age=$(( $(date +%s) - $(stat -c %Y "$cache" 2>/dev/null || echo 0) ))
  if [ "$age" -ge "$CACHE_TTL" ]; then
    ( get_verdict "$repo" >/dev/null 2>&1 & ) </dev/null >/dev/null 2>&1
  fi
  [ -f "$cache" ] && cat "$cache"
  return 0
}

# Cached verdict, recomputed when stale. Empty output = could not determine.
get_verdict() {
  local repo="$1" cache age fresh
  cache="$STATE_DIR/governor-verdict.$(printf '%s' "$repo" | tr '/' '_')"

  if [ -f "$cache" ]; then
    age=$(( $(date +%s) - $(stat -c %Y "$cache" 2>/dev/null || echo 0) ))
    if [ "$age" -lt "$CACHE_TTL" ]; then
      cat "$cache"
      return 0
    fi
  fi

  if fresh=$(compute_verdict "$repo") && [ -n "$fresh" ]; then
    printf '%s' "$fresh" > "$cache"
    printf '%s' "$fresh"
    return 0
  fi

  # Network/API failure: fall back to a stale cache rather than guessing.
  [ -f "$cache" ] && cat "$cache"
  return 0
}

# Issues per WINDOW that closure can absorb at the given verdict.
# Usage: rate_for <verdict> <closed7>
rate_for() {
  local verdict="$1" closed7="$2" pinned factor
  case "$verdict" in
    RED)   pinned="$RATE_RED";   factor="$FACTOR_RED"   ;;
    AMBER) pinned="$RATE_AMBER"; factor="$FACTOR_AMBER" ;;
    *)     pinned="$RATE_GREEN"; factor="$FACTOR_GREEN" ;;
  esac
  if [ -n "$pinned" ]; then printf '%s' "$pinned"; return 0; fi

  case "$closed7" in ''|*[!0-9]*) printf '%s' "$RATE_FLOOR"; return 0 ;; esac

  # closed7 covers 7 days; scale it to one WINDOW, then apply the verdict factor.
  python3 -c "
import math, sys
closed7, window, factor, floor = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
per_window = closed7 * window / (7 * 86400)
print(max(floor, math.ceil(per_window * factor)))
" "$closed7" "$WINDOW" "$factor" "$RATE_FLOOR" 2>/dev/null || printf '%s' "$RATE_FLOOR"
}

# Count bucket entries inside the window, rewriting the log to drop expired ones.
bucket_count() {
  local log="$1" now cutoff
  now=$(date +%s); cutoff=$(( now - WINDOW ))
  [ -f "$log" ] || { printf '0'; return; }
  awk -v c="$cutoff" '$1 > c' "$log" > "$log.tmp" 2>/dev/null && mv "$log.tmp" "$log"
  wc -l < "$log" | tr -d ' '
}

# There is deliberately NO deny() and no parking queue here.
#
# An earlier version denied `gh issue create` past a rate limit and spooled the
# text for later. It was removed on 2026-08-10 after it blocked five findings
# from an unrelated session — the hook is machine-global, so it throttled work
# it knew nothing about, and the parked items sat in a queue with no owner until
# someone happened to look. None had been filed.
#
# Filing is how a finding survives. Reporting the ratio is useful; refusing the
# filing is not. Do not reintroduce a blocking path in this script.

main() {
  local cmd="${1:-status}" repo state verdict open_prs unreviewed red filed7 closed7
  local log used allowed raw stripped

  # Testability: classify a command string without touching network or state.
  if [ "$cmd" = "match" ]; then
    if is_invocation "${2:-}"; then echo "INVOCATION"; exit 0; else echo "mention"; exit 1; fi
  fi

  # PreToolUse entry point. Exit before any network call unless this is a real
  # `gh issue create` — quoted mentions (grep/echo/commit messages) are not.
  if [ "$cmd" = "hook" ]; then
    raw=$(jq -r '.tool_input.command // empty' 2>/dev/null) || exit 0
    [ -n "$raw" ] || exit 0
    # Cheap pre-filter so the common case never spawns a parser.
    printf '%s' "$raw" | grep -q 'issue' || exit 0
    printf '%s' "$raw" | grep -q 'create' || exit 0
    # Regex cannot decide this: a PR body or doc that merely *discusses*
    # `gh issue create` is not an invocation. Tokenize instead — quoted text
    # collapses to a single token and can never sit at a command position.
    is_invocation "$raw" || exit 0
    RAW_CMD="$raw"
    cmd=check
  fi

  repo=$(repo_slug) || { [ "$cmd" = "check" ] && exit 0; echo "not a gh repo"; exit 0; }
  if [ "$cmd" = "check" ]; then
    state=$(get_verdict_cached "$repo")
  else
    state=$(get_verdict "$repo")
  fi

  if [ -z "$state" ]; then
    [ "$cmd" = "check" ] && exit 0        # fail open
    echo "verdict: UNKNOWN (GitHub unreachable, no cached verdict)"
    exit 0
  fi

  IFS='|' read -r verdict open_prs unreviewed red filed7 closed7 <<< "$state"
  log="$STATE_DIR/issue-rate.$(printf '%s' "$repo" | tr '/' '_').log"
  allowed=$(rate_for "$verdict" "$closed7")

  case "$cmd" in
    verdict|status)
      echo "repo:        $repo"
      echo "verdict:     $verdict  (advisory threshold ${allowed} issues / $(window_label), derived from 7d closure)"
      echo "open PRs:    $open_prs  (${unreviewed} awaiting review, ${red} with failing checks)"
      echo "7d filed:    $filed7"
      echo "7d closed:   $closed7  (net $(( filed7 - closed7 )))"
      [ "$cmd" = "status" ] && echo "filed ($(window_label)): $(bucket_count "$log")  — advisory only; filing is never blocked"
      ;;
    check)
      # ADVISORY ONLY — never blocks. Blocking filing was the wrong lever: it
      # does not increase delivery, it just makes findings invisible, and being
      # machine-global it silently throttled unrelated sessions whose parked
      # findings then sat in a queue nobody owned. A discovered problem must
      # always be filable; the backlog ratio is a thing to *report*, not to
      # enforce against the one rule that keeps findings from being dropped.
      used=$(bucket_count "$log")
      date +%s >> "$log"
      if [ "$used" -ge "$allowed" ]; then
        jq -n --arg m "Backlog governor: $verdict — $((used + 1)) issues filed in the last $(window_label) (advisory threshold $allowed).
  open PRs $open_prs ($unreviewed awaiting review, $red failing) | 7d filed $filed7 vs closed $closed7 (net $(( filed7 - closed7 )))
  Filing is never blocked. Raise closure, do not lower filing:
    ~/.claude/scripts/drain-parked.sh     # branches with commits that never landed
    ~/.claude/scripts/worktree-cap.sh status" \
          '{systemMessage: $m}'
      fi
      ;;
    *)
      echo "usage: $(basename "$0") {verdict|status|check|hook}" >&2; exit 2 ;;
  esac
}

main "$@"
