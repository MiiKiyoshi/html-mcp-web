# Neutral Technical Slides: Content Guideline

## Preamble

A deck helps its reader understand or decide something. This guideline governs what a technical deck says and shows. Template documentation governs page structure, components, and production checks.

Work within the authorized scope. Within it, make the intended explanation understandable to its reader as a condition of acceptance. Ground stated claims and reported values, and apply the level of detail and fidelity needed to answer the reader's question. If a requester's explicit constraint conflicts with either of these, report the conflict instead of silently changing the constraint or the content.

Each article gives a principle and rules for applying it. Apply a rule wherever its conditions hold. Examples illustrate a rule, not its limits. Named forms, such as titles, leads, takeaways, and scripts, are defaults. If a form obscures meaning or repeats content, adapt the form. Do not cut needed explanation to preserve it.

## Article 1. Answer the reader's question

Establish what the requester wants the reader to understand or decide. Find what the reader already knows, retain the field terms they understand, and include only what closes the gap.

1.1 State the purpose, audience, and intended use before planning. For a live presentation, make the explanation followable at the speaker's pace without requiring the audience to read dense text while listening. Derive each page's question from what the requester wants to understand or decide. Use the current request and its discussion, not available material. If a follow-up changes the question, follow the current request.

1.2 Include only claims and evidence that answer the page's question. Do not answer a different question because it is easier to measure, documented, or drawn.

1.3 Let the question set the detail. Include a detail only to help the reader understand, assess evidence, or act. Apply this test to source and working material, including internal names, file organization, tool operation, and intermediate outputs.

1.4 Keep drafting, revision, and submission history in planning records. Include it on a page only when the reader needs it to understand, assess evidence, or act.

1.5 Cut self-evaluation, inflated claims, and process narration. Cut maintenance detail that changes no method, measurement, or decision. Repeat established information only for a distinct need. Keep incidental names and counts only when they help the reader identify what matters, understand, assess evidence, or act. Apply the same test before restating a visible count.

## Article 2. Support each claim

Distinguish established facts, inferences, assumptions, proposals, and unknowns. Use evidence that establishes the kind of claim being made.

2.1 Distinguish observations, definitions, assumptions, proposals, and pending work wherever they appear. Do not present a proposal as a decision or a planned result as an observation. Mark pending results. Do not present provisional values as final.

2.2 Match the source to the claim. Use authoritative design descriptions for intended design, implementation sources for how something is built, and primary measurements or execution records for what happened. If the question needs several source types, use them together. Do not substitute one kind of evidence for another. Use secondary material only to fill a specific gap. Check current sources for facts that can change. Sources establish truth, not the page's question or level of detail.

2.3 Establish a cause only with evidence that distinguishes it from plausible alternatives. Name that evidence's source. Otherwise, state the observation and label the explanation as proposed.

2.4 Give every content page a check the reader can perform. For measured or computed values, show a counting or arithmetic check. Examples include a sum, difference, full enumeration, source row, or set derived from a shown rule. A mechanism or design page can use a diagram with every step traced to a source or rule. On a background page, trace each factual item to a named source. Remove unsupported claims or mark them unresolved.

2.5 Identify each quantity as measured, source-reported, assumed, or computed. Give its source or derivation. Generate reported results and derived numbers from primary data, then check them against the generator's output. Show the inputs and rule needed to recompute a value. Apply each rule to the whole object, including the hard case.

2.6 For each count, name the items counted and how groups form the total. Label illustrative and assumed values, and check their calculations separately. For conceptual curves and diagrams, verify the relationships a reader would infer, including ordering, crossings, and relative size when it conveys the relationship being explained. Require exact proportions only when they are needed to answer the page's question. Support these relationships with a source or an appropriate check, and state the conditions on which they depend. Omit unsupported relationships. Labeling a drawing conceptual does not make them valid. An illustrative example can explain a rule, but cannot serve as evidence of a measured result.

2.7 Cite sources needed to support claims or interpret evidence. Attribute a rule or claim to its primary source, not to the repository or summary used to obtain it. Include only the source details needed to identify the source or qualify the claim. Credit borrowed material. If you change it, say that it is adapted.

