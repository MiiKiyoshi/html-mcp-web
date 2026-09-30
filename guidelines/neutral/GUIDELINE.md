# Neutral Technical Slides: Content Guideline

Use this guideline for progress reports, design reviews, research meetings, and other technical decks built with the neutral-slides template. Template documentation defines page structure, available components, and production checks. This guideline defines what the deck should say and show. When rules pull in different directions, keep claims accurate and checkable, the explanation understandable, and the work within the authorized scope. Title, lead, takeaway, and script forms are defaults that serve those aims. Adapt one that obscures meaning or repeats content rather than dropping needed explanation to satisfy it.

## Plan

### Establish the decision and the reader

State what the audience must understand or decide after the deck. Include methods, evidence, results, constraints, and decision items that move them toward that state. Exclude self-evaluation, inflated claims, process narration, unexplained jargon, repetition, and maintenance detail that changes no method, measurement, or decision.

Identify the authoritative sources for direction, terminology, data, tables, and figures. Match sources to the claim being explained. Use authoritative design descriptions for intended design, implementation sources for how a system is constructed, and primary measurements or execution records for observed results. Use these sources together when needed to answer the reader's question, without substituting evidence for a different kind of claim. Use sources to establish the explanation, not to choose its level of detail. Explain the decisions, transformations, inputs, outputs, and governing constraints needed to answer the reader's question. Include implementation details, such as source file and function names or code structure, only when they are needed to understand those relationships, interpret the evidence, or perform the reader's task. Their presence in the source alone is not a reason to include them. Use secondary material only to fill a specific gap. Do not let code, logs, earlier decks, or a handoff reinterpret an established decision. Reuse approved wording, tables, and figures when they already express the required content. Check current sources for facts that can change.

Determine the deck's mode from primary evidence. If results are pending, omit result-dependent claims or retain a placeholder in the delivered deck explicitly marked pending. Such placeholders are exempt from evidence and density rules. Do not write a planned result as an observation.

### Build the floorplan before HTML

Keep the floorplan outside the deck, in `<artifact>.FLOORPLAN.md` beside the edit file. Update it before adding, splitting, or removing a slide. Include a term ledger that records every project-specific term and the page and element that defines it. Fix a missing or later definition before handoff. A local fix plans only the sections it affects and updates only their floorplan entries.

Plan in three passes:

1. Inventory each candidate fact with its primary evidence and any status, constraint, response, decision value, or exclusion reason that affects its use.
2. Cluster facts by one causal chain, comparison, mechanism, or decision question. Do not choose slide count yet.
3. Give each cluster a title, one interrogative reader question, required evidence, observation, response, visual form, prerequisite, successor, and expected density.

Map every top-level section and sibling before authoring. Order sections by what the reader must know first. Distinguish prerequisite background from the method, design, or findings being explained, based on each page's role in the current explanation rather than its source or novelty. Headings must accurately describe the role or subject of the content they label. Use subheadings or introductory text to clarify a broad, required heading, not to contradict it. Put a method before the setup that exercises it, then show the observed results.

Do not require one section order for every technical deck. A useful progress-update sequence is Cover, Recap, Summary of Progress, Methods, Experimental Setup, Results, optional Discussion, and Next Plan. Treat it as an example because a design review, decision review, and research update answer different audience questions. When using it, Recap connects prior context to the result now needed, Summary of Progress contains only work and status since that context, and Next Plan is exactly one final slide with evidence-derived actions or an explicit statement that no next action is needed.

### Give each slide a contract

Derive each content page's reader question from what the requester is trying to understand or decide, rather than from the material available to present. Read follow-up requests with the preceding exchange to determine whether they continue the same question or change it. Include only claims and evidence that answer that question. Do not substitute an answer to a different question merely because it is easier to measure or already documented. Choose a chain that matches the page:

