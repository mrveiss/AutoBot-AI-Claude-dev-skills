When to use: End-to-end GitHub issue implementation — umbrella gate, worktree, design, code, verify, PR, CI, and the three-gate closure check. Use when told to implement, fix, or solve a specific issue number, or when picking the next issue off the backlog. Supersedes the former `issue` skill.
When to use: Complete GitHub issue implementation workflow with built-in guardrails
When to use: Complete GitHub issue creation workflow with required type, area, and priority labels

# /autobot-dev-skills:lifecycle implement — End-to-End Issue Implementation

Read your assigned step from the umbrella issue before proceeding.

## Step 0 — Umbrella gate (MANDATORY)
- The task must hang off a GitHub umbrella issue with a task/subtask breakdown. Missing → create it first.
- Add this issue as a subtask checklist item on the umbrella before coding.
- Attach it natively too — a checklist item is not a relationship: `gh api -X POST repos/$REPO/issues/$PARENT/sub_issues -F sub_issue_id=$(gh api repos/$REPO/issues/$CHILD -q .id)`
- Every `Depends on: #N` gets a native edge: `gh api -X POST repos/$REPO/issues/$THIS/dependencies/blocked_by -F issue_id=$(gh api repos/$REPO/issues/$N -q .id)`

## Step 1 — Verify the issue is real and unclaimed
- `gh issue view <n> --json state` — closed or missing → STOP.
- Read the body AND every comment before planning — the decisive context is
  routinely in the comments: criteria agreed after filing, a blocker found later,
  a prior attempt parked, a scope call already made. Acting on the body alone
  redoes settled work.
  ```bash
  gh issue view <n> --json title,body,comments \
  -q '"# \(.title)\n\n\(.body)\n\n--- comments ---\n" + ([.comments[]|"@\(.author.login): \(.body)"]|join("\n\n"))'
  ```
  **Not** `gh issue view <n>` or `--comments`: both render via a GraphQL query
  that still asks for the retired `projectCards` field, so on an older `gh` they
  exit 1 with zero output. Only `--json` paths are safe.
  Long threads are real — one issue here is 21 comments / 86k characters. Check
  `--json comments -q '.comments|length'` first and read the tail when it is
  large, rather than pulling the whole thread into context.
- `gh pr list --search "<n>"` and `git branch -a | grep -i "<n>"` — no existing PR or branch.
- **No PR-count gate.** There is no open-PR limit; dispatch gates on review capacity. PRs piling up means review is the bottleneck — review, don't defer.

## Step 2 — Investigate, then design (do NOT code yet)
- Grep/Glob for the affected files; confirm each exists.
- Post the plan in ≤10 lines: files, changes, edge cases, risks.
- Ask the moment a user-level decision surfaces (architecture, deletion, scope); in an autonomous loop post options + a recommendation on the issue with `needs-decision` and continue. A file count alone is not the trigger.
- Write a TodoWrite checklist of discrete, testable tasks.

## Step 3 — Worktree (MANDATORY, never edit the main tree)
```bash
git worktree add .worktrees/issue-<n> -b issue-<n> origin/main
ledger iam <session> && ledger claim worktree issue-<n> --ttl 168h
```
- Branch off the PR base branch, `origin/main`, never `release`. Never touch another session's worktree.
- Commit incrementally inside the worktree — never `git stash` (it is shared repo-wide).

## Step 4 — Implement
- <8 files: Read → Edit → verify syntax → next file. No subagents (implementer sessions; the merge/review session delegates by model tier).
- ≥8 files or genuinely parallel work: subagents.
- Run the relevant tests after each task; fix failures before continuing.

## Step 5 — Verify
```bash
pytest <test_dir>
git diff --name-only | grep '\.py$' | xargs flake8 --max-line-length=100
mypy <files>
```

## Step 6 — Commit
```bash
git add <files>
git commit -m "<type>(scope): <description> (#<n>)"
```
- Format is `<type>(scope): <description> (#issue)`. `tech-debt` is NOT a valid type.
- **No commit trailers.** mrveiss is sole author — never add `Co-Authored-By`.
- Never `--no-verify`.

