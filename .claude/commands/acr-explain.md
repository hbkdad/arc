---
description: Replay a real task's telemetry trail -- provider, tokens, duration, event sequence
argument-hint: <task-id>
---

Run `uv run acr explain $ARGUMENTS` from the repo root and report what it shows: objective, final status, which provider handled it, token counts, total duration, and the chronological event sequence. If the task id doesn't exist, say so plainly -- don't guess at what a valid task might have looked like.

If `$ARGUMENTS` is empty, there's no dedicated `acr tasks` list command -- instead query the real `tasks` table directly (e.g. `sqlite3 data/acr.db "select id, objective, status, created_at from tasks order by created_at desc limit 10"`, adjusting the db path from `acr doctor`'s output if it differs) to show recent task ids so the user can pick one, rather than failing silently.
