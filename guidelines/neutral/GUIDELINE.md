# Neutral Technical Slides: Content Guideline

## Preamble

A deck exists so that its audience can understand or decide something. This guideline governs what a technical deck says and shows. Template documentation governs page structure, components, and production checks.

Work within the authorized scope. Within it, when rules pull in different directions, keep every claim accurate and checkable first, and then make the explanation understandable to its intended reader. If a requester's explicit constraint conflicts with either, report the conflict instead of silently changing the constraint or the content.

Each article states a principle, and its clauses are ways of meeting it. A clause governs every form of the situation it describes. Examples introduced with "such as" illustrate and never limit. Named forms such as the title, lead, takeaway, and script are defaults that serve the principles. Adapt a form that obscures meaning or repeats content rather than dropping needed explanation to satisfy it.

## Article 1. Purpose and the reader

Establish what the requester wants the reader to understand or decide, what that reader already knows, and what remains to be understood. Include what bridges that gap and nothing that does not.

1.1 State the deck's purpose and audience before planning. Derive each page's reader question from what the requester is trying to understand or decide, using the current request and the discussion it continues, not from the material available to present. When a follow-up changes the question, the current request governs.

1.2 Include only claims and evidence that answer the page's question. Do not substitute an answer to a different question because it is easier to measure, already documented, or already drawn.

1.3 Let the reader's question determine the level of detail. Include a detail only when the reader needs it to understand the explanation, assess the evidence, or act on it. Apply this test to details from source and working material as well, including internal names, file organization, tool operation, and intermediate outputs.

1.4 Include drafting, revision, or submission history only when the reader needs it to understand the content, assess its evidence, or act on it. Otherwise keep it in planning records.

1.5 Exclude self-evaluation, inflated claims, process narration, and maintenance detail that changes no method, measurement, or decision. Repeat established information only when the repetition serves a distinct need. Omit incidental names and counts that do not help the reader identify what matters, understand the explanation, assess the evidence, or act on it. Do not restate a visible count unless stating it serves one of those purposes.

## Article 2. Claims and evidence

Distinguish what is established, inferred, assumed, proposed, or unknown, and support each claim with the kind of evidence that establishes it.

2.1 Distinguish observations, definitions, assumptions, proposals, and pending work wherever they appear. Do not present a proposal as a decision or a planned result as an observation. Mark pending results as pending, and never present a provisional value as final.

2.2 Match each claim to the kind of source that establishes it: authoritative design descriptions for intended design, implementation sources for how something is built, and primary measurements or execution records for what happened. Use several kinds together when the question needs them, without letting evidence for one kind of claim stand in for another. Use secondary material only to fill a specific gap, and check current sources for facts that can change. Sources establish what is true. They do not decide what the page explains or how deeply.

2.3 Present a cause as established only when the evidence distinguishes it from plausible alternatives, and name the source of that evidence. Otherwise state the observation and label any explanation as proposed.

2.4 Give every content page a check the reader can perform. Measured or computed values come with a counting or arithmetic check, such as a sum, a difference, a complete enumeration, a source row, or a set derived from a shown rule. A mechanism or design page may instead offer a diagram whose every step traces to its source or rule. A background page traces each factual item to a named source. Remove a claim that has no such support, or mark it unresolved.

2.5 Identify every quantity as measured, source-reported, assumed, or computed, with its source or derivation. Generate reported results and their derived numbers from primary data and check them against the generator's output. Make computed values recomputable from the shown inputs and rule, and apply a rule to the whole object it describes, including the hard case. Counts name what is counted and how groups form the total. Label illustrative or assumed values and check their calculations separately. A labeled illustrative example may explain a rule but never stands in for evidence of a measured result.

2.6 Cite sources needed to support claims or interpret evidence, and credit borrowed material. Identify adaptations when material has been changed.

