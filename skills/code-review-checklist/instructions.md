# Code Review Checklist

A review that lists everything technically improvable is noise. A review
that surfaces what would actually break, ranked by how badly, is signal.
Work through these dimensions, but only report what survives verification.

1. **Correctness.** Trace each changed code path against a concrete input
   or state. Does it handle the actual boundary conditions present in this
   codebase (empty collections, concurrent access, the specific error types
   the surrounding code already raises) -- not hypothetical ones that can't
   occur here?

2. **Security.** Check for injection (command, SQL, template), unsafe
   deserialization, secrets in code/logs, and missing authorization checks
   on anything that changes state or reads sensitive data.

3. **Simplification.** Is there a smaller diff that accomplishes the same
   thing? Flag unnecessary abstraction, premature generalization, or logic
   duplicated from elsewhere in the codebase that should be shared instead.

4. **Test coverage.** Does a new code path have a test that would fail if
   the logic were wrong? A test that only exercises the happy path when the
   change's whole point is an edge case is a coverage gap, not coverage.

5. **Consistency.** Does the change follow the codebase's existing
   conventions (naming, error handling, module boundaries) rather than
   introducing a new one for no stated reason?

Before reporting a finding, verify it against the actual code -- not
against what the diff looks like it does. Rank findings by real-world
severity (would this crash in production vs. is this a style nit), and
state the concrete failure scenario for each: what input or state makes it
go wrong. Acknowledge what the change does well; it calibrates how much
weight to give the criticism.