2.8 When several actors or components take part, identify their roles. Show who selects, who executes, what each actor receives after any selection or transformation, the limits of its changes, and the resulting state. Do not credit one actor with another's work. Check that commands, paths, files, and implementations presented as existing do exist. Label external examples and proposed components.

2.9 If approved material and current evidence disagree, report the conflict. Do not silently change the approved decision or suppress the observation. Do not let secondary material reinterpret an established decision. This includes code, logs, earlier decks, and handoff notes. If approved wording, tables, or figures express the required content, reuse them.

## Article 3. Connect the explanation

Show the relationships the reader needs to understand. Establish each prerequisite before using it. Do not leave needed relationships for the reader to reconstruct.

3.1 Before drafting an explanation that spans pages, state its question and work backward from the understanding the later pages require to plan a connected path from what the reader already knows. At each step, identify the reader's next question and how the words and drawing will answer it at that page's level of explanation. Show how each part builds on earlier explanations and contributes to the whole. Read the whole sequence to check that it answers the reader's question. Check for unstated relationships and definitions given only after they are needed.

3.2 For each needed process step, show the actor, inputs, outputs, and how the output determines the next step. For a branch, repeat, stop, or rejected input, state the condition and resulting action. Naming the check is not enough.

3.3 Choose a chain that fits the page. For example:

- Status: `current state → evidence → constraint → response → decision`
- Method: `input → selection or transformation → executor → modification boundary → output`
- Result: `comparison conditions → fixed conditions → measurement → observed difference → response or decision question`

Start from what earlier pages established. Each element answers the question raised before it. Source order does not set this chain. State what a reduction or transformation keeps and discards.

3.4 If a choice or omission affects understanding, explain why. Name its goal or constraint and how the chosen structure or behavior serves it.

3.5 Put an explanation where it is first needed. Answer a question at the element that raises it, or just before. Show an output where it is produced and its use where it is consumed. Refer to the object itself, not the title or location of an earlier explanation. At each use, include only the prior information needed to follow the current explanation without looking elsewhere or recalling details no longer visible. Do not announce later pages, except to say where a deliberately open question will close. Move a page that depends on a later value.

3.6 Give each claim one owner page. Repeat it elsewhere only to add a consequence or interpretation. A file, module, component, or broad topic is not a reader question. Check that a real connection exists before combining subjects. Resolve or report a conflict with an earlier page.

3.7 Order sections by what the reader must know first. Distinguish background from the subject by its role in this explanation, not its source or novelty. Make headings match the content's role or subject. Use subheadings or introductory text to clarify a broad required heading, not contradict it. By default, put the method before its experimental setup, then the observed results.

3.8 Choose the section order for the deck. A progress update can use this sequence:

Cover → Recap → Summary of Progress → Methods → Experimental Setup → Results → optional Discussion → Next Plan.

In this sequence, Recap connects prior context to the result now needed. Summary of Progress covers only work since that context. Next Plan is exactly one final page with evidence-derived actions or a statement that none is needed.

3.9 Explain the problem a concept solves for this reader and what it represents. Connect its defining condition or operating rule to that purpose at the page's intended level of explanation. When the reader needs an intuitive explanation to follow equations or an algorithm, establish the concept first and let the formal explanation build on its names and drawing. In that introduction, both writing and review should first make the intended relationships easy to see and follow, accepting simplifications that preserve those relationships and remain consistent with the formal explanation. For conceptual drawings, check the relationships being explained rather than requiring measured curve shapes, timing offsets, or proportional lengths, unless their exact form is needed to answer the page's question. Keep the names of the cases being compared, and ground stated claims and reported values. Omit notes about how a drawing departs from measured data unless they help the reader understand the intended explanation. When the reader needs to understand why a model or representation is used instead of a simpler one, show what the simpler one misses, why that matters for the intended result, and how the chosen one accounts for it. Compare them under conditions that isolate the stated difference. Ground the concept's general definition in a source. Choose an example that shows both purpose and operation. At the page's level of explanation, keep the conditions that make the concept useful and show its scope beyond the example. A label or type signature is not an explanation.