2.7 When several actors or components take part, identify which one selects, which one executes, what it receives, where its changes stop, and what state results. Do not credit one with the work of another. Names presented as existing commands, paths, files, or implementations must exist, and external examples and proposed components are labeled as such.

2.8 When approved material and current evidence disagree, report the conflict. Do not silently change the approved decision or suppress the observation, and do not let secondary material such as code, logs, earlier decks, or handoff notes reinterpret an established decision. Reuse approved wording, tables, and figures when they already express the required content.

## Article 3. Coherent explanation

Organize the explanation around the relationships the reader must understand, establish each prerequisite before relying on it, and leave no required relationship for the reader to reconstruct.

3.1 For an explanation spanning pages, orient the reader to the question being answered and develop the parts in the order needed to understand it. Make clear how each part builds on earlier explanations and contributes to the whole. Read the sequence as a whole and check that it answers the reader's question without relying on unstated relationships or on definitions introduced only after they are needed.

3.2 For each step needed to understand a process or method, show who acts, its inputs and outputs, and how its result determines what happens next. Where it branches, repeats, stops, or rejects an input, state the deciding condition and the resulting action rather than only naming the check.

3.3 Choose a chain that matches each page, such as `current state → evidence → constraint → response → decision` for status, `input → selection or transformation → executor → modification boundary → output` for a method, and `comparison conditions → fixed conditions → measurement → observed difference → response or decision question` for a result. Within a page, each element answers the question raised before it, starting from what earlier pages established. Source order does not define this chain. State what a reduction or transformation keeps and discards.

3.4 When a choice or omission affects what the reader must understand, state its reason: the goal or constraint it serves and how the chosen structure or behavior serves it.

3.5 Place each explanation where the reader first needs it. Answer a question that an element raises at that element or just before it. Show an output where it is produced and its use where it is consumed. Refer backward by a named object, never by page position, and do not announce later pages. A deliberately unresolved question may point forward only to say where it will close. Move a page that depends on a later value.

3.6 Give each claim one owner page, and repeat it elsewhere only to add a consequence or interpretation. A file, module, component, or broad topic is not a reader question. Verify a real connection before combining subjects. Resolve or report a conflict with an earlier page rather than writing around it.

3.7 Order sections by what the reader must know first. Distinguish prerequisite background from the subject being explained by each page's role in the current explanation, not by its source or novelty. Headings must accurately describe the role or subject of the content they label. Use subheadings or introductory text to clarify a broad, required heading, not to contradict it. By default, present a method before the setup that exercises it, and the setup before the observed results. No single section order suits every deck. For a progress update, a useful order is Cover, Recap, Summary of Progress, Methods, Experimental Setup, Results, optional Discussion, and Next Plan. When it is used, Recap connects prior context to the result now needed, Summary of Progress covers only work since that context, and Next Plan is exactly one final page of evidence-derived actions or a statement that none is needed.

3.8 A concept is explained by what it is and what it is for, in general terms grounded in a source, and by how the page's example uses it. Choose an example that shows the purpose as well as the working, keep the conditions that make it useful, and show the concept's general scope as well as the instance. A label or type signature alone does not explain a concept.

## Article 4. Meaning and reference

Choose wording by the meaning the intended reader can reasonably take in context, not by the meaning familiar to the author.

4.1 Every visible line and every spoken sentence is understandable to a first-time reader without project-specific context. This applies to titles, leads, takeaways, captions, labels, notes, source lines, and scripts alike.

4.2 Judge wording by the meaning the intended reader would reasonably take from the page and what came before it, not by what the author can explain was intended. For each action described, identify who performs it and what it acts on or produces, and for each relationship, the objects and how they relate. Revise wording that could lead to a materially different reading or that depends on information only the author has. Apply this to familiar words used in a technical sense as well as to specialized labels.

4.3 Use established terms directly when they are clear to the intended reader, in the field's own form, and familiar plain language otherwise. When identifying a particular item, use its displayed or previously established name. When defining it, state its kind and role in terms the reader can understand. Add explanations or groupings when they convey meaning the names alone do not.

