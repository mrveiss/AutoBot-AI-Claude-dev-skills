---
name: engineering
description: Use for AutoBot domain work - backend, frontend, data, infra, performance, AI/ML, testing, refactoring, planning, docs, sweeps and memory. The playbooks behind the role agents; read the matching reference before acting.
---

# Engineering (router)

Invoke as `/autobot-dev-skills:engineering <workflow> [args]`; the first argument selects the row; with no argument, pick the row from the situation. Read only the matching reference in full before acting; its "When to use" line is the trigger.

| Workflow | Situation | Read |
|---|---|---|
| `senior-backend-engineer` | Backend performance, architecture, Redis pooling, complex backend issues | `references/senior-backend-engineer.md` |
| `frontend-engineer` | Vue 3 + TypeScript UI, WebSocket integration, dashboards | `references/frontend-engineer.md` |
| `database-engineer` | SQLite / ChromaDB / Redis Stack schema, migrations, queries, backups | `references/database-engineer.md` |
| `devops-engineer` | Docker, Redis Stack ops, NPU worker deployment, OpenVINO, scaling | `references/devops-engineer.md` |
| `performance-engineer` | Profiling, optimisation, monitoring, NPU/multimodal performance | `references/performance-engineer.md` |
| `ai-ml-engineer` | LLM providers, RAG, vector ops, ChromaDB tuning, NPU acceleration | `references/ai-ml-engineer.md` |
| `multimodal-engineer` | Vision, voice, screen analysis, cross-modal workflows | `references/multimodal-engineer.md` |
| `testing-engineer` | Test strategy, automation, E2E, multimodal / NPU validation | `references/testing-engineer.md` |
| `code-refactorer` | Structure, naming, duplication cleanup with no behaviour change | `references/code-refactorer.md` |
| `systems-architect` | Distributed-system redesign, scaling patterns, technology choices | `references/systems-architect.md` |
| `project-manager` | Planning, sprints, task breakdown, release coordination | `references/project-manager.md` |
| `project-task-planner` | Turn a PRD into a structured development task list | `references/project-task-planner.md` |
| `prd-writer` | Write a Product Requirements Document | `references/prd-writer.md` |
| `frontend-designer` | Mockups / wireframes to specs, component architecture, design-system docs | `references/frontend-designer.md` |
| `documentation-engineer` | `docs/`, API and code documentation, documentation standards | `references/documentation-engineer.md` |
| `content-writer` | Articles and blog posts (outline mode, write mode) | `references/content-writer.md` |
| `repo-sweeper` | Read-only mechanical sweeps (PR/CI status, branches, links, hit counts) | `references/repo-sweeper.md` |
| `conversation-compacter` | Compact a long conversation to a ~300-token summary | `references/conversation-compacter.md` |
| `memory-monitor` | Capture new memory entries (append-only) | `references/memory-monitor.md` |
| `memory-curator` | Remove, rewrite, merge or correct existing memory entries | `references/memory-curator.md` |

## Notes

- Reviewer lenses (`code-reviewer`, `code-skeptic`, `security-auditor`) live in `/autobot-dev-skills:review`; the research-only issue-tree workflow is `/research-hub to-issues` (KarnakOS-private-skills).
- Issue, commit and deploy mechanics are in `/autobot-dev-skills:lifecycle`; this skill holds domain knowledge only.
- Project rules in the repo `CLAUDE.md` override anything in a reference.
