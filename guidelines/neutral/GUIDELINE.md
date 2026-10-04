# Neutral Technical Slides: Content Guideline

## Preamble

A technical deck helps its reader understand or decide something. This guideline governs what it says and shows. Template documentation governs page structure, components, and production procedures. Automated checks help find defects but do not replace the author's checks.

Work within the authorized scope. Acceptance requires both an understandable explanation and grounded claims and values. Let the reader's question set the detail and fidelity. If an explicit requester constraint conflicts with these requirements, report the conflict without silently changing either.

Each article gives a principle and rules for applying it. Apply each rule wherever its conditions hold. Examples illustrate rules without limiting them. Named forms, such as titles, leads, takeaways, and scripts, are defaults unless explicitly required. Adapt a default that obscures meaning or repeats content. Never cut needed explanation to preserve a form.

## Article 1. Answer the reader's question

Include what moves the reader from their existing knowledge to the understanding or decision requested.

1.1 Establish purpose, audience, and intended use before planning. Derive each page's question from the current request and discussion, not available material. Follow a changed question. For a live talk, make the explanation followable at speaking pace without dense text to read while listening.

1.2 Include claims and evidence that answer that question. Do not substitute an easier, documented, or measurable question.

1.3 Include detail only to help the reader understand, assess evidence, or act. Apply this test to names, counts, source material, intermediate outputs, file organization, tool operation, and maintenance detail. Before restating a visible count, test whether the repetition helps. Remove each element in thought, considering what words, drawings, and conventions already convey. Cut it if no needed information, condition, distinction, or guidance is lost. Apply the same test to each page against earlier pages.

1.4 Cut self-evaluation, inflated claims, and process narration. Keep drafting, revision, and submission history in planning records unless it passes 1.3.

## Article 2. Support each claim

Match evidence to the kind of claim being made.

2.1 Distinguish facts, definitions, observations, inferences, assumptions, proposals, and unknowns. Do not present proposals as decisions, planned results as observations, or provisional values as final. Check primary evidence for whether results exist. Mark pending results or omit claims that depend on them.

2.2 Use authoritative design descriptions for intended design, implementation sources for construction, and primary measurements or execution records for what happened. Combine these when the question requires them. Use secondary material only to fill a specific gap. Check current sources for changing facts. Sources establish truth, not the page's question or level of detail.

2.3 Establish a cause with evidence that distinguishes it from plausible alternatives, and name the source. Otherwise state the observation and label the explanation as proposed.

2.4 Give every content page a check the reader can perform. For values, show a counting or arithmetic check, such as a source row, sum, or enumeration. For a mechanism, trace each diagram step to a source or rule. Trace background facts to named sources. Remove unsupported claims or mark them unresolved.

2.5 Identify quantities as measured, source-reported, assumed, or computed, with their sources or derivations. Generate reported results and derived numbers from primary data and compare them with the generator's output. Show the inputs and rule needed to recompute values. Apply the rule to the whole object, including the hard case. For counts, identify counted items and how groups form the total. Label illustrative and assumed values and check their calculations separately. An example does not establish a measured result.

2.6 Verify relationships a reader would infer from conceptual drawings, including ordering, crossings, and meaningful relative size. Support them with a source or an appropriate check and state their conditions. Omit unsupported relationships. Exact shapes, timing, or proportions are required only when the question needs them. Calling a drawing conceptual does not validate it.

2.7 Cite sources that support claims or help interpret evidence. Attribute a claim to its primary source, not a summary or repository that merely carries it. A repository can be the primary source for an implementation claim. Include identifying details and qualifications the reader needs. Credit borrowed material and mark changes as adaptations.

2.8 When several actors participate, show their roles, who selects and executes, what each receives after transformation, its change limits, and the resulting state. Attribute work to the actor that performs it. Check the existence of commands, files, paths, and implementations presented as existing. Label external examples and proposed components.

2.9 Report disagreements between approved material and current evidence. Do not silently change approved decisions or suppress observations. Code, logs, earlier decks, and handoff notes do not reinterpret an approved decision. Reuse approved wording, tables, and figures when they express the required content.

## Article 3. Connect the explanation and its pages

Build a path from what the reader knows to what the explanation must establish.

3.1 Before collecting content, identify authoritative sources for direction and terminology and inspect requested visual references. Before drafting a sequence, work backward from the understanding later pages need. Plan forward from the reader's knowledge, giving each step the next question and an answer through words and visuals at that page's level. Make each part's contribution to the whole explicit.

