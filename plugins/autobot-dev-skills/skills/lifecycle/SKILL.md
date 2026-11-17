---
name: lifecycle
description: Use for any AutoBot-AI issue-to-merged-PR work: starting or ending a session, implementing an issue, batches, draining the backlog, opening a PR, or any gh operation. Read the matching reference before acting.
---

# Issue → PR lifecycle (router)

Read the one reference whose situation matches; do not read the rest.

| Situation | Read |
|---|---|
| Session start/end, resume, take over, wrap up, hand off, stale-branch leftovers | `references/session-lifecycle.md` |
| Told to implement/fix/solve one issue number (umbrella gate, worktree, design, code, verify, PR, CI, closure) | `references/implement.md` |
| "Implement all X-labeled issues", a list of issue numbers, a batch run | `references/batch-implement.md` |
| Work the backlog / "solve what you can" / loop tick with no assigned issue | `references/drain.md` |
| Create a pull request (pre-flight branch checks, target `main`) | `references/pr.md` |
| Any GitHub operation: issues, PRs, comments, labels, reviews, merges, file contents, branches | `references/github-cli.md` |

Chain: session-lifecycle → implement (or drain → batch-implement) → pr → review skill (`autobot-dev-skills:review`).
