#!/usr/bin/env bash
# Cron wrapper for worktree-reap.sh — mirrors worktree-refresh-cron.sh.
#
# Kept separate from the tool itself so the schedule's concerns (cwd, PATH,
# overlap, log growth) stay out of the script a human runs by hand. Cron starts
# in $HOME with a minimal PATH and no shell profile, so the `cd` below is what
# makes every repo-relative call resolve — without it the job runs and silently
# does nothing.

export PATH=/usr/local/bin:/usr/bin:/bin
REPO="${REAP_REPO:-$HOME/AutoBot-Ai/AutoBot-AI}"
LOG="${REAP_LOG:-$HOME/.claude/logs/worktree-reap.log}"
KEEP_LINES="${REAP_LOG_LINES:-2000}"

mkdir -p "$(dirname "$LOG")" 2>/dev/null

cd "$REPO" 2>/dev/null || { echo "$(date -Is) repo not found: $REPO" >> "$LOG"; exit 0; }

{
  echo "===== $(date -Is) ====="
  REAP_REPO="$REPO" "$HOME/.claude/scripts/worktree-reap.sh" reap 2>&1
} >> "$LOG"

if [ "$(wc -l < "$LOG" 2>/dev/null || echo 0)" -gt "$KEEP_LINES" ]; then
  tail -n "$KEEP_LINES" "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