## Article 4. Make the meaning clear

Judge wording by what the reader understands in context, not by what the author intended.

4.1 Make every visible line and spoken sentence understandable without prior project context. This includes titles, leads, takeaways, captions, labels, notes, source lines, and scripts. Judge each line by the meaning a first-time reader gets from it and earlier explanations. Correct wording that suggests a materially different meaning or depends on information only the author has. Check familiar words used technically as well as specialized labels.

4.2 For each action, identify the actor and what it acts on or produces. Name each step so the reader can identify its object and operation at the level being explained. Avoid broad labels such as 'calculation' alone, and do not name a whole step after an internal substep that hides its purpose or result. When explaining a special case, describe the condition and its effect in terms the reader uses for the subject. Include the implementation mechanism only when it is needed to answer the reader's question. Do not replace an implementation condition with a domain explanation unless their correspondence is supported. For each relationship, identify the objects and how they relate. If the reader knows an established field term, use its usual form. Otherwise, use familiar plain language.

4.3 To identify an item, use its displayed or established name. To define it, explain its kind and role. If names alone do not convey the meaning, add explanations or groupings.

4.4 Do not assume readers know wording from your code, notes, or discussions. Do not use code names, literal translations, or working labels in place of an explanation. Introduce an internal name only when the reader needs the name itself.

4.5 Define each unfamiliar term at first use. At later uses, make its meaning clear from the established terminology and the local context. Never rely on a later definition. Check each legend, glossary, or notation table against what it explains. Explain every needed unfamiliar term or symbol there or earlier. Connect each entry's label or symbol to its meaning and any established name.

4.6 Use one term and one visual notation for each meaning throughout the deck. When the explanation needs to distinguish a particular kind, or the requester specifies a qualified name, use that name consistently in text and figures. Do not drop the qualifier on the assumption that an earlier definition makes it clear at every use. Give objects distinct names or explicit indices whenever the explanation relies on their difference. Preserve those names and symbols, and the distinction they express, in subsequent definitions, comparisons, calculations, and decisions. Simplify notation only without losing a required distinction. Build on earlier meanings instead of defining them again.

4.7 Name quantities, not their typography or screen position. When a quantity describes a relationship between objects, make that relationship clear in its name or local context. For a path quantity, identify the relevant source, destination, or direction where needed. Do not use endpoint ownership wording when it obscures that relationship. Use digits for counts. Separate numeric assignments visually. Reserve mathematical symbols for mathematical meanings. Pair each equation with its meaning in words, with one equation per step of a multi-step definition.

4.8 Name every input, output, and source in a computation. Give each symbol one role and distinguish assumed values from solved values. Use the form each step requires, without silently substituting one for the other. Use example values that need no project context and take part in the page's example.

4.9 For a deck with sections, use `<section name> — <page topic>` for each content-page title. Use a short noun phrase that identifies this page's specific subject within its section. Use the established name for that subject, and distinguish a detail from the whole it belongs to. Name the object or comparison, not the conclusion or an incidental source label. A defined API, file format, or dataset under review can name the page. Make the title, central visual, and takeaway support the same point.

4.10 By default, give each content page one short lead and one takeaway. The lead states the problem, comparison, or definition that makes the page necessary. Keep procedure, evidence, results, conclusions, and counts repeated below out of it. The takeaway states the one conclusion supported by the visible content and adds no evidence. Cover, contents, and divider pages are exempt.

4.11 Separate distinct statements in slide prose, captions, table cells, scripts, and planning documents. When their relationship matters, use an explicit conjunction.

## Article 5. Show the relationships

Choose a form that makes the intended relationships and distinctions clear. Do not let the presentation imply an unsupported relationship.

5.1 Plan the drawing before prose for time changes, spatial arrangements, branches, merges, loops, mechanisms, sequences, or state changes. When a relationship is needed to follow the argument and can be shown visually, make it visible in the drawing. Do not draw only the objects and leave prose to supply their essential relationship. Use labels to identify what is shown and state conditions the drawing cannot convey. If you cannot draw a relationship yet, report what is missing and continue independent pages. Do not add a second rendering of what the page's drawing, code, or text already shows. This includes connectors that repeat a relation stated by a label or expression within the drawing, unless they are needed to answer the page's question. For a simple relationship that gains nothing from a diagram, use short sentences or parallel list items.

