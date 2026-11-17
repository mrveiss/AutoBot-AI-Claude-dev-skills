---
name: review
description: Use for reviewing or validating PRs before merge (review cycle, merge decision, high-effort fleet, pre-merge checks) and for read-only review lenses - code quality, failure modes, security audit. Read the matching reference before acting.
---

# PR review & validation (router)

Invoke as `/autobot-dev-skills:review <workflow> [args]`; the first argument selects the row; with no argument, pick the row from the situation. Read only the matching reference.

| Workflow | Situation | Read |
|---|---|---|
| `review` | Review open PRs, work the review queue, CI diagnosis, merge decision, heartbeat tick with no assigned issue | `references/review.md` |
| `review-fleet` | High-effort / recall-biased PR review (10-angle finder + verifier fleet, one PR comment); auto-triggered by wake payloads `{"type": "pr_review", "effort": "high"}` or `{"type": "pr_review", "fleet": true}` | `references/review-fleet.md` |
| `pre-merge-validate` | Validate code before merging (syntax, imports, call-site impact, tests, types, lint) | `references/pre-merge-validate.md` |
| `code-reviewer` | Review fresh or modified Python/Vue/TypeScript for quality, performance, maintainability (MUST enforce the pre-commit workflow) | `references/code-reviewer.md` |
| `code-skeptic` | Pre-deploy or new code: failure modes, edge cases, bugs, architectural risk | `references/code-skeptic.md` |
| `security-auditor` | Vulnerability analysis, whole-codebase security audit, compliance (a diff-only review is the `secreview` project skill) | `references/security-auditor.md` |

Opening the PR itself: `/autobot-dev-skills:lifecycle pr`.