- Status: `current state → evidence → constraint → response → decision`
- Method: `input → selection or transformation → executor → modification boundary → output`
- Result: `comparison conditions → fixed conditions → measurement → observed difference → response or decision question`

For a method explained across pages, establish the overall problem and flow, then develop its parts in the order the reader needs to understand them. Each page should build on what is already established and make clear how its new explanation fits into that flow. Read the sequence as a whole and check that the reader can explain how the method reaches its result, without supplying missing relationships from the source or a later page. At each step needed to understand the method, show who acts, what is received and produced, and how the result determines what happens next. Where execution branches, repeats, stops, or rejects an input, state the deciding condition and the resulting action rather than only naming the check.

Give each claim one owner slide. Repeat it only to add a consequence or interpretation. A file, module, component, or broad topic is not a reader question. Verify the real connection before combining subjects.

Build one question chain per page. Each element answers the question raised before it, beginning with what the preceding page established. Source order does not define the chain. State what a reduction or transformation preserves and discards. Express the reader's new understanding without incidental names or counts. A defined named object under review may appear in the title and conclusion. If a page conflicts with an earlier establishment, resolve or report the conflict rather than writing around it.

Compare presentation alternatives by how well they serve the reader's question and the requester's stated purpose. Distinguish necessary content from choices that can be adjusted, such as which element carries a statement or where a block goes, and do not reject an explanatory approach because of a placement that can be changed. Reuse an established way of explaining the same relationship when it helps the reader, adapting the layout to the current content.

## Write

### Align title, lead, evidence, and takeaway

For a deck organized into sections, format each section's content-page title as `<section name> — <page topic>`. Use a short noun phrase for the page topic, naming the page's object or comparison rather than its conclusion or an incidental source label. A defined API, file format, or dataset under review may name the page. Use a causal title only when the evidence distinguishes that cause from plausible alternatives. The title, central visual, and takeaway must support one proposition.

By default, each content slide has one short lead and one takeaway. The lead states the problem, comparison, or definition that makes the page necessary. It does not contain procedure, evidence, result, conclusion, or a count repeated below. The takeaway states the one conclusion supported by the visible content and adds no new evidence. The page chain is `problem or question → visible method or evidence → applied method or result`. Cover, contents, and divider pages are exempt.

### Write for a technical reader

Apply these tests to all visible text, including captions, notes, and source lines, and to speaker sentences. Judge orientation labels and greetings by their page's purpose:

1. A first-time reader can understand it without project-specific context.
2. It distinguishes observations, definitions, assumptions, proposals, and pending work. Do not present a proposal as an established decision.
3. It avoids inflated scale, completion, abstraction, or importance.
4. It answers the page's reader question.

Choose terms that convey the intended meaning without misleading the reader in context. Use established field terms in the field's own form for technical concepts and familiar plain language otherwise. When an established term is clear to the intended reader, use it directly rather than replacing it with a longer everyday paraphrase. Explain unfamiliar terms without replacing their names. When defining an element, use the established term for its kind rather than a vague substitute, and explain its role in the example. Assess wording by the meaning the intended reader would reasonably take from the page and earlier explanations, not by whether the author can explain what they intended. If that reading could misrepresent the object, action, or relationship, revise the wording or supply the missing context. Apply this check to familiar words used technically as well as to specialized labels. Do not assume that wording familiar from the author's code, notes, or discussions is familiar to readers, and do not use code names, literal translations, or labels coined while working as substitutes for explaining the object or action. Use an internal name or introduce a new term when readers need the name itself, and define it at first use. When referring to specific elements shown on the page, such as fields in a code block or parts of a figure, use their displayed names. Add a paraphrase or grouping only when it explains something those names alone do not. Explain field terms the audience may not know and project-specific measurements. For design choices needed to understand the page, explain the goal or constraint they serve and how the chosen structure or behavior supports it.

