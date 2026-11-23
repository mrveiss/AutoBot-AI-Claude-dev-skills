#!/usr/bin/env bash
# worktree-cap.sh — ratchet limit on live worktrees.
#
# Parallel agents produce work concurrently and land it serially, so worktrees
# accumulate faster than branches land. A flat cap cannot be introduced against
# an existing pile without freezing all work, so the ceiling is a ratchet: it
# starts at the current population and can only ever move down. Every branch
# that lands permanently tightens the budget; nothing tightens it retroactively.
#
#   status    print the ceiling, the live count, and the headroom
#   check     gate one `git worktree add`; allow or deny
#   hook      PreToolUse entry point: reads the tool payload on stdin, gates
#             only real `git worktree add` invocations, ignores everything else
#
# Fails OPEN: if the count cannot be determined, the add is never blocked.

STATE_DIR="${CLAUDE_STATE_DIR:-$HOME/.claude/state}"
FLOOR="${WORKTREE_CAP_FLOOR:-8}"        # the ratchet never tightens past this
OVERRIDE="${WORKTREE_CAP:-}"            # set to pin the ceiling explicitly

mkdir -p "$STATE_DIR" 2>/dev/null

# True only when `git worktree add` is actually being invoked, not merely quoted
# inside an argument (a doc, a commit message, a grep pattern). Tokenizes with
# shlex and requires the three words to sit at a command position.
is_invocation() {
  python3 - "$1" <<'PY' 2>/dev/null
import re, shlex, sys

# Heredoc bodies are documentation, not commands: a `git worktree add` quoted
# inside one must stay invisible here, which is why the per-line walk below runs
# only after they are removed.
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def strip_heredocs(src: str) -> str:
    out, lines, i = [], src.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        marker = _HEREDOC.search(line)
        i += 1
        if marker:
            end = marker.group(2)
            while i < len(lines) and lines[i].strip() != end:
                i += 1
            i += 1  # drop the terminator too
    return "\n".join(out)


SEPARATORS = {";", "&&", "||", "|", "&", "\n"}
KEYWORDS = {"do", "then", "else", "{", "(", "!"}
WRAPPERS = {"sudo", "env", "nohup", "time", "timeout", "command", "builtin", "exec"}
VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}


def walk(tokens: list) -> bool:
    """True when `git worktree add` sits at a command position in *tokens*."""
    at_command_position = True
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in SEPARATORS or tok in KEYWORDS:
            at_command_position = True
            i += 1
            continue
        if at_command_position:
            if tok in WRAPPERS or "=" in tok and not tok.startswith("-"):
                i += 1
                continue
            if tok.isdigit():
                i += 1
                continue
            if tok == "git":
                j = i + 1
                while j < len(tokens) and tokens[j].startswith("-"):
                    j += 2 if tokens[j] in VALUE_OPTS else 1
                if tokens[j : j + 2] == ["worktree", "add"]:
                    return True
            at_command_position = False
        i += 1
    return False


def tokenize(text: str):
    lex = shlex.shlex(text, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    return list(lex)


# shlex treats a newline as ordinary whitespace and discards it, so a command
# on its own line used to inherit the previous line's "not at a command
# position" state: `cd /path` followed by `git worktree add` parsed as arguments
# to `cd`, and this gate never fired. Every line is therefore walked in its own
# right, which is what a newline means to a shell. The whole-string walk is kept
# as a fallback so a line that cannot be tokenized alone (a quote spanning lines)
# stays covered exactly as it was before.
body = strip_heredocs(sys.argv[1])
for line in body.split("\n"):
    if not line.strip():
        continue
    try:
        if walk(tokenize(line)):
            sys.exit(0)
    except ValueError:
        continue

try:
    sys.exit(0 if walk(tokenize(body)) else 1)
except ValueError:            # unbalanced quotes -- fall back to 'not an invocation'
    sys.exit(1)
PY
}

# Key the ceiling to the repo, so unrelated projects keep separate budgets.
repo_key() {
  local root
  root=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || return 1
  [ -n "$root" ] || return 1
  printf 'worktree-ceiling.%s' "$(printf '%s' "$root" | tr '/' '_')"
}

# Live worktrees excluding the main tree.
live_count() {
  local n
  # #20875 + owner ruling 2026-11-06: leaked /tmp/autobot-reach-base-* test checkouts do not count.
  n=$(git worktree list --porcelain 2>/dev/null | grep '^worktree ' | grep -vc '/autobot-reach-base-') || [ "${PIPESTATUS[2]}" = 1 ] || return 1
  [ "$n" -ge 1 ] 2>/dev/null || return 1
  printf '%s' $(( n - 1 ))
}

# Read the ceiling, seeding it on first use and ratcheting it down when the
# population has dropped. Never ratchets up.
ceiling_for() {
  local cache="$1" count="$2" current target
  if [ -n "$OVERRIDE" ]; then printf '%s' "$OVERRIDE"; return 0; fi

  if [ -f "$cache" ]; then
    current=$(cat "$cache" 2>/dev/null)
  fi
  case "$current" in ''|*[!0-9]*) current="" ;; esac

  # Seed at the existing population + 1 so introducing the cap never freezes
  # work that is already in flight; it only stops the pile from growing.
  target=$(( count + 1 ))
  [ "$target" -lt "$FLOOR" ] && target="$FLOOR"

  if [ -z "$current" ] || [ "$target" -lt "$current" ]; then
    printf '%s' "$target" > "$cache" 2>/dev/null
    printf '%s' "$target"
  else
    printf '%s' "$current"
  fi
}

deny() {
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":%s}}' \
    "$(printf '%s' "$1" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
  exit 2
}

main() {
  local cmd="${1:-status}" key cache count ceiling

  if [ "$cmd" = "hook" ]; then
    local payload command
    payload=$(cat)
    command=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null)
    [ -n "$command" ] || exit 0
    is_invocation "$command" || exit 0
    cmd=check
  fi

  key=$(repo_key) || { [ "$cmd" = "check" ] && exit 0; echo "not a git repo"; exit 0; }
  cache="$STATE_DIR/$key"
  count=$(live_count) || { [ "$cmd" = "check" ] && exit 0; echo "cannot count worktrees"; exit 0; }
  ceiling=$(ceiling_for "$cache" "$count")

  case "$cmd" in
    status)
      echo "ceiling:  $ceiling  (floor $FLOOR${OVERRIDE:+, pinned by WORKTREE_CAP})"
      echo "live:     $count"
      echo "headroom: $(( ceiling - count ))"
      ;;
    check)
      if [ "$count" -ge "$ceiling" ]; then
        deny "Worktree ceiling reached: $count live, ceiling $ceiling.

Land one branch before starting another. Parallel work is produced concurrently
but merged serially, so an unlanded branch is finished work earning nothing.

  ~/.claude/scripts/worktree-reap.sh         # retires workspaces whose work is safe on origin
  ~/.claude/scripts/drain-parked.sh          # ranks branches by readiness to land

The ceiling ratchets down on its own as branches land (floor $FLOOR); it never
rises. To start work that genuinely must run alongside the rest, re-run with
WORKTREE_CAP set to an explicit number."
      fi
      exit 0
      ;;
    *)
      echo "usage: $(basename "$0") {status|check|hook}" >&2; exit 2 ;;
  esac
}

main "$@"