## Step 7 — Pre-push quality checks (MANDATORY)
```bash
# print() outside tests → use get_logger(__name__)
grep -r 'print(' autobot-backend/ autobot_shared/ --include='*.py' | grep -v '#' | grep -v 'test_'
# console.* in TS/Vue → use createLogger()
grep -r 'console\.' autobot-frontend/src/ --include='*.ts' --include='*.vue'
black autobot-backend/ autobot_shared/ autobot-slm-backend/
isort autobot-backend/ autobot_shared/ autobot-slm-backend/
ruff check --fix autobot-backend/ autobot_shared/
git add -u && git diff --cached --quiet || git commit -m "style(format): auto-format (#<n>)"
```
- Frontend lint is oxlint AND eslint — `npx eslint` alone passes while CI fails.

## Step 8 — Push and open the PR
```bash
git push -u origin issue-<n>
gh pr create --base main --title "<type>(scope): <title> (#<n>)" --body-file <file>
```
- Target `main`. Direct commits on `release`/`master` are blocked by the pre-commit hook.
- PR body uses these exact headings — never Summary/Test Plan:
  `## Thinking Path` · `## What Changed` · `## Verification` · `## Model Used`
- Use `--body-file`, never an inline `--body`: backticks inside it execute as shell commands.

## Step 9 — CI
- `gh pr checks <PR>` — nothing PENDING and `smoke-test` SUCCESS before hand-off. Never busy-poll: one wakeup or Monitor, no sleep loops.
- Dedupe check-runs to the latest push; sort by `startedAt` — rollup order is not chronological.
- Merge gates (red never merges, 0 behind, `BLOCKED` resting state, `--admin` scope) — see `references/review.md` Merge Decision. Implementers never merge.

## Step 10 — Hand off
- Hand off to the trainmaster's merge train — see `references/pr.md` Step 5.
- Must wait: post ONE comment, set status `in_review`, STOP. Never busy-poll.
- Closes/Refs rule — see `references/pr.md` Step 3.

## Step 11 — Three-gate closure check (MANDATORY)
```bash
pipeline-scripts/check-new-module-callers.sh
pipeline-scripts/check-issue-close-refs.sh <n>   # exit 1 = forward refs dangle → do NOT close
```
- **Gate 1 — verbatim ACs:** quote each issue-body AC word-for-word with evidence, or `❌ NOT met → follow-up #X`. Never restate what shipped instead.
- **Gate 2 — dangling refs:** the script above; also eyeball the credited PR diff for `#<n>`.
- **Gate 3 — no partial close:** a bundled PR's `Closes #A, #B` requires each issue's FULL AC set. Subset delivery → check off the subtask, leave the issue open or name the follow-up in the same comment.
- New module with 0 production callers → wire it in, or file a `wire-in:` issue first and reference it.
- Host-behaviour ACs need HOST evidence, never merge evidence.

```bash
gh issue comment <n> --body-file <file>   # implementation ACs + integration ACs, with evidence
gh issue view <n> --json state            # Closes fired at merge; Refs → close only once every AC is evidenced
```

## Step 12 — Dispose
- Only after the PR is verified merged and the content is in base: `ledger release worktree issue-<n>`, `git worktree remove .worktrees/issue-<n>` (never `--force`), `git branch -D issue-<n>`.

## Success checklist
- [ ] Umbrella issue with step breakdown exists; issue verified open, no duplicate PR/branch
- [ ] Issue attached to the umbrella as a native sub-issue, and every blocker as a `blocked_by` edge
- [ ] Work done in a worktree off `origin/main`, committed incrementally
- [ ] Tests + lint + mypy pass; no `print(`/`console.` violations; formatted
- [ ] Commit format correct, no trailers, no `--no-verify`
- [ ] PR targets `main` with the four required headings; smoke-test green; not behind base
- [ ] Every new module has ≥1 caller, or a wire-in issue is filed and referenced
- [ ] Handed to the trainmaster (PR number + head); `Closes` only if every AC is delivered, else `Refs`; AC evidence posted after merge

---

## Folded from the former AutoBot `implement` skill

# Implement GitHub Issue

## Pre-Flight Checks (MANDATORY - run first)

Before making ANY code changes:

1. **Verify branch state:**
   ```bash
   git branch --show-current
   git status
   git stash list
   ```
   - If on wrong branch, STOP and ask user
   - If uncommitted changes exist, STOP and ask user how to handle
   - If stashes exist, STOP and ask user how to handle