5.2 Match the form to the relationship. Examples:

| Relationship | Form |
| --- | --- |
| Sequence | Directed path |
| One input under conditions | Branch |
| Conditions entering one evaluation | Convergence |
| Compared alternatives | Aligned inputs, stages, and outputs on shared axes |
| Hierarchy | Tree |
| State change | Before, action, after |
| Exact comparison | Table or shared-axis chart |
| Independent peers | Cards or bullets |
| Status | Evidence-to-action chain |

Unless the drawing convention explains a connection's relation, label that relation. Put operations on their operands.

5.3 Read the rendered drawing using its visual conventions. Follow each connection. In conceptual explanations, use pictograms that let readers recognize at a glance the kind and role of the objects being explained. Check that endpoints, exits, entries, labels, and any direction convey the intended relation, and that pictograms convey the roles of the elements they label. For process diagrams read left to right and top to bottom, route inputs into the top or left side of each element and outputs out of its bottom or right side. A flow must show its start, order, and destination. Make the explanation's reading path evident through placement, grouping, and connections. For left-to-right content, use left-to-right and top-to-bottom order by default, or clearly grouped columns read in sequence. Place the prerequisite, explanation, and result along that path. If the required explanation makes the reader jump between separated regions or backtrack to find a prerequisite, rearrange the layout. Place a process output after the steps that produce it in the established reading direction. Do not reverse that order to shorten a connector. For box-and-arrow diagrams, prefer horizontal and vertical connectors unless another route makes the relationship clearer. When several connectors enter the same element, join them near their sources. When several leave the same element, split them near their targets. Keep the branches short and the common segment long. Preserve arrow direction and make each source-to-target relationship unambiguous. Merge paths only when their direction and junctions make clear which source reaches which destination, without implying unintended connections. Enclose each separately labeled part or procedure stage of a diagram in its own panel, rather than separating them with a divider line or spacing alone, and keep each label and its explanatory elements inside that panel. Use placement, spacing, alignment, and consistent color cues to give needed symbols, labels, and connectors enough room within and between groups and to make grouping and separation clear. When adding an element, adjust or extend the underlying drawing to provide that room rather than squeeze it into an existing gap. Repair paths and arrangements that hide intended relationships or suggest unintended ones.

5.4 Make each independent column complete in its reading order. Align matching items across compared columns and show the match.

5.5 Compare approaches against the reader's goal and actual constraints. Before rejecting an approach for its presentation, check whether another arrangement or form preserves the content and solves the problem. If an established way to explain the same relationship helps the reader, reuse it. When that form is a standard plot, use a plotting tool that provides the required axes, scales, and annotations rather than rebuilding them by hand. Adapt reused material that no longer serves the explanation. Preserve needed content and explicit constraints.

5.6 Explain a mechanism with one instance the reader can check by hand. For a claim about a model, show its input and response. Put per-case measurements and fitted plots on result pages. In examples, keep the conditions and relationships needed for understanding. When the reader needs to connect a concept to code, a file format, or a record, retain the relevant source excerpt and show the correspondence. Simplify only details that this explanation does not need.

5.7 Draw an unchanged structure once with its changing values unless the page's question requires showing repeated instances. When explaining what is done once per item or combination of items, group that work with its corresponding inputs and results, and show shared inputs outside the group with connections to the work. When several item sets take part, show whether their work is independent or repeated for each combination, and make clear which items share each input. By default, show that multiplicity by stacking offset outlines of the group and labeling the items or total count. If the visible outlines encode the count, include the front outline and keep every outline distinguishable. For larger counts, use a schematic stack with the total count and mark it as abbreviated. Do not imply execution order or concurrency unless the diagram is meant to show it. Expand individual cases only when the reader needs to compare them or verify their count. A label such as 'per item' alone is not enough. Redraw a structure when it changes or a later page's question needs it. For a change, show both states and their difference. Draw a full curve only when its shape matters. Keep calculation-only quantities out of drawings unless their relationship is the claim.

