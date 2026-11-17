---
name: audit
description: Use to audit AutoBot-AI for unwired code or frontend/backend API drift (dead buttons, 404s from the GUI, unmounted routers, orphaned components), and as a completion gate for any frontend API or router change. Findings become wire-it-in issues, never deletions.
---

# Wiring & dead-code audits (router)

Read the one reference whose situation matches; do not read the rest.

| Situation | Read |
|---|---|
| Frontend/backend API contract, unmounted router, 404 from GUI, before marking any frontend feature complete | `references/api-wiring-audit.md` |
| Unregistered routers, uninvoked hooks, orphaned components, code that looks unused or commented out | `references/dead-code-audit.md` |