3.2 Keep planning records outside the deck. Inventory candidate facts, primary evidence, and conditions affecting use. Cluster them by causal chain, comparison, mechanism, or decision before choosing page count. For each cluster, write its reader question as a question and record evidence, visual form, prerequisites, and successor. Add a title, observation, response, and expected density where applicable. Map sections and their siblings before writing. Record page questions, sources, decisions, revision history, and where unfamiliar terms are defined. Update records before adding, splitting, or removing pages. For local fixes, update affected entries only.

3.3 Complete each process or comparison where the reader needs it. Show each needed step's actor, inputs, outputs, and how its output determines the next step. State the condition and action for branches, repeats, stops, and rejected inputs. Naming a check is insufficient. Keep inputs, transformations, and outputs together, and changed and fixed variables together. State what a reduction keeps and discards.

3.4 Start from established understanding and let each element answer the preceding question. For example, a result can connect comparison conditions, measurement, observed difference, and a decision question. Source order does not determine the explanation. Explain choices or omissions that affect understanding through their goals or constraints.

3.5 Explain an object or relationship where it first raises a question, or just before. Show outputs where produced and their uses where consumed. Refer to objects, not earlier page titles or locations. Repeat only the prerequisite information needed to follow a use without looking elsewhere or recalling hidden detail. Move a page that needs a later value. Announce later pages only to locate the answer to a deliberately open question.

3.6 Establish each claim on one page. Repeating necessary local context under 3.5 does not require proving the claim again. Elsewhere, add a needed consequence or interpretation instead of repeating the explanation. An expansion of an overview must answer the next question with explanation or evidence the overview lacks. A broad topic is not a question. Combine subjects only through a real connection. Resolve or report conflicts with earlier pages.

3.7 Explain the problem a concept solves for this reader, what it represents, and its defining rule at the page's intended level. When intuition is needed for equations or algorithms, establish the concept first. Build the formal explanation on its names and drawing. In that introduction, first make the relationships easy to follow in both writing and review. Accept simplifications that preserve those relationships and remain consistent with the formal explanation and 2.6. To justify a model over a simpler one, show what the simpler model misses, why it matters, and how the chosen model accounts for it. Compare under conditions that isolate that difference.

3.8 Order sections by prerequisite knowledge. Distinguish background from the subject by its explanatory role, not source or novelty. Make headings match that role or subject. Clarify broad required headings with subheadings or introductory text. By default, present method, experimental setup, then results.

3.9 A progress update can use this example sequence:

Cover → Recap → Summary of Progress → Methods → Experimental Setup → Results → optional Discussion → Next Plan.

Recap connects prior context to the result now needed. Summary of Progress covers only work since that context. Next Plan is exactly one final page with evidence-derived actions or a statement that none is needed.

3.10 Give each content page one distinct question, sufficient evidence, and a visual that justifies the page, all at a readable size. A visual can be a diagram, equation, table, or plot. Keep the evidence needed to check the answer on that page, then stop. Set page count by questions. Before adjusting layout, check definitions, evidence, and relationships. Split independent questions or divide a dense explanation into successive complete answers. Never shrink or cut needed explanation to meet a page count.

3.11 Count only content carrying the answer as occupied space. Use whitespace for grouping and hierarchy. If a page looks half empty, check completeness. If incomplete, supply what is missing, merge without repeating claims, or remove it. Replan wrong questions, evidence chains, or claim ownership rather than patching wording or coordinates. Cover, contents, and divider pages are orientation pages. They and marked pending placeholders are exempt from density and evidence requirements.

## Article 4. Make words and notation clear

Judge language by what the reader understands, not the author's intention.

4.1 Make every visible line and spoken sentence understandable from the reader's knowledge and earlier explanations. Correct misleading wording and dependence on private context, including familiar words used technically. Use known field terms in their usual form and otherwise use plain language. Code names, literal translations, working labels, and type signatures do not replace explanations. Apply 1.3 before introducing an internal name.

4.2 Identify each action's actor and object or output. Name steps by their object and operation at the level explained, not by a hidden substep. Identify the objects in each relationship and how they relate. Describe special cases through conditions and effects the reader understands. Include implementation mechanisms only when needed. Do not invent a domain explanation for an implementation condition without evidence of their correspondence.

4.3 Identify items by displayed or established names and define them by kind and role. Add explanations or groupings where names do not suffice. Define unfamiliar terms and symbols at first use and keep later meanings clear locally. Check legends, glossaries, and notation tables against their referents and established names. Never depend on a later definition.