5.8 Use captions and notes to identify what the figure shows and guide attention through the relationships needed for the page's question. Keep data, conditions, and brief source attribution needed to interpret or assess the figure visible. Put supporting detail that serves neither purpose in the record. Label multiple figures and the parts within a figure, including procedure stages, in reading order with parenthesized lowercase letters such as (a), (b), and (c). Give each figure's names, labels, numbers, captions, and notes a visible referent. Make each compared case identifiable. Remove notes and in-figure labels that have no referent or merely restate a relationship already clear from placement, grouping, or connections. If routing or grouping obscures a relationship, repair the drawing rather than compensate with explanatory text. Keep labels that supply identification, a visual convention, a condition, or a relationship that the drawing does not already make clear. Replace notation that needs a disclaimer.

5.9 In comparison tables, make rows the compared entities or conditions and order them by a meaningful key. State units once. If columns use different measurements, give each column's source. Keep group-defining conditions with the results. A full-page table must give a complete comparison for the page's question.

5.10 An image drawn inside an SVG or as a CSS background keeps its source width-to-height ratio.

## Article 6. Give each page one job

Give each page one distinct contribution at a readable size.

6.1 Give each content page one question, enough evidence, and a visual that justifies a page. Answer that question, then stop. Complete the causal chain or comparison in one place. Keep inputs, transformation, and output together. Keep changed and fixed variables together. Keep the evidence needed to check the page on that page.

6.2 Count only content that carries the answer as occupied space, regardless of layout reports. Use whitespace for grouping and hierarchy. If a page looks half empty, check whether its answer is complete. Only if incomplete, merge it without duplicating claims, add missing evidence or explanation, or remove it.

6.3 Set page count and grouping by the reader's questions, not by available space. Before adjusting layout, check that the page has the definitions, evidence, and relationships its question needs. Split independent questions. If one explanation is too dense at a readable size, divide it into successive questions with complete answers on separate pages. Remove repetition. Never shrink or cut needed explanation to fit a page count.

6.4 Wording, coordinate, or spacing changes alone do not create new claim boundaries. If the question, evidence chain, or claim ownership is wrong, replan the affected explanation and recheck its pages. Cosmetic edits do not fix structural defects.

6.5 Cover, contents, and divider pages are orientation pages. They and marked pending placeholders are exempt from density and evidence requirements.

## Article 7. Write scripts from the page

Speak to what the page shows. Do not add claims only in the script.

7.1 Give every page one script after planning its content. When the explanation changes, revise the script. Use the page's claim and authoritative material, grounded in visible content. Do not put a claim or number only in the script. Draw and make checkable each concept the speaker needs, or remove it. Greetings, transitions, and source citations for visible claims need not be drawn.

7.2 For a paragraph about visible content, start with an unspoken bracketed direction. Name the place on the page and the order to follow, not a topic. Order the paragraphs along the reading path established by the layout. Start with its first explanatory region, rather than a later result, and keep each paragraph's pointing directions on that path. Speak only to that place. The direction binds the paragraph to the visible explanation, rather than merely cueing the speaker. Check that the objects and relationships each sentence explains can be followed at the indicated places in the stated order. If they cannot, revise the drawing, the paragraph, or their order so they agree. Remove content only if the reader does not need it. Use complete sentences in the deck's spoken language. Do not add page numbers, titles, or note labels. Keep the cover script to the opening. No script repeats another page.

## Article 8. Keep planning records

Plan before building. Record sources, history, and decisions outside the deck. Put them on a page only as required by its question or evidence.

8.1 Keep `<artifact>.FLOORPLAN.md` beside the edit file. Update it before adding, splitting, or removing a page. Record each page's question, sources, and revision history. Keep a term ledger that names the page and element defining each project-specific term. Fix missing or late definitions before handoff.

8.2 Identify authoritative sources for direction and terminology before collecting candidate content. Plan in three passes:

1. Inventory each candidate fact, its primary evidence, and anything affecting its use.
2. Cluster facts by a causal chain, comparison, mechanism, or decision question before choosing page count.
3. Give each cluster a title, one reader question phrased as a question, evidence, observation, response, visual form, prerequisite, successor, and expected density.

