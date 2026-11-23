#!/usr/bin/env bash
# worktree-claim.sh — record which session created a worktree, and what for.
#
# Nothing in git carries this. A branch name gives you an issue number at best,
# commits cannot carry a session trailer here (the repo forbids trailers and a
# required check enforces it), and a worktree found dirty weeks later gives no
# way to tell who was in it or what they were partway through. That turns every
# stale worktree into an investigation before it can be a resumption.
#
# Provenance lives in git's own per-worktree admin dir
# ($GIT_COMMON_DIR/worktrees/<name>/session-provenance): outside the working
# tree, so it can never be committed or pollute a diff, and removed by git
# itself when the worktree goes.
#
#   claim [path] [note]   record this session as the owner (first claim wins)
#   show  [path]          print the provenance, inferring what it can if unclaimed
#
# Inference matters as much as recording: every worktree that predates this
# script has no claim, and `show` reconstructs what git still knows — branch,
# issue, first and last commit, and who authored them.

set -uo pipefail

MODE="${1:-show}"
TARGET="${2:-$PWD}"
NOTE="${3:-}"

admin_dir() {
  local path="$1" gitdir
  gitdir="$(git -C "$path" rev-parse --absolute-git-dir 2>/dev/null)" || return 1
  case "$gitdir" in *"/worktrees/"*) printf '%s' "$gitdir" ;; *) return 1 ;; esac
}

claim() {
  local path="$1" note="$2" admin file
  admin="$(admin_dir "$path")" || { echo "worktree-claim: $path is not a linked worktree" >&2; return 1; }
  file="$admin/session-provenance"
  if [ -s "$file" ] && [ "${CLAIM_FORCE:-0}" != "1" ]; then
    echo "already claimed — $(grep -m1 '^session_id=' "$file" 2>/dev/null || echo 'unknown session')"
    return 0
  fi
  {
    echo "session_id=${CLAUDE_CODE_SESSION_ID:-unknown}"
    echo "claimed_at=$(date -Is)"
    echo "host=$(hostname 2>/dev/null || echo unknown)"
    echo "branch=$(git -C "$path" branch --show-current 2>/dev/null)"
    echo "base=$(git -C "$path" rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || echo unknown)"
    [ -n "$note" ] && echo "note=$note"
  } > "$file"
  echo "claimed $path for session ${CLAUDE_CODE_SESSION_ID:-unknown}"
}

show() {
  local path="$1" admin file branch
  admin="$(admin_dir "$path")" || { echo "not a linked worktree: $path" >&2; return 1; }
  file="$admin/session-provenance"
  branch="$(git -C "$path" branch --show-current 2>/dev/null)"
  if [ -s "$file" ]; then
    cat "$file"
  else
    # Unclaimed: reconstruct from what git still knows, so a stale worktree is a
    # resumption rather than an investigation.
    echo "session_id=unrecorded (predates provenance, or created outside the wrapper)"
    echo "branch=$branch"
    case "$branch" in
      issue-*|hotfix-*) echo "issue=#$(printf '%s' "$branch" | grep -oE '[0-9]+' | head -1)" ;;
    esac
    echo "first_commit=$(git -C "$path" --no-optional-locks log --reverse --format='%ad %an — %s' --date=short 2>/dev/null | head -1)"
    echo "last_commit=$(git -C "$path" --no-optional-locks log -1 --format='%ad %an — %s' --date=short 2>/dev/null)"
    echo "dirty_files=$(git -C "$path" --no-optional-locks status --porcelain 2>/dev/null | wc -l)"
    # --not <base> is load-bearing: a refreshed worktree carries base commits that
  # inflate the naive count, several-fold in practice. An unpushed count that is
  # wrong in the reassuring direction is worse than none — it cries wolf on every
  # worktree until nobody reads it, including the one where the work is real.
  # NOT origin/HEAD: the default branch is not the PR base in every repo (git-flow's
  # develop), and excluding the wrong branch would leave the count inflated while
  # looking principled. Dev_new_gui is last: AutoBot-AI's base until the 2026-09-12
  # rename, kept only while its mirror branch exists.
  local base=""
  for cand in develop main master Dev_new_gui; do
    git -C "$path" show-ref --verify --quiet "refs/remotes/origin/$cand" && { base="refs/remotes/origin/$cand"; break; }
  done
  echo "unpushed=$(git -C "$path" --no-optional-locks rev-list --count "@{upstream}..HEAD" --not "$base" 2>/dev/null || echo 'no upstream')"
  fi
}

case "$MODE" in
  claim) claim "$TARGET" "$NOTE" ;;
  show)  show "$TARGET" ;;
  *) echo "usage: worktree-claim.sh {claim|show} [path] [note]" >&2; exit 2 ;;
esac