4.4 Wording familiar from the author's code, notes, or discussions is not familiar to the reader. Do not use code names, literal translations, or labels coined while working as substitutes for explaining the object or action. Introduce an internal name only when the reader needs the name itself, and define it at first use. Define every term at its first use or name the earlier element that defines it, and never rely on a later definition. Check a legend, glossary, notation table, or other reference aid against the material it explains: each unfamiliar term or symbol needed to understand that material is explained there or earlier, and each entry clearly connects the label or symbol, its established name if any, and its meaning.

4.5 Use one term and one visual notation for one meaning throughout the deck. Give objects distinct names or explicit indices whenever the explanation relies on their difference, and preserve that distinction in the definitions and expressions built from them. Reduce notation only when no required distinction is lost. Build later explanations on meanings already introduced instead of defining them again.

4.6 Name quantities rather than their typography or screen position. Write digits for counts, keep numeric assignments visually separate, and reserve mathematical symbols for their mathematical meaning. Pair each equation with its meaning in words, one equation per step of a multi-step definition. Name every input, output, and source of a computation, give each symbol one role, and keep assumed and solved values distinct. Use example values the reader can interpret without project context, and make them participate in the page's example. Use the form required by each step rather than silently substituting assumed and solved values for one another.

4.7 In a deck organized into sections, format each content-page title as `<section name> — <page topic>`. Use a short noun phrase for the page topic, naming the page's object or comparison rather than its conclusion or an incidental source label. A defined API, file format, or dataset under review may name the page. The title, central visual, and takeaway support one proposition.

4.8 By default a content page has one short lead and one takeaway. The lead states the problem, comparison, or definition that makes the page necessary and contains no procedure, evidence, result, conclusion, or count repeated below. The takeaway states the one conclusion the visible content supports and adds no new evidence. Cover, contents, and divider pages are exempt.

4.9 Write prose without semicolons in slide text, captions, table cells, speaker scripts, and planning documents. Separate distinct statements and use an explicit conjunction when their relationship matters.

## Article 5. Form and relationships

Choose the form that makes the intended relationships and distinctions perceptible, and let nothing in the presentation imply a relationship the explanation does not support.

5.1 Work out the drawing before the prose whenever the content is a change over time, a spatial arrangement, a branch, a merge, a loop, a mechanism, a sequence, or a state change. If a relationship cannot yet be drawn, report what is missing and continue with independent pages. Do not add a second rendering of what the page's code or text already shows. Use short sentences or parallel list items for simple relationships that a diagram would not explain better.

5.2 Give each relationship the form that matches it, such as a directed path for a sequence, a branch for one input under conditions, convergence for conditions entering one evaluation, aligned inputs, stages, and outputs on shared axes for compared alternatives, a tree for a hierarchy, before-action-after for a state change, a table or shared-axis chart for an exact comparison, cards or bullets for independent peers, and an evidence-to-action chain for status. Label an edge with its relation unless the drawing's convention already makes it clear, and put operations on their operands.

5.3 Read the rendered drawing using its visual conventions. Follow each connection and check that its endpoints, exit and entry points, direction where applicable, and labels convey the intended relationship. For a flow, make its start, order, and destination clear from the drawing itself. Check that placement, spacing, and alignment make grouping and separation clear. Rework ambiguous paths and arrangements that suggest unintended relationships or hide intended ones. Complete independent columns in their own reading order. Align corresponding items across compared columns and make the matching explicit.

5.4 Compare approaches against the reader's goal and actual constraints. Before rejecting one for a limitation of its current presentation, check whether a different organization or form resolves that limitation without losing necessary content. Reuse an established way of explaining the same relationship when it helps the reader. Preserve required content and explicit constraints, but adapt reused material and its arrangement when they no longer serve the current explanation.