2. **Fetch issue details:**
   ```bash
   gh issue view {issue_number}
   ```
   - Verify issue is still open
   - Read full description and acceptance criteria
   - Check for linked PRs or existing branches

3. **Check for existing work:**
   ```bash
   gh pr list | grep {issue_number}
   git branch -a | grep {issue_number}
   ```
   - If PR/branch exists, STOP and ask user

4. **Verify target merge branch:**
   ```bash
   git fetch origin main
   git log --oneline origin/main -3
   ```
   - Confirm main is the target (unless explicitly told otherwise)

## Implementation Phase

6. **Search memory for context:**
   - Use `mcp__memory__search_nodes` to find relevant past work
   - Check for related issues or patterns

7. **Create implementation plan:**
   - Break work into 3-10 subtasks
   - Add subtasks as checklist to GitHub issue
   - Identify backend vs frontend work
   - Plan commit checkpoints (every 2-3 logical tasks)

8. **Implement using incremental edits:**
   - Use `Edit` for existing files >50 lines (NOT Write)
   - Focus on one subtask at a time
   - Run relevant tests after each subtask
   - **Commit after completing each logical group (2-3 subtasks)**

   **Commit pattern:**
   ```bash
   git add <files-for-this-group>
   git commit -m "<type>(scope): <description> (#{issue_number})"
   git log -1 --stat  # Verify commit landed
   git diff           # Verify nothing left uncommitted
   ```

9. **For multi-phase work (backend + frontend):**
   - Complete and commit backend FIRST
   - Then start frontend
   - Commit frontend when complete
   - Run full test suite

## Verification Phase

10. **Run tests:**
    ```bash
    # Backend
    python -m pytest {affected_test_files}

    # Frontend (if applicable)
    npm run test {affected_components}
    ```

