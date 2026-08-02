# Local Business / Trades Web Design Methodology

This is the process behind real shipped client sites (a drilling/well
contractor, an industrial-B2B campaign, a rider/lifestyle merch brand) --
a raw/industrial/trade-native visual system, not a generic SaaS or
agency template. Each project looked distinct because each client's
brand facts were real; this is the reusable *process*, not one client's
palette.

## First move: read or create the project's own MASTER.md

Look for `design-system/MASTER.md` or `CLIENT_HANDOFF.md` in the target
project. If present, it is the source of truth for that client's real
brand facts (pricing, voice, assets) and overrides everything below. If
absent on a new client project, create one before writing component
code -- filled with real client facts, never invented placeholders.
Never let a "premium redesign" quietly replace a client's real brand
with a generic one; the improvement is fidelity, accessibility,
conversion, SEO, and performance, not brand replacement.

## Anti-patterns (the actual differentiator)

Ban, per client, with their real palette substituted in: cyan/blue tech
glow accents, purple-to-blue gradient heroes, beige/tan generic
lifestyle palettes, stock imagery when real photos exist, fabricated
logos/testimonials/brand facts, corporate-audit language leaking into
customer copy ("conversion system," "platform," "enterprise"), a generic
circular icon replacing a real logo mark, and the same "safe" font
pairing (e.g. Inter everywhere) used on any other project.

## Color and type architecture

One `:root` CSS custom-property token block -- colors, fonts, radii,
shadows, spacing -- consumed everywhere, never a hardcoded value inside
a component. Display font: heavy/condensed/impact, matching the
industry's own register (industrial, moto/rider, trade). Body font: a
clean neutral sans, never the same family as the display face, never
all-caps. Dark-based palette by default for these industries, one or
two saturated accents max. Heading scale via `clamp()` so hero text
never overflows mobile.

## Component structure, in order

Header (sticky, real logo, primary CTA, mobile nav) -> Hero
(brand-native headline + real photo/video + 1-2 CTAs) -> proof/price/
trust (visible before the form) -> product/service detail cards (real
content, real states) -> lead/quote/order form (the actual conversion
point) -> story/proof/media (real, never fabricated) -> footer (real
pages and contact channels only, no private links exposed).

## Motion, forms, accessibility

Motion: fast and useful, never decorative-only; respect
`prefers-reduced-motion`; content visible even if animation fails.
Forms: never placeholder-only inputs, state exactly what happens after
submit, repeat the trust statement near the submit button. Accessibility:
one `<h1>`, semantic landmarks, visible focus states, `aria-label` on
icon-only controls, `aria-pressed` on toggled state, real alt text,
muted-by-default video, computed (not assumed) contrast on the actual
palette used, no horizontal overflow on mobile.

## SEO, performance, handoff

Keep structured data in sync with visible copy/pricing. Optimize media
(webp/avif, lazy-load below the fold, no eager-loaded video galleries).
Keep JS bundle growth intentional. On finishing new client work, write
or update `CLIENT_HANDOFF.md`: live URL, host, repo, customer flow,
contact channels, page map, analytics events, and a maintenance
checklist -- written for the client to read, not as engineering notes.
