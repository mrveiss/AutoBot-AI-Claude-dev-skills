# AutoBot-AI Claude Dev Skills

AutoBot-AI-specific [Claude Code](https://claude.com/claude-code) skills, packaged as a plugin
marketplace so every developer on the platform gets the **same** workflow setup with one install.

These encode the AutoBot-AI development workflow — the issue-to-merge loop, full-stack debugging,
and codebase auditing — and they hardcode AutoBot's conventions (`main` as the PR base, `release` as the stable branch, `autobot_shared`,
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

Five router meta-skills. Each `SKILL.md` is a short decision table; the full workflow is read on demand from its `references/` folder.

- **`lifecycle`** (`autobot-dev-skills:lifecycle`) — the issue-to-merged-PR workflow. Covers the former `session-lifecycle`, `implement`, `batch-implement`, `drain`, `pr` and `github-cli` skills plus the absorbed AutoBot project skills `issue` (folded into `implement`), `commit`, `parallel`, `deploy`, `research`, `research-to-issues` and `adopt` (`references/<old-name>.md`).
- **`review`** (`autobot-dev-skills:review`) — PR review and validation. Covers `review`, `review-fleet` and `pre-merge-validate`, plus the read-only reviewer lenses `code-reviewer`, `code-skeptic` and `security-auditor`.
- **`audit`** (`autobot-dev-skills:audit`) — unwired-code and API-contract audits. Covers `api-wiring-audit` and `dead-code-audit` (which also holds the former AutoBot `dead-code-review`).
- **`debug`** (`autobot-dev-skills:debug`) — full-stack debugging across layers. Covers `debug-autobot`.
- **`engineering`** (`autobot-dev-skills:engineering`) — 20 domain lenses (backend, frontend, database, devops, performance, AI/ML, multimodal, testing, refactoring, architecture, planning, PRDs, design specs, documentation, content, sweeps, conversation compaction, memory capture and curation), one reference each. Invoke as `/autobot-dev-skills:engineering <lens>`.

## The agents

Seven model-pinned role agents in `plugins/autobot-dev-skills/agents/`, invoked as `autobot-dev-skills:<role>`. Each is a short router: hard constraints plus a table that loads the matching skill workflow.

| Agent | Model | Writes? | Routes to |
|---|---|---|---|
| `senior-developer` | sonnet | yes | `engineering` (build lenses), `lifecycle`, `debug`, `claude-dev-skills:coding` |
| `reviewer` | sonnet | no (read-only) | `review` lenses and PR review, `audit`, `claude-dev-skills:review-lenses` |
| `researcher` | fable | no (read-only; `gh issue create` only) | `lifecycle research`, `research-to-issues`, `adopt` |
| `planner` | fable | yes (docs/plans, never code) | `engineering` (planning lenses) |
| `writer` | sonnet | yes | `engineering` (documentation-engineer, content-writer) |
| `sweeper` | haiku | no (read-only) | `engineering` (repo-sweeper) |
| `memory` | sonnet | yes | `engineering` (memory-monitor, memory-curator, conversation-compacter) |

## Configuration

The `debug` skill (`references/debug-autobot.md`) reads service hosts from environment variables — export them from your deployment
before use, never hardcode addresses:

```bash
export REDIS_HOST=… NPU_HOST=… BROWSER_HOST=… AISTACK_HOST=…
```

## Layout

```
.claude-plugin/marketplace.json            the marketplace manifest
plugins/autobot-dev-skills/
  .claude-plugin/plugin.json               the plugin manifest
  skills/<meta>/SKILL.md                    router (decision table)
  skills/<meta>/references/<workflow>.md   full workflow, read on demand
  agents/<role>.md                         model-pinned role agent (auto-discovered)
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
