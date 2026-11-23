#!/usr/bin/env bash
# Cron wrapper for worktree-refresh.sh — see #15306.
#
# Kept separate from the script itself so the schedule's concerns (cwd, PATH,
# overlap, log growth) stay out of the tool a human runs by hand.

export PATH=/usr/local/bin:/usr/bin:/bin
REPO="${REFRESH_REPO:-$HOME/AutoBot-Ai/AutoBot-AI}"
LOG="${REFRESH_LOG:-$HOME/.claude/logs/worktree-refresh.log}"
KEEP_LINES="${REFRESH_LOG_LINES:-2000}"

cd "$REPO" 2>/dev/null || { echo "$(date -Is) repo not found: $REPO" >> "$LOG"; exit 0; }

{
  echo "===== $(date -Is) ====="
  "$HOME/.claude/scripts/worktree-refresh.sh" refresh 2>&1
} >> "$LOG"

# Hourly output accumulates; keep the log bounded without needing logrotate.
if [ "$(wc -l < "$LOG" 2>/dev/null || echo 0)" -gt "$KEEP_LINES" ]; then
  tail -n "$KEEP_LINES" "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