A concept page answers its reader question by linking two parts: what the concept is and is for in source-grounded general terms, and how the page's example uses it. Choose an example that shows what the concept is for as well as how it works. Keep the conditions and relationships that make it useful, and simplify details that do not contribute to that understanding. A label or type signature alone is insufficient. A mechanism diagram can carry both parts when it shows their relationship. Show the concept's general scope as well as the instance.

Use text to label visual relationships. A short sentence or list may carry a simple relationship a diagram would not explain better. Name quantities rather than their typography or screen position. Write digits for counts. Separate numeric assignments clearly and reserve mathematical symbols for their mathematical meaning.

### Make evidence checkable

Report any conflict between approved material and current evidence without silently changing the approved decision or suppressing the observation. Name the source of a causal explanation. If that source has not been inspected, state only the observed value. When roles differ, identify the selector, executor, input state, modification boundary, and resulting state. Do not credit one component with calculations or mutations performed by another.

Record provenance during planning. Counts name what is counted and how groups form the total. Names presented as current project commands, paths, or implementations must exist there. Label external examples and proposed components as such. When reusing a published figure, preserve its identity and cite its number and source. A redraw with different conventions is a new figure.

Except for marked pending placeholders, every content page provides a visible check. A page that states measured or computed values keeps a counting or arithmetic check, such as a sum, subtraction, complete enumeration, source row, or set derived from a shown rule. A concept or design page may use a traceable mechanism diagram instead, with each drawn step traceable to its source or rule. If that page also states measured or computed values, those values still require counting or arithmetic checks. Remove an unsupported claim or mark it unresolved. A labeled illustrative example can explain a rule but cannot substitute for evidence of a measured result. Apply a rule to the whole drawn object, including the hard case, and make computed values recomputable from the shown inputs and rule. Trace measured values to the cited measurement or source row. A background page without arithmetic instead traces each factual item to a named source.

Distinguish measured, source-reported, assumed, and computed quantities. Keep calculation-only quantities as values or sentence terms unless their relationship or calculation is the claim. When a model is the claim, show its input and response. A difference between states shows both states and the difference. Draw a full curve only when its shape matters.

Pair each equation with plain-language meaning. For a multi-step definition, show one equation and its meaning per step. Name every computation input, output, and source. Give each symbol one role, distinguish assumed and solved values, and use the form required by each step rather than silently substituting one for the other. Define every term at first use or name its earlier defining object. Do not rely on a later definition. Use example values that a reader can interpret without project context and that participate in the page's example.

Make comparison rows the compared entities or conditions and order them by a meaningful key. State units once and identify sources when columns come from different measurements. Keep group-defining conditions with benchmark results. A full-page table must contain a complete comparison. Generate reported measurement results and their derived numbers from primary data and check them against the generator output. Label illustrative or assumed values and check their calculations separately. Mark pending measurements as pending and never present a provisional value as final. When a table explains notation, make each symbol, its established name if any, and its meaning easy to distinguish. Check the table together with the material it explains so that the notation needed to understand that material is defined there or earlier in the deck.

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

Label an edge with its relation, such as movement, order, dependency, or connection, unless the diagram's convention already makes it clear. Put operations on their operands. For a process diagram, make start, next element, and destination clear from composition alone. Choose connector exit and entry points that make the direction of flow easy to follow. Trace each connector on the rendered diagram and reroute it if unnecessary bends or cramped spacing obscure its path or make separate blocks appear joined. Independent columns must be complete in their reading order. For a comparison, align corresponding items across columns and make the matching explicit. Reuse alignment, direction, shared axes, highlighted transformations, and input-output continuity when two pages show the same relationship.

Use one hand-checkable toy instance to explain a mechanism. Put per-case measurements and fitted plots on result pages. Draw an unchanged structure once with changing values together. Within one page, redraw only when structure changes. A later page may redraw a structure its reader question needs.

