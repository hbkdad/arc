# UI Design Critique

Vague feedback ("this looks off") isn't actionable. Structured feedback
tied to a specific principle and a concrete fix is. Work through these five
dimensions in order; not every dimension will have a finding, and that's a
valid outcome for a dimension, not a reason to invent one.

1. **First impression.** What draws the eye first, and is that the right
   thing? Is the page's purpose clear within a couple of seconds, with no
   need to read supporting text?

2. **Usability.** Can the user actually accomplish the task the page
   exists for? Are interactive elements obviously interactive? Are there
   steps that could be removed?

3. **Visual hierarchy.** Is there a clear reading order? Is whitespace
   doing real work, or is it just gaps? Are the most important elements
   the most visually emphasized ones, or is emphasis going somewhere less
   important?

4. **Consistency.** Does this page follow the same design system (colors,
   spacing, type scale, component patterns) as the rest of the product?
   Flag *specific* deviations -- a component styled differently from its
   siblings, a color used outside its established semantic meaning.

5. **Accessibility.** Check contrast ratios against WCAG thresholds where
   verifiable rather than eyeballing them, touch target sizes, and whether
   state (error, success, warning) is conveyed by more than color alone.

For each finding: name the element, name the principle, state severity
(critical/moderate/minor), and give a specific fix -- not just a diagnosis.
Always note what already works well; a critique that's 100% negative is as
uninformative as one that's 100% praise.
