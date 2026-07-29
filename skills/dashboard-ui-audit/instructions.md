# Dashboard UI Audit

A screenshot-first critique only catches what's visible in one viewport at
one moment. This procedure catches what a screenshot can't: dead CSS
classes, semantic gaps between similar-looking elements, and inconsistent
application of a design system that's fine in the parts you happen to look
at and broken in the parts you don't.

1. **Read the design tokens first.** Find the CSS custom properties (colors,
   spacing, type scale) defined once and reused everywhere. Note what
   semantic categories exist (status colors, severity levels) before judging
   any individual page.

2. **Read every template/component, not just the landing page.** Grep for
   the shared patterns (a status-badge class, a data-table wrapper, a
   metric-card component) across every page that uses them. A pattern
   correctly used on 9 pages and dropped on the 10th is a real, fixable
   inconsistency -- and it's invisible unless you check all 10.

3. **Cross-check every dynamically-set class against its CSS.** Anywhere
   JavaScript sets `className` or toggles a class based on runtime state
   (an error state, a loading state, a connection-lost state), confirm a
   CSS rule actually exists for it. A class set only in JS with no matching
   rule renders as unstyled text -- exactly the state a user most needs to
   notice (e.g. "something failed") silently loses its visual signal.

4. **Verify contrast and sizing computationally, not by eye.** If tooling
   allows executing JS in the page, compute real WCAG contrast ratios for
   text/background pairs rather than eyeballing them. Compute actual
   rendered/backing-store pixel dimensions for canvas or image elements
   instead of assuming CSS sizing behaves as intended.

5. **Check that a value styled one place is styled everywhere it appears.**
   If a status/severity value gets a color-coded badge in a table, and the
   same value is also summarized as a raw count elsewhere (a stat tile, a
   legend, a chart), confirm it carries the same semantic color there too.
   The most common gap is a design system that's correct in its component
   library but inconsistently *applied*.

6. **Report only verified findings.** Every finding must name the exact
   file, selector, or computed value that proves it, and a concrete fix.
   Distinguish confirmed bugs (a class with no CSS rule) from stylistic
   opinions (a color you'd have picked differently) -- lead with the former.