4.4 Use one term and visual notation per meaning. Preserve qualified names when the kind matters or the requester specifies them. Give distinct objects distinct names or indices when their difference matters. Carry those distinctions into later definitions, comparisons, calculations, and decisions. Simplify notation only without losing needed distinctions or redefining established meanings.

4.5 Name quantities, not typography or position. Make the relation described by a quantity clear, including path direction or endpoints when needed. Use digits for counts and separate numeric assignments visually. Reserve mathematical symbols for mathematics. Pair each equation with its meaning in words, with one equation per definition step. Name computation inputs, outputs, and sources. Give each symbol one role and distinguish assumed from solved values without substituting them. Example values must participate in the example and need no private context.

4.6 For sectioned decks, use `<section name> — <page topic>` for content-page titles. Use a short noun phrase naming the specific subject, object, or comparison, not its conclusion or incidental source label. Distinguish a detail from its whole. A defined interface, format, or dataset under review can be the subject. Align title, central visual, and takeaway around one point.

4.7 By default, give content pages one short lead and one takeaway. From the reader's prepared understanding, the lead raises the unresolved problem, comparison, or definition. It does not summarize the procedure, evidence, results, or answer. The takeaway states the one conclusion the page is meant to establish and its visible content supports. Support every part of the lead. Orientation pages are exempt.

4.8 Separate distinct statements in prose, captions, cells, scripts, and planning records. Use an explicit conjunction when their relationship matters.

## Article 5. Show the relationships

Make needed relationships visible without implying unsupported ones.

5.1 Plan drawings before prose for mechanisms, arrangements, sequences, branches, merges, loops, and changes. Show relationships that the argument needs and that can be drawn. Do not show only objects and leave prose to supply their essential relationship. For a simple relationship that gains nothing from a diagram, use an equation, short sentences, or parallel list items. If a relationship cannot yet be drawn, report what is missing and continue independent pages. Add a second representation only when it supplies needed guidance or a check.

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

Put operations on their operands. Label relations that the visual convention does not explain. Compare forms against the goal and constraints. Try another form or arrangement before rejecting an approach for its presentation. Reuse established explanations when helpful and adapt them without losing needed content or explicit constraints.

5.3 Make the reading path evident through placement, grouping, and connections. Default to left-to-right and top-to-bottom order, or clearly sequenced columns. Put prerequisites before explanations and results. Complete independent columns in reading order and align matching items across compared columns. Rearrange jumps and backtracking. A flow shows its start, order, and destination. Put outputs after the steps producing them, even when reversing that order would shorten a connector.

5.4 Follow each connection using the drawing's conventions. Check endpoints, entries, exits, labels, and direction against its intended meaning. In processes read left to right and top to bottom, prefer inputs at the top or left and outputs at the bottom or right when sides make no visible difference. Use another side when it gives a visibly simpler route while keeping flow direction, junctions, and reading order clear. These side defaults do not apply to returning feedback or return lines or to symbols with fixed pin positions. Merge paths only when direction and junctions show exactly which sources reach which targets.

5.5 In conceptual explanations, make each object's kind and role recognizable at a glance. Use pictograms by default, omitting them when standard symbols or the drawing already convey that information. Always check the meaning of pictograms used.

In every diagram, enclose separately labeled parts and stages in separate panels, with their labels and explanations inside. Spacing or divider lines alone do not replace panels. Only parts compared on shared axes may share a panel. Use placement, spacing, alignment, and consistent color to clarify groups and give elements room. Extend or rearrange drawings for additions instead of squeezing them into gaps.

5.6 Explain mechanisms with the smallest set of instances the reader can check by hand. For model claims, show input and response. Examples must show purpose and operation. At the page's level of explanation, keep useful conditions and show scope beyond the instance. Retain source excerpts and show their correspondence when connecting concepts to code, formats, or records. Simplify only irrelevant details.

5.7 Draw unchanged structure once with changing values unless repeated instances are needed. Group work performed per item or combination with its inputs and results. Show shared inputs outside that group and connect them to the work. Distinguish independent work from work per combination and identify which items share each input. A 'per item' label alone is insufficient. If repeated marks encode a count, make all counted marks distinguishable. Mark abbreviated depictions and give their total. Do not imply unintended order or concurrency. Expand cases when needed for understanding, comparison, or counting. Redraw changed structures or when a later question requires them. Show both states of a change and their difference. Show full curves only when shape matters, and calculation-only quantities only when their relationship is the claim.

