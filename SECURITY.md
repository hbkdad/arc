# Security Policy

ACR is pre-1.0, local-first software (see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
for current status). There is no supported-versions matrix yet — please
report against the current `main` branch.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, use GitHub's private vulnerability reporting for this repository:

1. Go to the [Security tab](https://github.com/hbkdad/arc/security).
2. Click **Report a vulnerability**.

This opens a private draft advisory visible only to the maintainer until
it's resolved and (optionally) published.

## Scope

Relevant areas given ACR's security model (master spec §37-41, §1122-1191):

- Permission/capability checks (`acr.security.permissions`) being bypassable
- Safe mode (`acr.security.safe_mode`) not actually blocking a mutating
  operation it claims to block
- Secrets (API keys, tokens) leaking into logs, telemetry, or memory records
  (`acr.security.secrets`)
- Prompt-injection detection (`acr.security.injection`) being trivially
  evadable in a way that leads to a real security consequence, not just a
  missed heuristic match (the scanner is explicitly a best-effort heuristic,
  not a guarantee — see its module docstring)
- Anything that lets untrusted content (retrieved memory, fetched web pages,
  GitHub search results) execute code or exfiltrate data

## Not a vulnerability report

General bugs, feature requests, and questions belong in
[GitHub Issues](https://github.com/hbkdad/arc/issues) instead.
