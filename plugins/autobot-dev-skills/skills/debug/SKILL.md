---
name: debug
description: Use for any AutoBot failure whose layer is unknown, any cross-layer symptom, or when a fix in one layer did not hold. Dispatches per-layer investigators and synthesises one root cause.
---

# Full-stack debugging (router)

Invoke as `/autobot-dev-skills:debug <workflow> [args]`; the first argument selects the row; with no argument, pick the row from the situation. Read only the matching reference.

| Workflow | Situation | Read |
|---|---|---|
| `debug-autobot` | Any AutoBot bug (Vue, FastAPI, Redis, ChromaDB, NPU, Browser, AI Stack), unknown layer, or a fix that did not hold | `references/debug-autobot.md` |
