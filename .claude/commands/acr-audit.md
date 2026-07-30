---
description: Full quality gate -- ruff, pyright, pytest with coverage -- and a real summary of what's failing or under-covered
---

Run, from the repo root, in this order (stop and report immediately if any step fails rather than continuing past a broken gate):

```bash
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest --cov=acr --cov-report=term-missing -q
```

Report:
- Whether each step passed or failed, with the real error output for any failure (not a paraphrase).
- From the coverage report: any module below 90%, with the specific missing line ranges. For each one, note briefly whether it looks like real untested business logic worth a test, or an external-failure branch (missing CLI tool, network error, etc.) that's low-value to chase.
- Do not propose or make any code changes as part of this command -- it's a report, not a fix. If the user wants fixes, that's a separate follow-up.
