# Production rules

## Preamble

These rules govern how authors build and check paged HTML documents. Read this document in full. Consult [COMPONENTS.md](COMPONENTS.md) by component for markup and layout reports. The configured content guideline governs what the document says and shows. References to neutral clauses below link to the [neutral content guideline](../guidelines/neutral/GUIDELINE.md).

## Article 1. Prepare the document

Keep the source and planning records ready for the next edit.

1.1 Keep the template's page geometry. Without a template, preserve the `main.pages` and `section.page` structure described in [README.md](README.md#without-a-template).

1.2 Keep `<artifact>.FLOORPLAN.md` beside the edit file and outside the deck. Follow neutral clause 3.2 for planning and updates. Include a term ledger naming the page and element that defines each unfamiliar term. Apply neutral clause 4.3 and fix missing or late definitions before handoff.

## Article 2. Build figures and tables

Fit content to its intended box while preserving its meaning and proportions.

2.1 For a contents page, try columns at full size before scaling to fit or fill the page.

2.2 Use the same units statement form on every slide that shows measurements. See `p.units` in [the table reference](COMPONENTS.md#tables-and-units).

2.3 Prefer inline SVG over a picture of a drawing when the other components do not carry the figure. Settle the figure's box first from the column width and the height left on the page. Give its `viewBox` those proportions and the size at which the figure is drawn, rather than a smaller box scaled up. Draw inside it. Lay out each panel for its own width and height while preserving grouping and reading order. When a page has one figure, size it for the available content area and readable detail rather than placing it in an unnecessarily small box.

2.4 Give raster figures a `max-height`. Preserve the source width to height ratio of images, including `<img>`, images inside SVG, and CSS backgrounds. At the intended display or export size, check the rendered image itself, excluding padding and letterboxing, for correct proportions and readable text and marks needed by the page. A clean layout report does not establish these qualities.

2.5 When a drafting tool accepts images, supply requested visual reference images as inputs. A description does not replace the images. Follow neutral clauses 3.1 and 5.10 for using references.

2.6 Use a plotting tool that supplies the required axes, scales, and annotations for a standard plot. Do not rebuild these by hand.

2.7 For diagrams of boxes and arrows, prefer horizontal and vertical connectors unless another route clarifies the relationship. Join connectors entering the same element near their sources. Split connectors leaving the same element near their targets. Keep branches short and the common segment long. Follow neutral clause 5.4 for direction, source and target relationships, entry and exit sides, and permitted merges. Remove a bend or detour when another permitted entry or exit side avoids it without changing reading order or intended connections, obscuring junctions, or adding crossings or label overlaps.

2.8 Set mathematical symbols and formulas as math markup using the forms in the component reference.

## Article 3. Check an edit

Check the rendered page and its layout before requesting independent review.

3.1 Render affected pages with `image()` and perform the configured content guideline's checks. Neutral Article 7 defines the scope and reading order of those checks.

3.2 Use `layout(artifact=..., page=...)` to check each affected page's errors. Consult [Layout check reports](COMPONENTS.md#layout-check-reports) to interpret the result. Read the returned blocks and free space only when the rendered page leaves a placement or spacing question unresolved.

## Article 4. Complete independent review

Use a reader who did not build the deck to find problems in the finished pages and spoken explanation.

4.1 Before handing off a new deck or a revision across the deck, complete independent review after `layout()` returns an empty `errors` list, the configured content guideline's Article 7 checks pass, and the author completes the request checks in neutral clauses 8.2 and 8.3. Run one review round by default, with another only at the requester's direction.

4.2 Use a reader who did not build the deck, such as a new agent or session. First give that reader the full rendered deck in reading order, either through the built deck or page images from `image()`, and the instruction in 4.4. Requested focus areas may set priorities but must not replace or restrict that instruction. After the reader records findings for all rendered pages, provide the scripts as text labelled by page for a second pass. Do not provide the guideline, template documentation, planning files, sources, other hidden notes, or an account of how the deck was made.

4.3 Record one row per finding in a table with columns `Page`, `Finding as stated`, `Kind`, `Decision`, and `Action or reason`. Use `wording`, `logic`, `inconsistency`, or `layout` for kind and `adopt`, `reject`, or `hold` for decision. Hold changes that alter meaning or structure for the requester's decision. Fix adopted findings, rerun your content and layout checks on affected pages, and include the table in the handoff report.

4.4 Copy this instruction to the reviewer:

```text
First review every supplied page as a reader, using only the rendered deck. Requested focus areas do not limit the checks below. Record which pages you read and your findings before requesting or reading the scripts. If earlier pages are missing, report prerequisite and repetition checks that cannot be completed. Limit your verdict to the pages and checks actually reviewed. Do not inspect markup or other hidden notes, consult other material, or edit the deck.
Identify the question each page answers and what the reader can conclude from it. If either is unclear, report that before individual wording defects.
Read for wording that interrupts understanding, including undefined terms, implementation names that replace needed explanations, phrases without an actor or action, and several terms used for one meaning. Read titles, leads, and takeaways in order for jumps, repetition, and conclusions without premises. On each page, check whether visible evidence supports the takeaway, how any difference used to justify it leads to the conclusion, whether comparisons identify both sides, and whether each visible citation clearly identifies the claim or evidence it refers to.
Always check for titles or takeaways that contradict figures, evaluative words such as sufficient, limited, or negligible without support on the page, later pages that repeat earlier ones, and contents or overviews that disagree with the body. Check for conflicting values of the same quantity under the same conditions, totals that do not add up, unexplained changes in units or periods, and values with no source or derivation that are not labeled illustrative or assumed.
Then review the supplied scripts in spoken order alongside their pages. Check that the presenter can speak from the page currently shown and the audience's established context. Flag previews of later titles or content not shown on that page. A forward reference may only locate the answer to a deliberately open question. A divider script should announce only its displayed section, and a contents script should introduce only its displayed organization. Check that each reference identifies what is being discussed, terms have clear and consistent meanings, and sentences follow the visible explanation without jumps or contradictions. For each sentence, check whether removing it would lose information or guidance the audience needs. A cover may include one short sentence recalling an earlier presentation or discussion to establish today's starting point. Preserve that orientation even when the audience already knows the recalled context. Judge the sentence's role, not only whether it adds new information. Flag unnecessary sentences, reasons, transitions, readings of visible text, and source recitation. Required source attribution belongs on the page. A spoken source name must help the audience distinguish whose evidence or settings are being discussed. For borrowed settings with a shared source, flag repeated spoken attribution unless it is needed to keep evidence or settings distinct. Check that the presenter states their own design choices as first person decisions using I or we accurately. Flag actorless passives that hide the decision maker, advance apologies, and wording that diminishes the presenter. Keep limitations and open items needed to judge the work visible as facts. Their spoken explanation must serve a necessary judgment about a claim or decision. Do not remove necessary qualifications or credit for another person's work. Before requesting an addition, identify what the audience cannot understand without it. Check that displayed measurements and calculated values are not read aloud, and that any spoken interpretation is needed, clear, and supported. Ratios and multiples may be spoken when they carry the explanation, including those computed from displayed values. A value that defines the rule itself may also be spoken when it carries the explanation. Keep the findings from the first pass even if the script explains what the page left unclear.
Seek at least three specific findings across both passes and order them by what to fix first. For each, give the page number, identify whether it concerns the page or script, quote the relevant text, and explain the problem. For conflicts across pages or between a page and its script, identify and quote both. Report only findings supported by the rendered pages or supplied scripts. If fewer than three are supported, report those and state that fewer were found.
```
