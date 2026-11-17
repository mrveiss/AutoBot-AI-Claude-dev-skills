---
name: review
description: Use for reviewing or validating PRs before merge: review cycle and merge decision, high-effort review fleet, pre-merge checks. Read the matching reference before acting.
---

# PR review & validation (router)

Invoke as `/autobot-dev-skills:review <workflow> [args]`; the first argument selects the row; with no argument, pick the row from the situation. Read only the matching reference.

| Workflow | Situation | Read |
|---|---|---|
| `review` | Review open PRs, work the review queue, CI diagnosis, merge decision, heartbeat tick with no assigned issue | `references/review.md` |
| `review-fleet` | High-effort / recall-biased PR review (10-angle finder + verifier fleet, one PR comment); auto-triggered by wake payloads `{"type": "pr_review", "effort": "high"}` or `{"type": "pr_review", "fleet": true}` | `references/review-fleet.md` |
| `pre-merge-validate` | Validate code before merging (syntax, imports, call-site impact, tests, types, lint) | `references/pre-merge-validate.md` |

Opening the PR itself: `/autobot-dev-skills:lifecycle pr`.
