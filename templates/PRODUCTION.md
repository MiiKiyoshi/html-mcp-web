# Production rules

Neutral clauses cited below are in the neutral guideline of the artifact's layout, [neutral-slides](../guidelines/neutral-slides/GUIDELINE.md) for a deck and [neutral-report](../guidelines/neutral-report/GUIDELINE.md) for a report, which number the clauses they share alike.

## Article 1. Plan the document

1.1 Keep the template's page geometry. Without a template, preserve the `main.pages` and `section.page` structure described in [README.md](README.md#without-a-template).

1.2 Keep the planning records of neutral clause 2.8 in `<artifact>.FLOORPLAN.md` beside the edit file.

## Article 2. Build page content

Fit content to its box at a readable size, preserving its proportions. When it does not fit, distribute it under neutral clause 2.6 rather than shrinking it.

2.1 For a contents page, try columns at full size before scaling the list down to fit the page.

2.2 Put a table's shared information once in `p.units`, directly above the table and aligned to its right edge: its units, any metric shared by all value columns, any value shared by all rows under neutral clause 5.9, and any needed key to cell notation.

Use the same placement for a plot's keys to marks that do not identify data series and for brief metric definitions needed to read table or plot values under neutral clauses 4.3 and 5.8. A metric's defining equation goes in the page text before the visual, not in `p.units`. Keep data series legends with the plot. See [units and notation keys](KITS.md#article-4-tables-and-units).

2.3 For a drawing you make, prefer inline SVG over a picture of it when other components do not carry it. A figure reused unchanged under neutral clause 2.3 stays an image.

Size the figure's box for readable detail and the relationships it must show, within the column width and height available on the page. Give its `viewBox` the box's proportions and the size at which the figure is drawn, rather than a smaller box scaled up. Draw inside it. Lay out each panel for its own width and height while preserving grouping and reading order. Compute crossings, arrow ends, and label positions rather than estimating coordinates by eye.

2.4 Give raster figures a `max-height`. Preserve the source width to height ratio of images, including `<img>`, images inside SVG, and CSS backgrounds. At the intended display or export size, check the rendered image itself, excluding padding and letterboxing, for correct proportions and readable text and marks needed by the page. A clean layout report does not establish these qualities.

2.5 When a tool or agent that drafts a figure accepts images, give it the requested visual reference images. Follow neutral clauses 2.2 and 5.10 for using references.

2.6 Use a plotting tool that supplies the required axes, scales, and annotations for a standard plot. A plot made this way is a drawing you make under 2.3.

2.7 For diagrams of boxes and arrows, prefer horizontal and vertical connectors unless another route clarifies the relationship. Join connectors entering the same element near their sources. Split connectors leaving the same element near their targets. Keep branches short and the common segment long. Follow neutral clause 5.4 for direction, source and target relationships, entry and exit sides, and permitted merges. Remove a bend or detour when another entry or exit side avoids it without changing reading order or intended connections, obscuring junctions, or adding crossings or label overlaps.

2.8 Set mathematical notation under neutral clause 4.6 using the forms in [KITS.md](KITS.md#article-6-math) Article 6. Define only the symbols an equation introduces whose meaning it does not show, not the quantity it defines, in a bulleted HTML list directly below it. For an equation inside a panel or column, keep the list inside that panel or column. Begin each definition with the symbol or expression in inline math, followed by a colon and its meaning under neutral clause 4.3.

2.9 Show source attribution on a page only through `<ol class="references">` entries and their `<cite>` markers, as described in [references and citations](KITS.md#article-7-references-and-citations).

2.10 For the bullets below a visual under neutral clause 5.8, use HTML lists outside SVG, images, or tables, in the same column as that visual.

## Article 3. Check an edit

3.1 Render affected pages with `image()`, with `grayscale=false` when colour is in question, and perform the content guideline's checks in the scope and order of neutral Article 7.

3.2 Use `layout(artifact=..., page=...)` to check each affected page's errors. Consult [layout check reports](KITS.md#article-11-layout-check-reports) to interpret the result. Read the returned blocks and free space only when the rendered page leaves a placement or spacing question unresolved.

3.3 A suggestion applied from the viewer is written only into the edit file. Regenerating from a script or an earlier copy loses it unless that source also contains the change. Before regenerating a page, carry applied review changes into its source and check that they survive regeneration.

## Article 4. Complete independent review

4.1 Before handing off a new document or a revision across the document, run one independent review round. First bring all of the following to hold:

1. `layout()` returns an empty `errors` list,
2. the checks of neutral Article 7 pass,
3. for work answering a review request, the requirements gathered under neutral clause 8.1 are met.

When one cannot be brought to hold, run the round anyway and report what remains under neutral clause 9.1. Run another round only at the requester's direction.

4.2 The independent reviewer is a reader who did not build the document, such as a new agent or session. First give it:

1. the full rendered document in reading order, as page images from `image()` or the built document viewed in a browser, never its markup,
2. the text of [REVIEWER.md](REVIEWER.md), copied verbatim,
3. the audience's knowledge and, when it differs, the presenter's,
4. the applicable requester decisions under neutral clause 1.5, each with its scope, leaving out author preferences and explanations of the document,
5. any focus areas the requester named.

After the independent reviewer records findings for all rendered pages, give any scripts as text labelled by page. Do not give the guideline, template documentation, planning files, sources, or other hidden notes.

4.3 Record the independent reviewer's comprehension blockers, then its incidental form observations, in two separate tables, one row per finding, with columns `Page`, `Finding as stated`, `Kind`, `Decision`, and `Action or reason`. Use `missing`, `wording`, `logic`, `inconsistency`, `unneeded`, or `layout` for kind and `adopt`, `reject`, or `hold` for decision.

Decide each finding that adds or removes content by neutral clause 1.4 at the audience's knowledge, recording what only the presenter needs as presenter notes under neutral clause 2.8. Repair adopted findings in the order of neutral clause 8.3. Besides findings held under neutral clause 8.2, hold for the requester's decision one whose fix would change a claim's meaning or exceed the editing scope of neutral clause 1.5. Regrouping pages alone is not held. Rerun your content and layout checks on affected pages, and include both tables in the handoff report.
