---
name: lifecycle
description: Use for every AutoBot-AI session start and end, and for issue-to-merged-PR work: implementing issues, batches, draining the backlog, opening PRs, any gh operation. Read the matching reference before acting.
---

# Issue → PR lifecycle (router)

Invoke as `/autobot-dev-skills:lifecycle <workflow> [args]`; the first argument selects the row; with no argument, pick the row from the situation. Read only the matching reference.

| Workflow | Situation | Read |
|---|---|---|
| `session-lifecycle` | Applies to ALL sessions: run at the START (worktree, stale-branch cleanup, rebase) and END (wrap up, finish, hand off, mission complete or blocked); also resuming/taking over a session or finding another session's leftovers | `references/session-lifecycle.md` |
| `implement` | Told to implement/fix/solve one issue number, or picking the next issue off the backlog | `references/implement.md` |
| `batch-implement` | "Implement all X-labeled issues", "fix all Y bugs", a list of issue numbers. Do NOT ask for scope clarification: run the pre-flight and start | `references/batch-implement.md` |
| `drain` | Work the backlog, drain issues, "solve what you can", run the loop autonomously, or a loop tick with no assigned issue | `references/drain.md` |
| `pr` | Create a pull request (pre-flight branch checks, target `main`) | `references/pr.md` |
| `github-cli` | ANY GitHub operation (issues, PRs, comments, labels, reviews, merges, file contents, branches, repo queries); always prefer gh CLI over GitHub MCP tools | `references/github-cli.md` |

Chain: session-lifecycle → implement (or drain → batch-implement) → pr → `/autobot-dev-skills:review review`.
