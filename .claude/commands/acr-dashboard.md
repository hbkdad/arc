---
description: Start (or reuse) the ACR dashboard and open it -- the one-step launch this repo didn't have
---

ACR has no background service -- the dashboard is a local web server (`acr dashboard serve`) that only exists once something starts it, and blocks its terminal like any dev server. This command is that one step.

If the Browser pane tools are available in this session:

1. Call `preview_start` with `{"name": "acr-dashboard"}` -- `.claude/launch.json` already defines this entry (`uv run acr dashboard serve`, port 8765). It reuses an already-running instance rather than starting a duplicate.
2. Report the URL back to the user.
3. Do a quick real check that it's actually serving live data, not just that the process started: `read_console_messages` for errors, then `get_page_text` on the Overview page and confirm it shows something other than an error page. Don't fabricate what it shows -- report what's actually there (including "no tasks recorded yet" if that's genuinely the state).

If Browser pane tools are not available in this session (a plain terminal-only context), tell the user to run this themselves and report the URL once they confirm it's up:

```bash
uv run acr dashboard serve --open-browser
```

`--open-browser` opens their default browser automatically once the server is ready; omit it if they'd rather navigate to `http://127.0.0.1:8765` manually. This blocks the terminal it runs in by design (no daemon mode) -- either give it its own terminal, or background it themselves (`... &`, or a separate shell).
