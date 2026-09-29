# Neutral Technical Slides: Content Guideline

Use this guideline for progress reports, design reviews, research meetings, and other technical decks built with the neutral-slides template. Template documentation defines page structure, available components, and production checks. This guideline defines what the deck should say and show.

## Plan

### Establish the decision and the reader

State what the audience must understand or decide after the deck. Include methods, evidence, results, constraints, and decision items that move them toward that state. Exclude self-evaluation, inflated claims, process narration, unexplained jargon, repetition, and maintenance detail that changes no method, measurement, or decision.

Identify the authoritative sources for direction, terminology, data, tables, and figures. Use secondary material only to fill a specific gap. Do not let code, logs, earlier decks, or a handoff reinterpret an established decision. Reuse approved wording, tables, and figures when they already express the required content. Check current sources for facts that can change.

Determine the deck's mode from primary evidence. If results are pending, omit result-dependent claims or retain a placeholder in the delivered deck explicitly marked pending. Such placeholders are exempt from evidence and density rules. Do not write a planned result as an observation.

### Build the floorplan before HTML

Keep the floorplan outside the deck, in `<artifact>.FLOORPLAN.md` beside the edit file. Update it before adding, splitting, or removing a slide. Include a term ledger that records every project-specific term and the page and element that defines it. Fix a missing or later definition before handoff.

Plan in three passes:

1. Inventory each candidate fact, its primary evidence, status, constraint, response, decision value, and exclusion reason.
2. Cluster facts by one causal chain, comparison, mechanism, or decision question. Do not choose slide count yet.
3. Give each cluster a title, one interrogative reader question, required evidence, observation, response, visual form, prerequisite, successor, and expected density.

Map every top-level section and sibling before authoring. Order sections by what the reader must know first. Put a method before the setup that exercises it, then show the result.

Do not require one section order for every technical deck. A useful progress-update sequence is Cover, Recap, Summary of Progress, Methods, Experimental Setup, Results, optional Discussion, and Next Plan. Treat it as an example because a design review, decision review, and research update answer different audience questions. When using it, Recap connects prior context to the result now needed, Summary of Progress contains only work and status since that context, and Next Plan is exactly one final slide with evidence-derived actions or an explicit statement that no next action is needed.

### Give each slide a contract

Each content slide owns one reader question and only the claims required to answer it. Choose a chain that matches the page:

- Status: `current state → evidence → constraint → response → decision`
- Method: `input → selection or transformation → executor → modification boundary → output`
- Result: `comparison conditions → fixed conditions → measurement → observed difference → response or decision question`

Give each claim one owner slide. Repeat it only to add a consequence or interpretation. A file, module, component, or broad topic is not a reader question. Verify the real connection before combining subjects.

Build one question chain per page. Each element answers the question raised before it, beginning with what the preceding page established. Source order does not define the chain. State what a reduction or transformation preserves and discards. Express the reader's new understanding without incidental names or counts. A defined named object under review may appear in the title and conclusion. If a page conflicts with an earlier establishment, resolve or report the conflict rather than writing around it.

## Write

### Align title, lead, evidence, and takeaway

Use a short noun phrase for the title. Name the page's object or comparison rather than its conclusion or an incidental source label. A defined API, file format, or dataset under review may name the page. Use a causal title only when the evidence distinguishes that cause from plausible alternatives. The title, central visual, and takeaway must support one proposition.

Every content slide has one short lead and one takeaway. The lead states the problem, comparison, or definition that makes the page necessary. It does not contain procedure, evidence, result, conclusion, or a count repeated below. The takeaway states the one conclusion supported by the visible content and adds no new evidence. The page chain is `problem or question → visible method or evidence → applied method or result`. Cover, contents, and divider pages are exempt.

### Write for a technical reader

Apply these tests to visible technical content and speaker sentences. Judge orientation labels and greetings by their page's purpose:

1. A first-time reader can understand it without project-specific context.
2. It distinguishes observations, definitions, assumptions, proposals, and pending work. Do not present a proposal as an established decision.
3. It avoids inflated scale, completion, abstraction, or importance.
4. It answers the page's reader question.

Keep field terms as the field writes them. Explain project-specific terms, choices, and measurements, and define field terms the audience may not know. Define an internal name where the reader first needs it. Prefer a common term and introduce a new term only when the explanation uses it. Use one name per object across the deck.

A concept page answers its reader question by linking two parts: what the concept is and is for in source-grounded general terms, and how the page's example uses it. A label or type signature alone is insufficient. A mechanism diagram can carry both parts when it shows their relationship. Show the concept's general scope as well as the instance.

