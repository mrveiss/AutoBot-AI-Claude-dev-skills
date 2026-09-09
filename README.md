# AutoBot-AI Claude Dev Skills

AutoBot-AI-specific [Claude Code](https://claude.com/claude-code) skills, packaged as a plugin
marketplace so every developer on the platform gets the **same** workflow setup with one install.

These encode the AutoBot-AI development workflow — the issue-to-merge loop, full-stack debugging,
and codebase auditing — and they hardcode AutoBot's conventions (`Dev_new_gui`, `autobot_shared`,
the deploy path, the required PR-body headings). They are the project-specific counterpart to the
general, reusable-anywhere skills in
[Claude-Dev-Skills](https://github.com/mrveiss/Claude-Dev-Skills).

> **Requires an [AutoBot-AI](https://github.com/mrveiss/AutoBot-AI) checkout.** These skills reference the platform's paths and conventions;
> they are not meant to run against an unrelated codebase.

Copyright © 2026 mrveiss · Apache-2.0.

---

## The one rule

Every skill here assumes it, so it is stated once rather than repeated in each.

**Say "I don't know" — never fabricate.**

A plausible-sounding guessed cause, count or verdict is the one error treated as
serious. Not because guessing is impolite, but because **for an agent a wrong
answer is not an opinion — it executes.** A person who fabricates a cause is
wrong until someone checks; an agent acts on it, at machine speed, against the
environment it needs to keep working. A guess produces an action, the action
produces new state, and the new state is then read as evidence.

**And an admission is not a closure — it is an opening.** *"I don't know"* means
*"I need help with this: let's research it, guide me, let's find the answer
together."* It is the rewarded move because it **starts** the conversation that
solves the problem, not because it ends one.

So the follow-through is not silence. In an interactive session, **ask right
then** — for the guidance, the decision, or the joint dig that closes the gap.
Where there is nobody to ask, leave the criterion unticked and say why, fix it in
scope or file it, and never drop it. An admission that opens no dialog and
produces no issue has lost the finding politely.

A *stated* gap is a finding. An *unstated* one is the defect. The same missing
knowledge produces either, depending only on whether someone wrote it down.

The operative form for anything mechanical: **distinguish *nothing found* from
*did not look*.** A check that never ran and a check that passed report the same
green, and only one of them means anything.

## Install

In Claude Code:

```
/plugin marketplace add mrveiss/AutoBot-AI-Claude-dev-skills
/plugin install autobot-dev-skills@autobot-ai-claude-dev-skills
```

or via the CLI:

```bash
claude plugin marketplace add mrveiss/AutoBot-AI-Claude-dev-skills
claude plugin install autobot-dev-skills@autobot-ai-claude-dev-skills
```

Every AutoBot developer runs the same two lines and gets the identical skill set — the point of
this repo. On a new machine, they restore the whole workflow.

## The skills

### Issue → merge

- **`batch-implement`** — Full implement→review→merge→close→discover loop for a list of GitHub issues, with self-healing retry and per-issue verification.
- **`implement`** — End-to-end GitHub issue implementation — umbrella gate, worktree, design, code, verify, PR, CI, and the three-gate closure check
- **`pr`** — Create a pull request with pre-flight branch checks, targeting Dev_new_gui by default
- **`pre-merge-validate`** — Validate code before merging — syntax, imports, call-site impact, tests, types, and linting
- **`drain`** — Pick and solve the backlog issues that need no decision

### Review

- **`review`** — Run a PR review cycle — CI diagnosis, a three-angle finder pass, lint-only auto-fix, and the merge decision
- **`review-fleet`** — Dispatch a 10-angle parallel PR review fleet (finder agents + verifier agents) that posts only confirmed, deduplicated findings to a single PR comment

### Audit

- **`api-wiring-audit`** — Audit and enforce frontend/backend API contract wiring in AutoBot-AI (or any FastAPI + SPA monorepo)
- **`dead-code-audit`** — Systematic codebase audit for unwired code — identify unregistered routers, uninvoked hooks, orphaned components, and file discovery issues

### Debug

- **`debug-autobot`** — Debug any AutoBot failure across the full stack — dispatches parallel investigators per layer (Vue, FastAPI, Redis, ChromaDB, NPU, Browser, AI Stack),

### Platform & session

- **`github-cli`** — Use when performing any GitHub operation — issues, PRs, comments, labels, reviews, merges, file contents, branch management, or repository queries
- **`session-lifecycle`** — Mandatory start-of-session and end-of-session protocol for every Claude Code session in this repository

## Configuration

`debug-autobot` reads service hosts from environment variables — export them from your deployment
before use, never hardcode addresses:

```bash
export REDIS_HOST=… NPU_HOST=… BROWSER_HOST=… AISTACK_HOST=…
```

## Layout

```
.claude-plugin/marketplace.json            the marketplace manifest
plugins/autobot-dev-skills/
  .claude-plugin/plugin.json               the plugin manifest
  skills/<name>/SKILL.md                    one skill each
```

## Updating

```bash
claude plugin marketplace update autobot-ai-claude-dev-skills
```

## Relationship to the AutoBot-AI repo

The general half of this discipline lives in
[Claude-Dev-Skills](https://github.com/mrveiss/Claude-Dev-Skills) — reusable on any project. This
repo holds the half that only makes sense with AutoBot-AI. Keeping them apart means a general
skill improves for everyone while a project-specific one stays where its conventions apply.
