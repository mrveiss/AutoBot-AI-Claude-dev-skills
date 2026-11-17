---
name: audit
description: Use to audit AutoBot-AI for unwired code or frontend/backend API drift (dead buttons, GUI 404s, unmounted routers, orphaned components), and as a completion gate before marking any frontend feature complete or changing any frontend API call, FastAPI route or router registration. Findings become wire-it-in issues, never deletions.
---

# Wiring & dead-code audits (router)

Invoke as `/autobot-dev-skills:audit <workflow> [args]`; the first argument selects the row; with no argument, pick the row from the situation. Read only the matching reference.

| Workflow | Situation | Read |
|---|---|---|
| `api-wiring-audit` | Frontend/backend API contract, unmounted router, 404 from GUI, before marking ANY frontend feature complete, any frontend API call / FastAPI route / router registration change | `references/api-wiring-audit.md` |
| `dead-code-audit` | Unregistered routers, uninvoked hooks, orphaned components, code that looks unused or commented out | `references/dead-code-audit.md` |
