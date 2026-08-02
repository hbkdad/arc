# New Dashboard Page Layout and Interaction Design

ACR's dashboard is server-rendered Jinja2 + a single CSS-custom-property
token system (`--bg --surface --surface-2 --line --ink --ink-dim --accent
--accent-ink --wire --ok --warn --danger --info`, `--radius`, `--mono`).
Its own stated design rule: plain tables, no charting library, no JS
framework -- "the dashboard must remain useful without advanced
graphics." JavaScript exists on exactly one prior mutating page
(`/settings`): a vanilla-JS `fetch()` POST with a JSON body, then a
full-page redirect to a GET URL on success (not live client-side DOM
patching). Every other page is a plain server-rendered GET.

Propose a layout for the NEW page described in the objective. Your
proposal must specify:

1. **Page regions** -- name each concrete area (e.g. "a left sidebar
   listing X, a right panel showing Y, a form at the bottom"), not vague
   "make it clean" language.
2. **Which existing CSS classes it reuses** versus what's genuinely new
   -- `.table-wrap`/`table`, `.metric-grid`/`.metric-card`,
   `.settings-card`/`.settings-field`, `.pill` + `pill_class` filter,
   `.empty`, `.lede`, `.btn-primary`. Only propose new CSS where none of
   these already fit the shape of the content.
3. **The mutation pattern**, if the page has one -- match `/settings`'s
   precedent exactly unless there's a concrete reason not to: vanilla JS
   `fetch()` with a JSON body, a CSRF Origin-header check on the
   server route (a present-but-mismatched `Origin` rejected, a missing
   one allowed), then redirect to a GET URL on success. State plainly if
   you're deviating from this and why.
4. **Where it lives in nav** -- which existing `nav-group` in the
   sidebar it belongs under, or whether it needs a new one.
5. **Empty state** -- what renders before there's any data, matching the
   `.empty` treatment used elsewhere (e.g. `events.html`'s "No events
   match.").

Ground every choice in this being a dense, operational tool used by one
local developer, not a consumer product -- legibility and consistency
with the existing nine pages matter more than novelty for its own sake.