5.5 Explain a mechanism with one hand-checkable instance. When a model is the claim, show its input and response. Put per-case measurements and fitted plots on result pages. In any example, keep the conditions and relationships needed for the understanding it is meant to provide, and simplify details that do not contribute to that understanding. Draw an unchanged structure once with its changing values, and redraw it only when the structure changes or a later page's question needs it. Show both states and their difference for a change, draw a full curve only when its shape matters, and keep calculation-only quantities out of drawings unless their relationship is the claim.

5.6 Caption every data or relationship figure with what is drawn and the data it uses, and letter multiple figures in reading order. Every name, label, number, caption, and note in a figure resolves to a visible referent, and each compared case has an identifiable representation. Remove a note that has no referent or repeats the figure, and replace notation that needs a disclaimer.

5.7 In a comparison table, rows are the compared entities or conditions ordered by a meaningful key, units appear once, the source of each column is stated when columns come from different measurements, and group-defining conditions stay with the results. A full-page table holds a complete comparison.

5.8 Keep rendered content faithful. An embedded image keeps its source width-to-height ratio. Compare the rendered image content's width-to-height ratio with the source arithmetically, excluding surrounding padding or letterboxing. Text and glyphs are never scaled unevenly. Line wrapping that changes a text box's shape is not distortion.

## Article 6. Pages

Give each page one distinct contribution that the reader can take in at a readable size.

6.1 A content page answers one reader question with sufficient evidence and a page-worthy visual, then stops. Complete one causal chain or comparison in one place, keeping inputs, transformation, and output together and keeping changed and fixed variables together. Keep the evidence needed to check the page on the page.

6.2 Only content that carries the answer counts as occupied space, whatever a layout report says. Whitespace shows grouping and hierarchy. For a page that looks half empty, check whether its answer is complete. Only if incomplete, merge it without duplicating claim ownership, add missing evidence or explanation, or remove it.

6.3 Choose the page count that makes the explanation understandable, and group content by the question it answers rather than by available space. Before adjusting layout, check that the page answers one question with the definitions, evidence, and relationships it needs. Split independent questions. Divide an explanation too dense to read at a readable size into successive questions, each answered on its own page. Remove redundancy, but never shrink or cut needed explanation to fit a page count.

6.4 A change of wording, coordinates, or spacing alone does not create new claim boundaries. When the question, evidence chain, or claim ownership is wrong, restart planning for the affected explanation and recheck the affected pages. Cosmetic edits never close a structural defect.

6.5 Cover, contents, and divider pages serve orientation and are exempt from density and evidence requirements, as are marked pending placeholders.

## Article 7. Speaker scripts

Each page's script speaks to what the page shows and adds no claim the page does not carry.

7.1 Every page has one script, written after the page is planned and revised whenever its explanation changes. It is derived from the page's owned claim and authoritative material, grounded in what is visible, and never the only place a claim or number appears. A concept the speaker needs is drawn and checkable, or removed. Greetings, transitions, and source citations supporting visible claims need not be drawn.

7.2 Each script paragraph that explains visible content begins with a bracketed, unspoken direction naming the place on the page and the order to traverse it, and speaks only to that place. The direction is not a topic label. Write complete sentences in the deck's spoken language without spacing paragraphs, page numbers, titles, or note labels. The cover script is the opening only, and no script repeats another page.

## Article 8. Planning records

Plan before building and record sources, history, and decisions in the planning record. Include them on the page when required by Articles 1 and 2.

8.1 Plan outside the deck, in `<artifact>.FLOORPLAN.md` beside the edit file, and update it before adding, splitting, or removing a page. Record each page's reader question, its sources and revision history, and a term ledger naming the page and element that defines every project-specific term. Fix a missing or late definition before handoff.

