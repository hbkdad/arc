---
description: Real health/usage snapshot of this ACR instance -- doctor checks, per-provider spend, memory calibration
---

Run these three commands from the repo root and report a concise summary (a few sentences plus any real problems found -- don't just paste raw output):

```bash
uv run acr doctor
```

```bash
uv run acr models usage
```

```bash
uv run acr memory calibration
```

For each:
- `acr doctor`: call out any check that isn't `ok`, with its detail.
- `acr models usage`: state real call counts/cost per provider. If a provider shows zero calls, say so plainly rather than omitting it.
- `acr memory calibration`: state the Brier score and whether any bin's predicted confidence diverges meaningfully from its actual success rate. If there's not enough recorded evidence yet, say that plainly instead of treating "no data" as "healthy."

Do not fabricate numbers -- if a command errors, show the real error and stop there rather than guessing at what it would have said.