5.8 Use captions and notes to identify content and guide attention. Keep necessary data, conditions, limitations, and brief attribution visible. Put other supporting detail in records. Label multiple figures and their parts, including stages, with (a), (b), (c) in reading order. Give labels, numbers, captions, and notes visible referents and identify compared cases. Apply 1.3 to redundant labels. Repair unclear drawing relationships instead of explaining around them. Keep labels needed for identification, conventions, conditions, or relations not otherwise clear. Replace misleading notation rather than disclaiming its implication. Retain assumptions or limitations needed to interpret the claim, but omit irrelevant departures from measured detail.

5.9 In comparison tables, use rows for entities or conditions by default. Transpose when that makes comparison clearer. Each row must belong to the set named by the row header, at the same level of grouping. Apply the same rule to columns. Put conclusions and facts of another kind outside the table, in a takeaway or note. Aggregates computed from member rows or columns may remain if labeled and visually set apart. Order entries meaningfully, state units once, and identify sources of differing measurements. Keep group conditions with results. A full-page table must complete the comparison its question requires.

5.10 When extending an existing deck or restyling any of its pages, use representative pages as visual references. Reuse palette, typography, panel and header shapes, line and arrow styles, and panel label placement. Use existing visual distinctions before adding new ones and preserve their meanings when adapting figures.

5.11 For a plotted quantity with a defined range, choose the axis range by the claim. Show the full defined range when the claim concerns the value's size, and draw a reference line when a stated threshold matters. When the claim concerns differences between close values, crop the axis to show those differences and visibly mark the cropped range.

## Article 6. Speak from the page

Speak to what the page shows.

6.1 Give each page one script after planning its content and revise it with the explanation. Ground it in visible content and authoritative sources. Make needed concepts visible and checkable or remove them. No claim or number belongs only in a script. Greetings, transitions, and citations for visible claims need not be drawn.

6.2 Begin each paragraph about visible content with an unspoken bracketed direction naming a place and order, not a topic. Follow the reading path in 5.3 from its first explanatory region. Bind every sentence to the indicated objects and relationships. Repair the drawing, paragraph, or order if they cannot be followed there. Remove only unneeded content. Use complete sentences in the deck's spoken language without page numbers, titles, or note labels. Keep the cover script to the opening. Apply 3.5–3.6 to necessary context and repeated explanation across scripts.

## Article 7. Check the finished explanation

Read the finished deck as its reader and check what each change affects.

7.1 Read every rendered page for a new deck or deck-wide review. After a change, read all pages carrying, describing, or depending on it, including unedited pages. Include dependencies in definitions, claims, examples, summaries, conclusions, and layout. This also applies when the described system, configuration, or data changes. Move needed prerequisites after deletions or moves and update dependents. Recheck other explanations of the same point for missing information or contradictions while preserving each page's level.

7.2 Check rendered content against all applicable rules in Articles 1–6. Check that the presenter can explain it by pointing. Trace the layout and then the script directions, checking agreement and prerequisite order. Compare rendering alongside requester-named visual references and representative deck pages. Apply the removal test in 1.3. Check orientation pages for purpose, scripts, and geometry.

7.3 Repair failed checks relevant to the decision the draft serves. A layout draft must fix defects affecting the requested visual comparison, with remaining repairs made in the redraw before acceptance. Report content findings separately from production checks. A successful build, preserved edits, or clean geometry does not establish an understandable explanation.

## Article 8. Resolve the review request

Restore the understanding requested, not merely the requested words.

8.1 Answer questions without editing unless a change is explicitly requested. Preserve wording the requester explicitly specifies as exact. Report conflicts with other rules without silently changing that wording.

8.2 Read the comment, discussion, and referenced material before responding. Identify the subject and requested explanation, proposal, or change. Read connected instructions together, including their application after moves or removals. Preserve distinctions and do not reintroduce rejected content. If materially different readings remain, ask one focused question.

8.3 Put the requested understanding where needed within authorized scope and placement constraints. Make the judgments required to complete the fix. Redistribute content or add pages when needed, asking before exceeding scope or an explicit page limit. Read the revised explanation against the original comment. Repair the same underlying defect elsewhere on that page within scope. Report unrelated defects with the rule broken and pages checked. If the same question returns, reconsider structure, missing premises, and interpretation under 3.11.

8.4 Before regenerating a page, carry applied review changes into its source and check that they survive regeneration.

8.5 Answer directly and report status briefly, including only what the reviewer needs to assess the change or decide the next step. For a deck-wide defect review, identify each defect type, inspect every rendered page, and report its count. Report changes and remaining defects, not search mechanics.