Use text to label visual relationships. A short sentence or list may carry a simple relationship a diagram would not explain better. Name quantities rather than their typography or screen position. Write digits for counts. Separate numeric assignments clearly and reserve mathematical symbols for their mathematical meaning.

### Make evidence checkable

Report any conflict between approved material and current evidence without silently changing the approved decision or suppressing the observation. Name the source of a causal explanation. If that source has not been inspected, state only the observed value. When roles differ, identify the selector, executor, input state, modification boundary, and resulting state. Do not credit one component with calculations or mutations performed by another.

Record provenance during planning. Counts name what is counted and how groups form the total. Names presented as current project commands, paths, or implementations must exist there. Label external examples and proposed components as such. When reusing a published figure, preserve its identity and cite its number and source. A redraw with different conventions is a new figure.

Except for marked pending placeholders, every content page provides a visible check. A page that states measured or computed values keeps a counting or arithmetic check, such as a sum, subtraction, complete enumeration, source row, or set derived from a shown rule. A concept or design page may use a traceable mechanism diagram instead, with each drawn step traceable to its source or rule. If that page also states measured or computed values, those values still require counting or arithmetic checks. Remove an unsupported claim or mark it unresolved. A labeled illustrative example can explain a rule but cannot substitute for evidence of a measured result. Apply a rule to the whole drawn object, including the hard case, and make computed values recomputable from the shown inputs and rule. Trace measured values to the cited measurement or source row. A background page without arithmetic instead traces each factual item to a named source.

Distinguish measured, source-reported, assumed, and computed quantities. Keep calculation-only quantities as values or sentence terms unless their relationship or calculation is the claim. When a model is the claim, show its input and response. A difference between states shows both states and the difference. Draw a full curve only when its shape matters.

Pair each equation with plain-language meaning. For a multi-step definition, show one equation and its meaning per step. Name every computation input, output, and source. Give each symbol one role, distinguish assumed and solved values, and use the form required by each step rather than silently substituting one for the other. Define every term at first use or name its earlier defining object. Do not rely on a later definition. Use example values that a reader can interpret without project context and that participate in the page's example.

Make comparison rows the compared entities or conditions and order them by a meaningful key. State units once and identify sources when columns come from different measurements. Keep group-defining conditions with benchmark results. A full-page table must contain a complete comparison. Generate reported measurement results and their derived numbers from primary data and check them against the generator output. Label illustrative or assumed values and check their calculations separately. Mark pending measurements as pending and never present a provisional value as final.

### Use a visual grammar

Work out the drawing before prose for time change, spatial arrangement, branch, merge, loop, mechanism, sequence, or state change. If the relationship cannot yet be drawn, report the missing source or relationship and continue independent pages. Cut a second rendering of a mechanism the page's code or text already shows.

Map each relationship to its form:

- sequence to one directed path
- one input under conditions to a branch
- conditions entering one evaluation to convergence
- two methods to aligned inputs, stages, and outputs on shared axes
- hierarchy to a tree
- state mutation to before, action, and after
- exact comparison to a table or shared-axis chart
- independent peers to cards or bullets
- status to an evidence-to-action chain

Label an edge with its relation, such as movement, order, dependency, or connection, unless the diagram's convention already makes it clear. Put operations on their operands. For a process diagram, make start, next element, and destination clear from composition alone. Independent columns must be complete in their reading order. For a comparison, align corresponding items across columns and make the matching explicit. Reuse alignment, direction, shared axes, highlighted transformations, and input-output continuity when two pages show the same relationship.

Use one hand-checkable toy instance to explain a mechanism. Put per-case measurements and fitted plots on result pages. Draw an unchanged structure once with changing values together. Within one page, redraw only when structure changes. A later page may redraw a structure its reader question needs.

Every data or relationship figure has a caption that names what is drawn and the data it uses. Letter multiple figures in reading order so surrounding text can refer to them by label. Label alternatives, parts, and procedure stages at their blocks. Every figure-specific name, label, number, caption, and note must resolve to a clear visible referent, which may be a group of compared objects. Give each compared case an identifiable representation, which may share a drawing or axis with the other cases. Remove a figure note that has no visible referent or merely repeats the figure. Replace notation that requires a disclaimer.

### Keep information local and pages economical

A content page states one step and stops. Do not announce later pages or send the reader backward by slide position. Show an output where it is produced and its use where it is consumed. A deliberately unresolved question may point forward only to say where it will close. Refer backward by a named object. Move a page that requires a later value.

