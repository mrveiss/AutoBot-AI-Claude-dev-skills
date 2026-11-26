---
name: lifecycle
description: Use for every AutoBot-AI session start and end, and for issue-to-merged-PR work: implementing or filing issues, commits, parallel agents, deploys, batches, draining the backlog, PRs, any gh operation, and researching or adopting an external project into issues and code. Read the matching reference before acting.
---

# Issue → PR lifecycle (router)

Invoke as `/autobot-dev-skills:lifecycle <workflow> [args]`; the first argument selects the row; with no argument, pick the row from the situation. Read only the matching reference.

| Workflow | Situation | Read |
|---|---|---|
| `session-lifecycle` | Applies to ALL sessions: run at the START (worktree, stale-branch cleanup, rebase) and END (wrap up, finish, hand off, mission complete or blocked); also resuming/taking over a session or finding another session's leftovers | `references/session-lifecycle.md` |
| `implement` | Told to implement/fix/solve one issue number, or picking the next issue off the backlog | `references/implement.md` |
| `issue` | Filing a new GitHub issue (type/area/priority labels, body, native sub-issue / blocked_by edges, post-task gap check) | `references/implement.md` (section "former `issue` skill") |
| `commit` | Committing in AutoBot-AI: the AutoBot-specific rules (branch names, message format, no trailers, hook-failure table); the generic steps are `/claude-dev-skills:coding commit` | `references/commit.md` |
| `parallel` | Several issues at once with isolated worktrees and parallel agents | `references/parallel.md` |
| `deploy` | Pushing code to a remote VM/server and verifying the deployment | `references/deploy.md` |
| `research` | Analyse a web article, GitHub repo or local file, then compare it to the AutoBot codebase (report only) | `references/research.md` |
| `research-to-issues` | Research-only run that must end in a filed issue tree (umbrella + children) and must NOT touch code, worktrees, commits or PRs | `references/research-to-issues.md` |
| `adopt` | Adopt, port or bring in external features; research, file issues, drive them to merged PRs with an evidence report | `references/adopt.md` |
| `batch-implement` | "Implement all X-labeled issues", "fix all Y bugs", a list of issue numbers. Do NOT ask for scope clarification: run the pre-flight and start | `references/batch-implement.md` |
| `drain` | Work the backlog, drain issues, "solve what you can", run the loop autonomously, or a loop tick with no assigned issue | `references/drain.md` |
| `pr` | Create a pull request (pre-flight branch checks, target `main`) | `references/pr.md` |
| `github-cli` | ANY GitHub operation (issues, PRs, comments, labels, reviews, merges, file contents, branches, repo queries); always prefer gh CLI over GitHub MCP tools | `references/github-cli.md` |

Research chain: research → research-to-issues (or adopt → issue → implement). Chain: session-lifecycle → implement (or drain → batch-implement) → pr → `/autobot-dev-skills:review review`.