8.2 Identify the authoritative sources for the deck's direction and terminology before inventorying candidate content. Plan in three passes. Inventory each candidate fact with its primary evidence and anything that affects its use. Cluster facts by one causal chain, comparison, mechanism, or decision question before choosing a page count. Give each cluster a title, one interrogative reader question, required evidence, observation, response, visual form, prerequisite, successor, and expected density.

8.3 Map every section and its siblings before writing. Determine from primary evidence whether results exist, and if they are pending, omit result-dependent claims or keep a marked placeholder. A local fix plans only the sections it affects and updates only their entries.

## Article 9. Verification and revision

Check the finished deck as its intended reader will meet it, and after any change, check everything that depends on what changed.

9.1 Audit every rendered page as its intended reader for a new deck or a deck-wide review. For any other change, including an edit, a deletion, a change of meaning, or a change to the system, configuration, or data the deck describes, audit the pages that carry or describe what changed, edited or not, and every page whose definitions, claims, summaries, examples, conclusions, or layout depend on it. Check them for newly missing information as well as contradictions, and preserve each page's level of detail.

9.2 On each content page, confirm that the reader can perform its check, that every quantity's kind and source are identified, that every note has a referent, that every term and value is understandable from what the reader has, that the presenter can explain the page by pointing, that unchanged structure is drawn once, that every element answers a question the reader has at that point, and that the lead still describes the finished page. Trace the reading order suggested by the rendered layout. At each element, check that the explanation needed to understand it is available there or has already been introduced.

9.3 Assess each element against the meaning already conveyed by the wording, visual structure, and conventions available to the reader. Remove it in thought and cut it if no information or guidance needed for the current question is lost. Apply the same test to each page against what earlier pages have established. Keep a page only if it contributes understanding or guidance needed for the current question that is not already available. When revising or removing a page, relocate any still-needed prerequisites and update dependent explanations. After moving, adding, or removing an explanation, recheck everything else that addresses the same point.

9.4 Repair each applicable failed check and add visible support for any part of the lead left unanswered. Check cover, contents, and divider pages for their orientation purpose, scripts, and geometry. Use the template's layout checks for clipping and overlap before acceptance.

9.5 Keep content findings separate from production checks. A clean build, preserved edits, and clean geometry show that the artifact was produced as intended, not that the explanation works.

## Article 10. Review

Answer what the reviewer asks, change what the reviewer asks to change, and restore the understanding the comment asks for.

10.1 Treat a reviewer's question as a request for an answer unless it explicitly asks for a change. Preserve wording the requester explicitly specifies as exact, and report a conflict between that wording and another rule instead of silently changing it.

10.2 Before answering or editing, read the comment together with the discussion it continues and the material it refers to. Identify its subject and what it asks you to explain, propose, or change, and keep the distinctions it makes without reinstating what it rejects. If materially different readings remain, ask one focused question.

10.3 An edit makes the requested understanding available where the reader needs it. Adding requested words or removing a criticized term is not enough. After editing, read the affected explanation in order against the original comment. Within a requested fix, make every judgment the fix needs, including repairs on the same page that affect it, and do not change unrelated pages. Report an out-of-scope defect with the rule it breaks and the pages checked.

10.4 Answer the question directly and state the change's status briefly. Add only what the reviewer needs to assess the change or decide the next step, such as a change not visible on the page, a departure from the request, or work left undone.

10.5 Within the authorized scope, place requested content where the reader needs it and respect explicit placement constraints. Do not assume that an existing page must absorb the addition. Redistribute material or add pages when understanding requires it, and ask before exceeding the scope or an explicit page limit. If the same question returns after revision, re-examine the explanation's structure, missing premise, and reading of the question rather than patching its wording again.

10.6 Before regenerating any page from another source, carry every applied review change into that source, and confirm afterward that the regenerated page keeps them.

10.7 A deck-wide defect review names each defect type, inspects every rendered page for it, and reports the count. One example found is not a deck-wide review. Report changes and remaining defects, not search mechanics.