Complete one causal chain or comparison in one place. Keep a method's inputs, transformation, and result together. Keep changed and fixed variables together. Use previously defined terms consistently, but keep the evidence needed to check this page's count or comparison on this page. Merge adjacent fragments or redraw claim boundaries. Place detail beside the visual it changes.

A content slide needs an independent question, sufficient evidence, and a page-worthy visual. Cover, contents, and divider pages serve orientation and are exempt from content-density and evidence requirements. A subsection name does not qualify. Meaningful occupancy comes from answer-carrying text, data, diagrams, or images. Whitespace establishes grouping and hierarchy. For a roughly half-empty page, check whether its answer is complete. Only if incomplete, merge it without duplicating claim ownership, add missing evidence or explanation, or remove it. Marked pending placeholders are exempt from density and evidence requirements. Use available neighboring space before adding another slide.

Count only answer-carrying content as occupied space, even when a layout report marks a box as filled. An empty box is not information.

Fix overflow first by combining labels, clarifying column ownership, moving blocks, or separating an independent claim. Adjust font and padding only afterward. A change to wording, coordinates, or spacing alone does not require new claim boundaries. If the reader question, evidence chain, or claim ownership is wrong, restart claim clustering and floorplanning, then rerender the deck. Cosmetic edits do not close a structural defect.

### Write speaker scripts from the page

Write one speaker script for every page after its body is planned. Derive it from authoritative material and the page's owned claim. Ground technical statements in visible figures, names, numbers, and relationships. Greetings, transitions, and source citations supporting visible claims need not be drawn. Draw and make checkable any concept the speaker needs, or remove it. Do not put a new claim or number only in notes.

Begin each script paragraph with a square-bracketed unspoken direction that names the visible place and traversal order. Spoken sentences follow the closing bracket. The direction is not a topic label. Each paragraph speaks only to that place. Use complete sentences in the deck's spoken language. Do not add empty spacing paragraphs, page numbers, titles, or note labels. Keep the cover script to the opening and avoid repeating another page.

## Verify

Audit every rendered page as its intended reader. Repair each applicable failed check. Apply evidence, lead, and claim checks to content pages, with the pending-placeholder evidence exemption. Check cover, contents, and divider pages for their orientation purpose, scripts, and geometry:

1. Can the reader check measured or computed values by counting or arithmetic? On a concept or design page, can the reader trace each step of the mechanism diagram to its source or rule? On a background page without arithmetic, does each factual item trace to a named source?
2. Is each quantity identified as measured, source-reported, assumed, or computed, with its source or derivation?
3. Does each explanatory note have a clear referent, including a figure element, table column, or the page-wide claim it qualifies?
4. Is every project-specific term, figure value, and code example defined here or earlier?
5. Can the presenter explain the page by pointing rather than reading?
6. Are unchanged structures drawn once per page, with later reuse serving that page's reader question?
7. Does every element answer a question the reader has at that point?
8. Does the lead still describe the finished page?

For the last two checks, remove each element in thought. Cut it if the page loses nothing. Add visible support for any part of the lead left unanswered.

Check rendered geometry before accepting it:

- An embedded image keeps its source width:height. Compare the rendered image content's width:height with the source arithmetically, since flex stretch or a forced width can distort it despite correct markup. Exclude surrounding padding or letterboxing from the measured image area.
- Text and glyphs are never scaled non-uniformly, for example by a stretched SVG or a transform. Line wrapping that changes a text box's shape is not distortion.

Use the template's layout checks for clipping and overlap.

Keep content findings separate from production checks. A successful build, preserved edits, and clean geometry show that the artifact was produced as intended. They do not show that the explanation works.

## Review

When reporting a defect, name its type, inspect the relevant text and visual elements on every rendered page, and report the number of instances. One found example is not a deck-wide review. Report changes and remaining defects rather than search mechanics or dismissed candidates.

Treat a reviewer question as a request for an answer unless it explicitly requests a change. Read a correction for the understanding it requests rather than copying its words mechanically. Preserve requester-specified exact wording. If exact wording conflicts with another rule, report the conflict instead of silently changing it.

Within a requested fix, make every judgment needed to complete that fix. Align the lead and takeaway, remove repetition, add missing support, and repair another defect on the same page when it affects the requested result. Do not change unrelated pages. Report an out-of-scope defect with the rule it breaks.

If a fix cannot stay on one page because claim ownership or page assignment is wrong, identify the affected chain in the floorplan. If those pages are outside the authorized scope, request that scope before editing them. If the same reader question returns after revision, re-examine the explanation's structure, missing premise, and interpretation of the question rather than patching its wording again.

When a page can be regenerated from another source, carry every applied review change into that source before regeneration. Confirm afterward that the regenerated page still contains those changes.
