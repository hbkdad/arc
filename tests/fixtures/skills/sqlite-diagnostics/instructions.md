# SQLite Diagnostics

1. Run `PRAGMA integrity_check;`.
2. If FTS5 tables are present, run `PRAGMA quick_check;` on them too.
3. Summarize findings, citing the exact PRAGMA/query used for each claim.