Every data or relationship figure has a caption that names what is drawn and the data it uses. Letter multiple figures in reading order so surrounding text can refer to them by label. Label alternatives, parts, and procedure stages at their blocks. Every figure-specific name, label, number, caption, and note must resolve to a clear visible referent, which may be a group of compared objects. Give each compared case an identifiable representation, which may share a drawing or axis with the other cases. Remove a figure note that has no visible referent or merely repeats the figure. Replace notation that requires a disclaimer.

### Keep information local and pages economical

A content page answers one reader question and stops. Do not announce later pages or send the reader backward by slide position. Show an output where it is produced and its use where it is consumed. A deliberately unresolved question may point forward only to say where it will close. Refer backward by a named object. Move a page that requires a later value.

Complete one causal chain or comparison in one place. Keep a method's inputs, transformation, and output together. Keep changed and fixed variables together. Use established terms and visual notation consistently across the deck. Build later explanations on meanings already introduced instead of defining them again. Keep the evidence needed to check this page's count or comparison on this page. Merge adjacent fragments or redraw claim boundaries. Place an explanation where the reader needs it in the reading sequence. When a specific element raises a question needed to understand what follows, answer it at that element or immediately before it, rather than making the reader continue past dependent content to find the answer. Trace the reading order suggested by the rendered layout and check, at each element, whether the explanation needed to understand it is available there or has already been introduced.

A content slide needs an independent question, sufficient evidence, and a page-worthy visual. Cover, contents, and divider pages serve orientation and are exempt from content-density and evidence requirements. A subsection name does not qualify. Meaningful occupancy comes from answer-carrying text, data, diagrams, or images. Whitespace establishes grouping and hierarchy. For a roughly half-empty page, check whether its answer is complete. Only if incomplete, merge it without duplicating claim ownership, add missing evidence or explanation, or remove it. Marked pending placeholders are exempt from density and evidence requirements. Choose page count to make the explanation understandable, rather than treating the existing count as fixed. Group content by the reader question it answers, not by available space.

Count only answer-carrying content as occupied space, even when a layout report marks a box as filled. An empty box is not information.

Before adjusting layout, check whether the page answers one reader question with the definitions, evidence, and relationships needed to understand it. Split independent questions into separate pages. If one explanation remains too dense to follow at a readable size, divide it into successive questions, each answered completely on its own page. Remove redundancy, but do not shrink content or remove needed explanation merely to fit the current page count. A change to wording, coordinates, or spacing alone does not require new claim boundaries. If the reader question, evidence chain, or claim ownership is wrong, restart claim clustering and floorplanning for the affected explanation, then rerender and check the affected pages. Cosmetic edits do not close a structural defect.

### Write speaker scripts from the page

Every page has one speaker script, written after its body is planned and revised when the page's explanation changes. Derive it from authoritative material and the page's owned claim. Ground technical statements in visible figures, names, numbers, and relationships. Greetings, transitions, and source citations supporting visible claims need not be drawn. Draw and make checkable any concept the speaker needs, or remove it. Do not put a new claim or number only in notes.

Begin each script paragraph that explains visible content with a square-bracketed unspoken direction that names the visible place and traversal order. Spoken sentences follow the closing bracket. The direction is not a topic label. Each such paragraph speaks only to that place. Use complete sentences in the deck's spoken language. Do not add empty spacing paragraphs, page numbers, titles, or note labels. Keep the cover script to the opening and avoid repeating another page.

## Verify

For a new deck or a deck-wide review, audit every rendered page as its intended reader. For a local fix, audit the changed pages and inspect any other pages whose definitions, claims, or shared layout the change affects. When another page summarizes or illustrates changed content, check whether it still answers its reader question accurately and sufficiently. Check for newly missing information as well as contradictions, and preserve the page's level of detail when addressing either. Repair each applicable failed check. Apply evidence, lead, and claim checks to content pages, with the pending-placeholder evidence exemption. Check cover, contents, and divider pages for their orientation purpose, scripts, and geometry:

