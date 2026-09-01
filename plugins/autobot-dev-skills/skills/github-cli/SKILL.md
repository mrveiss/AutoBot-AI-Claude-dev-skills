---
name: github-cli
description: Use when performing any GitHub operation — issues, PRs, comments, labels, reviews, merges, file contents, branch management, or repository queries. Always prefer gh CLI over GitHub MCP tools.
---

# GitHub CLI (gh)

Use `gh` for all GitHub operations. Never use browser automation or GitHub MCP tools when `gh` will do.

## Issues

```bash
# View / list
gh issue view <number> --json title,body,comments   # NOT bare: see note below
gh issue list --state open --label "bug,backend"
gh issue list --assignee @me

# Create
gh issue create --title "Bug: <desc>" --body "..." --label "bug,backend,priority: high"

# Update / close
gh issue comment <number> --body "..."
gh issue close <number>
gh issue edit <number> --add-label "priority: high" --title "New title"

# Check state
gh issue view <number> --json state -q '.state'
```

## Issue Relationships (native — always, not just prose)

A checklist or a `Depends on:` line is prose; GitHub cannot see it. Record every parent/child and
every blocker natively **at filing time**. `sub_issue_id` / `issue_id` take the issue's `id`, not
its number.

```bash
REPO=mrveiss/AutoBot-AI

# Parent -> child (hierarchy)
CHILD_ID=$(gh api repos/$REPO/issues/$CHILD -q .id)
gh api -X POST repos/$REPO/issues/$PARENT/sub_issues -F sub_issue_id="$CHILD_ID"

# Blocker (dependency) — recorded on the BLOCKED issue
BLOCKER_ID=$(gh api repos/$REPO/issues/$BLOCKER -q .id)
gh api -X POST repos/$REPO/issues/$BLOCKED/dependencies/blocked_by -F issue_id="$BLOCKER_ID"

# Read back
gh api repos/$REPO/issues/$PARENT/sub_issues            -q '.[].number'
gh api repos/$REPO/issues/$N/dependencies/blocked_by    -q '.[].number'
gh api repos/$REPO/issues/$N/dependencies/blocking      -q '.[].number'

# Undo / re-parent
gh api -X DELETE repos/$REPO/issues/$PARENT/sub_issue -F sub_issue_id="$CHILD_ID"
gh api -X DELETE repos/$REPO/issues/$N/dependencies/blocked_by/$BLOCKER_ID
```

- One parent per child. Re-parenting is DELETE then POST; a duplicate POST returns 422.
- Hierarchy and dependency are different graphs — never encode one as the other.
- Issue *types* are org-only; this repo is user-owned, so keep using labels.

## Pull Requests

```bash
# View / list
gh pr view [number]
gh pr list --state open
gh pr diff [number]

# Create (always target Dev_new_gui)
gh pr create --base Dev_new_gui --title "..." --body "..."

# Review / merge
gh pr review <number> --approve
gh pr merge <number> --squash

# Status checks
gh pr status
gh pr checks <number>
```

## Files & Code

```bash
# Get file from any branch/ref
gh api repos/mrveiss/AutoBot-AI/contents/<path>?ref=<branch> --jq '.content' | base64 -d

# Search code
gh search code "query" --repo mrveiss/AutoBot-AI
```

## Comments & Reviews

```bash
gh pr comment <number> --body "..."
gh issue comment <number> --body "..."
gh pr review <number> --comment --body "..."
```

## Quick Reference

| Task | Command |
|------|---------|
| View issue | `gh issue view <n> --json title,body,comments` |
| Create issue | `gh issue create --title "..." --label "..."` |
| Link child to umbrella | `gh api -X POST repos/$REPO/issues/$P/sub_issues -F sub_issue_id=$(gh api repos/$REPO/issues/$C -q .id)` |
| Link blocker | `gh api -X POST repos/$REPO/issues/$B/dependencies/blocked_by -F issue_id=$(gh api repos/$REPO/issues/$A -q .id)` |
| Close issue | `gh issue close <n>` |
| Create PR | `gh pr create --base Dev_new_gui ...` |
| View PR diff | `gh pr diff <n>` |
| Merge PR | `gh pr merge <n> --squash` |
| List labels | `gh label list` |
| View checks | `gh pr checks <n>` |

## AutoBot Conventions

- **Repo:** `mrveiss/AutoBot-AI`
- **Base branch:** Always `Dev_new_gui` (never `main`) for PRs
- **Required labels:** type (`bug`, `enhancement`, `technical-debt`) + area (`backend`, `frontend`) + priority (`priority: high`, etc.)
- **Commit/PR title format:** `<type>(scope): <description> (#issue-number)`
- **Auto-close limitation:** `Closes #NNN` in a PR body **does not auto-close issues** when merging into `Dev_new_gui` (only works for the default branch). **Always close the GH issue manually after merge:**
  ```bash
  gh pr merge <pr> --squash --delete-branch
  gh issue close <number> --comment "Closed via PR #<pr> merged into Dev_new_gui."
  gh issue view <number> --json state  # confirm state=CLOSED
  ```

## Common Mistakes

- Targeting `main` instead of `Dev_new_gui` for PRs
- Forgetting required labels on new issues
- Assuming `Closes #NNN` in PR body auto-closes the issue (it doesn't for `Dev_new_gui`)
- Merging a PR without immediately closing the linked GH issue — issues stay open forever otherwise
- Using Playwright/browser for GitHub when `gh` handles it in one command

## Prefer `--json` for issue reads

`gh issue view <n> --json title,body,comments` is the form to use when an agent
reads an issue to act on it. Not because the plain form is broken -- it works on
`gh` 2.98.0 -- but because the JSON form is parseable, lets you select fields,
and makes "read the comments too" explicit rather than incidental.

History worth keeping: this environment shipped `gh` 2.4.0 (2022) until
2026-08-30, whose text renderers still requested the retired `projectCards`
GraphQL field. Bare `gh issue view` and `--comments` exited 1 with **no output
at all**, as did `gh pr edit`; `gh run list --branch` and `gh run rerun --failed`
did not exist. Only `--json` paths worked. Resolved by upgrading to 2.98.0
(#15305). If a `gh` subcommand ever fails with a `projectCards` GraphQL error
again, check the client version first.