8.3 Map every section and its siblings before writing. Check primary evidence to determine whether results exist. If results are pending, omit claims that depend on them or keep a marked placeholder. For a local fix, plan only affected sections and update only their entries.

## Article 9. Check the finished explanation

Read the finished deck as its reader. After a change, check what depends on it.

9.1 For a new deck or a deck-wide review, read every rendered page. For other changes, read all pages that carry or describe the change, including unedited pages. Include pages whose definitions, claims, summaries, examples, conclusions, or layout depend on it. This applies to edits, deletions, changed meanings, and changes in the system, configuration, or data described. Check for newly missing information and contradictions. Preserve each page's level of detail.

9.2 On each content page, recheck the evidence, meanings, and drawings against Articles 2, 4, and 5. Check that the presenter can explain it by pointing. Trace the reading path made evident by the rendered layout, then follow the script's pointing directions from the first paragraph to the last. Check that the two paths agree and that each prerequisite is encountered before the explanation that needs it. At each element, check that its explanation is available there or earlier. Check that every element answers the reader's question at that point and that the lead still fits the page. When the requester specifies a reference for visual style, view the finished rendering alongside it and check the requested visual qualities. When adding or revising a page in an existing deck, use representative existing pages as visual references and reuse their established palette, typography, line and arrow styles, and panel-label placement. Use the deck's existing visual distinctions before introducing new ones, and preserve those distinctions when adapting the figure. Compare the finished rendering alongside those references.

9.3 Test each element against the meaning already conveyed by words, visual structure, and conventions. Remove it in thought. If the reader loses no information or guidance needed for the current question, cut it. Test each page against earlier pages in the same way. When expanding an overview, identify the reader's next question and check that the page answers it with explanation or evidence the overview does not provide. Keep it only for needed understanding or guidance not already available.

9.4 If a page changes or is removed, move any prerequisites still needed and update dependent explanations. After moving, adding, or removing an explanation, recheck everything else that addresses the same point.

9.5 Repair each failed check that applies. Add visible support for any part of the lead left unanswered. Check orientation pages for their purpose, scripts, and geometry. Before acceptance, use the template's layout checks for clipping and overlap.

9.6 Separate content findings from production checks. A clean build, preserved edits, and clean geometry show successful production, not a working explanation.

## Article 10. Resolve the review request

Answer the question asked and make the change requested. Restore the understanding the comment asks for.

10.1 Answer a reviewer's question without editing unless it explicitly asks for a change. Preserve wording the requester explicitly specifies as exact. If it conflicts with another rule, report the conflict instead of silently changing it.

10.2 Before answering or editing, read the comment, its discussion, and the material it refers to. Identify its subject and the explanation, proposal, or change it requests. Interpret connected instructions together, and resolve what each applies to after any requested move or removal. Keep its distinctions and do not reintroduce what it rejects. If materially different readings remain, ask one focused question.

10.3 Put the requested understanding where the reader needs it. Adding requested words or removing a criticized term is not enough. After editing, read the explanation in order against the original comment. Within a requested fix, make every judgment the fix needs. Check the rest of the page for the same underlying defect and repair affected elements within the authorized scope. Do not change unrelated pages. Report out-of-scope defects with the rule broken and the pages checked.

10.4 Answer directly and state the change's status briefly. Add only what the reviewer needs to assess it or decide the next step. Examples include an unseen change, a departure from the request, or unfinished work.

10.5 Place requested content where needed within the authorized scope. Respect explicit placement constraints. Do not assume an existing page must hold an addition. When understanding requires it, redistribute content or add pages. Ask before exceeding the scope or an explicit page limit. If the same question returns after revision, reconsider the structure, missing premise, and interpretation of the question instead of patching the wording.

10.6 Before regenerating a page, carry every applied review change into its source. Check that the regenerated page keeps those changes.

10.7 For a deck-wide defect review, name each defect type, inspect every rendered page for it, and report the count. One example is not a deck-wide review. Report changes and remaining defects, not search mechanics.
