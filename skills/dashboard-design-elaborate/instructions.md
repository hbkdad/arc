# Elaborate Dashboard Design Direction

ACR's operational dashboard is entirely token-driven: every component
(tables, pills, metric cards, charts, nav) reads its colors from CSS
custom properties on `:root`, never a hardcoded value. Two themes exist
today by redefining the same token set:

- **Default** — warm parchment/ink, a calm data-desk aesthetic
  (`--bg:#F2EEE3`, `--accent:#A8571F`, serif-adjacent restraint).
- **Neo Cyber** — near-black with neon cyan/violet accents, CRT
  scanlines, glow shadows on the accent and danger colors.

Propose a **third** theme in the same spirit: elaborate, upscale,
frontier-tier -- the kind of visual identity a well-funded AI lab's
internal tooling would actually ship, not a generic dark-mode palette.
Avoid the AI-generated-design defaults: no warm cream + terracotta, no
lone neon-on-black with no other idea, no purple-to-blue gradient hero,
no Inter-as-safe-choice.

Your proposal must give exact, implementable values for every one of
these tokens (hex colors):

`--bg --surface --surface-2 --line --ink --ink-dim --accent --accent-ink
--wire --ok --warn --danger --info`

Plus:
1. **Typography** — a specific display/heading typeface and a specific
   body typeface (real font names), and why they fit the direction.
2. **One concrete texture/layout idea** — something implementable in
   pure CSS (a background pattern, a border treatment, a glow/shadow
   recipe, a corner-radius philosophy) that gives the theme a real
   point of view, the way Neo Cyber's scanline overlay does.
3. **A one-sentence name and thesis** for the theme.

Ground every choice in the fact that this is a *dense, information-heavy
operational dashboard* (real tables, real charts, pills, status
indicators) — legibility and a working light/dark contrast ratio matter
more than atmosphere for its own sake. Never propose a color you
couldn't also justify passing WCAG AA contrast against its paired
background token.