1. Can the reader check measured or computed values by counting or arithmetic? On a concept or design page, can the reader trace each step of the mechanism diagram to its source or rule? On a background page without arithmetic, does each factual item trace to a named source?
2. Is each quantity identified as measured, source-reported, assumed, or computed, with its source or derivation?
3. Does each explanatory note have a clear referent, including a figure element, table column, or the page-wide claim it qualifies?
4. Can the intended reader understand each term, figure value, and code example using established meanings and the explanations given here or earlier? Could any wording still lead them to misunderstand the intended object, action, or relationship in that context? Check short forms such as leads, takeaways, captions, and labels using only the context available to the audience. For each action described, identify who performs it and what it applies to or produces. For each relationship described, identify the objects involved and how they are related. Compare these readings with the intended meaning. Revise wording that could reasonably lead to a materially different understanding in that context or depends on information only the author has.
5. Can the presenter explain the page by pointing rather than reading?
6. Are unchanged structures drawn once per page, with later reuse serving that page's reader question?
7. Does every element answer a question the reader has at that point?
8. Does the lead still describe the finished page?

For the last two checks, assess each element against what the page already shows and what earlier pages have established. Remove it in thought and cut it if nothing needed to answer the current reader question is lost. After moving or adding an explanation, recheck the remaining text and visuals that address the same point, keeping them only if they still serve a distinct purpose needed on that page. Add visible support for any part of the lead left unanswered.

Check rendered geometry before accepting it:

- An embedded image keeps its source width:height. Compare the rendered image content's width:height with the source arithmetically, since flex stretch or a forced width can distort it despite correct markup. Exclude surrounding padding or letterboxing from the measured image area.
- Text and glyphs are never scaled non-uniformly, for example by a stretched SVG or a transform. Line wrapping that changes a text box's shape is not distortion.

Use the template's layout checks for clipping and overlap.

Keep content findings separate from production checks. A successful build, preserved edits, and clean geometry show that the artifact was produced as intended. They do not show that the explanation works.

## Review

For a deck-wide defect review, name each defect type, inspect the relevant text and visual elements on every rendered page, and report the number of instances. One found example is not a deck-wide review. Report changes and remaining defects rather than search mechanics or dismissed candidates.

Treat a reviewer question as a request for an answer unless it explicitly requests a change. Preserve requester-specified exact wording. If exact wording conflicts with another rule, report the conflict instead of silently changing it.

Before answering or choosing an edit, read the comment together with the discussion it continues and the material it refers to. Identify the subject and what the reviewer is asking you to explain, propose, or change. Check that your interpretation and response preserve the distinctions the reviewer makes and do not reinstate what they explicitly reject. If the exchange leaves materially different readings unresolved, ask a focused clarification. When editing, make the requested understanding available where the reader needs it, rather than merely adding requested words or removing a criticized term. After editing, read the affected explanation in order and check it against the original comment. The change is complete when it resolves the requested issue while preserving the explanation's purpose.

Answer the reviewer's question directly and confirm the requested change's status briefly. Add only what the reviewer needs to assess the change or decide what happens next, such as a change not visible on the page, a departure from the request, or work left undone. Do not repeat page content or list edits unless needed to answer the question or explicitly requested.

Within a requested fix, make every judgment needed to complete that fix. Align the lead and takeaway, remove repetition, add missing support, and repair another defect on the same page when it affects the requested change. Do not change unrelated pages. Report an out-of-scope defect with the rule it breaks and the pages checked.

Within the authorized content scope, redistribute material or add pages when needed to make the explanation understandable, and update the floorplan. Ask before changing content outside that scope or exceeding an explicit page limit. If the same reader question returns after revision, re-examine the explanation's structure, missing premise, and interpretation of the question rather than patching its wording again.

When a page can be regenerated from another source, carry every applied review change into that source before regeneration. Confirm afterward that the regenerated page still contains those changes.