11. **Pre-commit validation:**
    - Run `git diff --staged` before committing
    - Verify no unintended files are staged
    - If pre-commit hooks fail, fix the issue (don't bypass)

## PR & Merge Phase

15. **Close issue** — run the closure gates first ([`CLAUDE_CLOSURE.md`](https://github.com/mrveiss/AutoBot-AI/blob/main/docs/developer/CLAUDE_CLOSURE.md)):
    ```bash
    gh issue close {issue_number} --comment "Implemented in PR #{pr_number}. Gate 2 clear.

    Acceptance criteria (quoted verbatim from issue body):
    - \"<exact AC text>\" — ✅ <evidence>
    - \"<exact AC text>\" — ❌ NOT met → follow-up #XXXX"
    ```

16. **Store in memory:**
    - Use `mcp__memory__create_entities` to record:
      - What was implemented
      - Key technical decisions
      - Patterns used
      - Lessons learned

## Guardrails

**If session is getting long:**
- Commit completed work immediately
- Note what's left in issue comment
- Ask user if should continue or pause

**If implementation is blocked:**
- Document blocker in issue comment
- Ask user how to proceed
- Don't implement workarounds without permission

**If scope expands:**
- Create new issue for additional work
- Ask user if should include in current PR or defer

**If tests fail:**
- Fix failures before creating PR
- Don't skip tests or mark as "will fix later"

## Success Criteria

✅ All code committed with correct issue references
✅ All acceptance criteria verified
✅ Tests passing
✅ Feature branch deleted
✅ Issue closed with summary
✅ Knowledge stored in memory MCP

---

## Folded from the former AutoBot `issue` skill (filing issues)

Invoke as `/autobot-dev-skills:lifecycle issue` to file an issue: the former `issue` skill, kept verbatim below.

# Create GitHub Issue

Creates a well-labeled GitHub issue with all required metadata for filtering and triage.

## Step 1 — Gather details

If not provided upfront, collect:
- **Title**: concise, action-oriented ("Fix X", "Add Y", "Refactor Z")
- **Description**: what's broken or needed, where it is in the codebase, severity/impact
- **Discovered during**: which issue or PR surfaced this (if applicable)

## Step 2 — Choose labels

**Every issue requires at minimum: one Type + one Priority.**

### Type (pick one)
| Label | When |
|-------|------|
| `bug` | Something broken |
| `enhancement` | New feature or improvement |
| `technical-debt` | Cleanup, refactoring |
| `security` | Security vulnerability or hardening |
| `performance` | Speed, memory, efficiency |
| `testing` | Missing or broken tests |
| `documentation` | Docs gap |

### Area — coarse (pick one or more)
`backend` · `frontend` · `testing` · `infrastructure` · `docs` · `ci` · `security`
`database` · `deployment` · `configuration` · `monitoring` · `mcp` · `rag` · `agents`
`memory` · `analytics` · `ai-ml` · `error-handling` · `optimization`

### Area — cluster (pick exactly one)
Every issue also carries its `area: <cluster>` label from the backlog dependency waves —
32 clusters, coloured by wave, listed with `gh label list --search "area: "`. The cluster
says *which body of work* the issue belongs to; the coarse label says which part of the
stack it touches. An issue that fits no existing cluster gets the coarse label only, and
says so in the report.

### Priority (pick one)
| Label | When |
|-------|------|
| `priority: critical` | Data loss, security breach, production down |
| `priority: high` | Major feature broken, significant user impact |
| `priority: medium` | Important but workaround exists |
| `priority: low` | Cosmetic, nice-to-have, minor inconvenience |

## Step 3 — Create issue

```bash
gh issue create \
  --title "<title>" \
  --body "$(cat <<'EOF'
## Problem
<what's wrong or needed>

## Location
<file paths, function names, line numbers>

## Impact
<who is affected and how>

## Discovered During
Working on #<original-issue> (if applicable)

## Acceptance Criteria
- [ ] <criterion 1>
- [ ] <criterion 2>
EOF
)" \
  --label "<type>,<area>,<priority>"
```

## Step 4 — Link relationships (native, not prose)

A checklist item and a `Depends on: #N` line are prose — GitHub's hierarchy and dependency
graphs cannot see them. Record the real edges immediately after creating the issue.
`sub_issue_id` / `issue_id` take the issue's `id`, never its number.

```bash
REPO=mrveiss/AutoBot-AI

# Attach to its umbrella
gh api -X POST repos/$REPO/issues/$UMBRELLA/sub_issues \
  -F sub_issue_id=$(gh api repos/$REPO/issues/$NEW -q .id)

# One edge per blocker, recorded on the BLOCKED issue
gh api -X POST repos/$REPO/issues/$NEW/dependencies/blocked_by \
  -F issue_id=$(gh api repos/$REPO/issues/$BLOCKER -q .id)

# Read back
gh api repos/$REPO/issues/$UMBRELLA/sub_issues         -q '.[].number'
gh api repos/$REPO/issues/$NEW/dependencies/blocked_by -q '.[].number'
```

- One parent per child — re-parenting is `DELETE .../sub_issue -F sub_issue_id=…` then POST.
- Backfilling from an existing checklist: a row owns **at most one** issue. Refs in parentheses,
  or after `blocked by` / `depends on` / `unblocks` / `sub-tree` / `PR`, are commentary — linking
  them re-parents another umbrella's child, and one-parent-per-child then blocks the real parent.
- A duplicate POST returns 422; that means already-linked, not a failure.
- Hierarchy and dependency are separate graphs — never encode one as the other.
- Issue *types* are an org-only GitHub feature and 404 here; labels stay the taxonomy.

## Step 5 — Report and ask

```bash
gh issue view <new-number>   # Confirm creation
```

Then report:
```
Created #<number>: <title>
Labels: <type> · <area> · <priority>
Parent: #<umbrella> (native sub-issue) · Blocked by: #<n>, #<n>
Should I: a) Fix now  b) Finish current issue first  c) Leave for later
```

## Examples

```bash
# Bug discovered during implementation
gh issue create \
  --title "Bug: query_cache has no max size limit" \
  --label "bug,backend,rag,priority: medium"

# New feature
gh issue create \
  --title "feat: add BM25 scoring to keyword search" \
  --label "enhancement,backend,rag,performance,priority: medium"

# Security issue
gh issue create \
  --title "Security: python-ecdsa Minerva timing attack" \
  --label "security,backend,priority: high"
```

## Post-task Gap Check (ALWAYS after completing any task)

> "Were there any gaps or issues discovered while implementing? Do all discoveries have a GitHub issue?"

If yes → run this skill immediately for each discovery before closing the original issue.
