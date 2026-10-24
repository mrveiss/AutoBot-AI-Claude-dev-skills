---
name: pr
description: Create a pull request with pre-flight branch checks, targeting main by default
---

# /pr - Create Pull Request

Target: `main` (the default branch; never `release`, the stable branch). There is no open-PR cap.

## Step 1 — Pre-Flight Checks

```bash
git branch --show-current          # must NOT be main or release
git status && git diff             # must be clean; if not, run /commit first
git log --oneline origin/main..HEAD
```

## Step 1.5 — Pre-Push Quality Check (MANDATORY)

```bash
# Catch violations before they fail CI
grep -rn 'print(' autobot-backend/ autobot_shared/ --include='*.py' | grep -v '#' | grep -v 'test_'
grep -rn 'console\.\(log\|error\|warn\)' autobot-frontend/src/ --include='*.ts' --include='*.vue'
# Auto-format Python
black autobot-backend/ autobot_shared/ autobot-slm-backend/ 2>/dev/null || true
isort autobot-backend/ autobot_shared/ autobot-slm-backend/ 2>/dev/null || true
ruff check --fix autobot-backend/ autobot_shared/ 2>/dev/null || true
# Commit formatting changes if any
git add -u && git diff --cached --quiet || git commit -m "style(format): auto-format (#<issue-number>)"
```

- `print()` → `get_logger(__name__)` from `autobot_shared.logging_manager`; `console.*` → `createLogger()` from `@/utils/debugUtils`
- Fix all violations before proceeding.

## Step 2 — Push Branch

```bash
git push -u origin <current-branch>
# Rejected? git pull --rebase origin main && git push
```

## Step 3 — Create PR

PR body must include these four headings: **Thinking Path · What Changed · Verification · Model Used**

Write the body to a file (never an inline `--body`: backticks in it execute as shell).

`Closes #N` auto-closes at merge: write it only when every AC is delivered, `Refs #N` otherwise. The merger posts the AC evidence; a failed AC reopens the issue.

```markdown
## Thinking Path
- <key decision>
## What Changed
- <change>
## Verification
- <command + output>
## Model Used
<model that did the work>

Refs #<issue-number>
```

```bash
gh pr create --base main --title "<type>(scope): <description> (#issue-number)" --body-file <file>
```

## Step 4 — CI

- Never busy-poll: schedule one wakeup or arm one Monitor, then `gh pr checks <pr>` once when it fires.
- CI failing: root-cause, push a fix commit (not once the head is queued in a train).

## Step 5 — Land and close

Approved PRs land via a merge train run by the trainmaster session — merge commit, never squash. Hand the trainmaster the PR number + head SHA; never push to a head once it is queued; the trainmaster merges and fixes small findings in-train.

The merger posts the per-AC evidence (Closes/Refs rule: Step 3).

```bash
gh issue comment <number> --body-file <file>   # per-AC evidence, after the merge
```

## Step 6: Worktree Cleanup (After Merge)

Once the PR is verified merged (`gh pr view <pr> --json state` = MERGED), clean up both local worktree and branch:

```bash
ledger release worktree <name>
git worktree remove .worktrees/<name>   # no force flag: a refusal is unfinished work
git branch -D <branch-name>
# remote branch normally deleted at landing; if not:
git push origin --delete <branch-name>
```

Do not leave merged worktrees on disk. Stale worktrees waste disk and confuse `git worktree list`.

## Red Flags (STOP)

- Branch is `main` or `release`
- Uncommitted changes present
- No issue reference in title or body
- Skipped pre-push quality checks (Step 1.5)
- Busy-polling CI or pushing to a head queued in a train
