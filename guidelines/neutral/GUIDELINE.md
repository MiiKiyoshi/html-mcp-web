# Neutral Technical Slides: Content Guideline

## Preamble

This guideline governs a technical deck's content. Follow the drafting sequence in 3.4, using Article 2 to establish evidence, Article 5 to build the visual, and Article 4 to choose words and notation as they are needed. Template documentation governs page structure, components, and production procedures. Article 7 and independent review address defects left in the finished explanation.

Acceptance requires an understandable explanation and grounded claims and values within the authorized scope. Report conflicts with explicit requester constraints without silently changing either.

Apply rules wherever their conditions hold, not only to the examples named. Titles, leads, takeaways, and scripts are defaults unless explicitly required. Adapt defaults that obscure meaning, repeat content, or force out needed explanation.

## Article 1. Answer the reader's question

Include what moves the reader from their existing knowledge to the understanding or decision requested.

1.1 Establish purpose, audience, and intended use before planning. Derive page questions from the current request and discussion, not available material. For a live talk, make the explanation followable at speaking pace without dense text to read while listening.

1.2 Do not substitute an easier, documented, or measurable question for the one requested.

1.3 Before adding an element, or retaining one whose supporting context has changed, identify what information, condition, distinction, or guidance the reader needs there that their knowledge and the existing words, drawings, and conventions do not already provide. If omitting it would lose none of these, do not add or retain it. Apply this test at every scale, from a label or repeated count to a whole page. Judge necessity separately from clarity or fit.

1.4 Cut self-evaluation, inflated claims, and process narration. Keep drafting, revision, and submission history in planning records unless it passes 1.3.

## Article 2. Support each claim

Match evidence to the kind of claim being made.

2.1 Before writing a claim, distinguish whether it is a fact, definition, observation, inference, assumption, proposal, or unknown. Check primary evidence for whether a reported result exists and is final. Mark pending results or omit claims that depend on them. Keep proposals distinct from decisions and provisional values distinct from final ones.

2.2 Use authoritative design descriptions for intended design, implementation sources for construction, and primary measurements or execution records for what happened. Use secondary material only to fill a specific gap. Check current sources for changing facts. Sources establish truth, not the page's question or level of detail.

2.3 Establish a cause with evidence that distinguishes it from plausible alternatives, and name the source. Otherwise state the observation and label the explanation as proposed.

2.4 Select evidence the reader can check for each content page's answer before placing its claims. For results, establish the tested cases and conditions. If only a subset of the introduced evaluation set was tested or shown, state why and limit the conclusion accordingly. Show a source or calculation for each reported measurement, count, or computed value. Verify chosen settings against the configuration or decision record, and support claimed benefits separately. Trace mechanism steps to sources or rules and background facts to named sources. Omit unsupported claims or mark them unresolved when drafting.

2.5 Generate results and derived numbers from primary data before placing them in a figure or table, and compare the reported values with that output. Identify quantities as measured, source-reported, assumed, chosen, or computed, with their sources, decision records, or derivations. Show inputs, rules, and assumptions needed to recompute values. Apply the rule to the whole object, including the hard case. For counts, identify items and how groups form the total.

Before calculating from an example, establish when its inputs and rule are valid and limit the conclusion accordingly. Label illustrative and assumed values and check their calculations separately. An example does not establish a measured result.

2.6 Support relationships implied by conceptual drawings, including ordering, crossings, and meaningful relative size, with a source or check under stated conditions. Omit unsupported relationships. Exact shapes, timing, or proportions are required only when the question needs them.

2.7 Cite the primary source of a claim, not a summary or repository that merely carries it. A repository can be primary evidence for an implementation claim. Include details needed to identify and interpret the evidence. Credit borrowed material and mark changes as adaptations.

2.8 When several actors participate, show their roles, who selects and executes, what each receives after transformation, its change limits, and the resulting state. Attribute work to the actor that performs it. Check the existence of commands, files, paths, and implementations presented as existing. Label external examples and proposed components.

2.9 Report disagreements between approved material and current evidence. Do not silently change approved decisions or suppress observations. Code, logs, earlier decks, and handoff notes do not reinterpret an approved decision. Reuse approved wording, tables, and figures when they express the required content.

## Article 3. Connect the explanation and its pages

Build a path from what the reader knows to what the explanation must establish.

3.1 Establish the reader's starting knowledge and the understanding or decision the deck must enable. Work backward from that outcome to its prerequisites, then arrange the questions forward from what the reader knows. Use established answers where later questions depend on them. Before collecting content, identify authoritative sources for direction and terminology and inspect requested visual references.

3.2 Keep planning records outside the deck and record choices as they are made. Record the reader states established under 3.1. For each required question, record the one answer the reader should retain, its prerequisites, evidence, visual form, and successor. Record unresolved gaps rather than filling a page slot with available content. Record page boundaries and the deck map, including sections and their siblings, after grouping the explanation under 3.10.

During the drafting sequence in 3.4, record only the elements needed to establish, assess, or follow each answer, in reading order, and where their prerequisites are established. Record the primary source locations for mechanism and calculation steps or mark them unverified. Keep first definitions, revision history, and decisions under 8.2 with their authority, scope, and reason.

Update affected entries before changing content or page grouping. Treat author choices as revisable plans, not constraints. Change a planned page boundary, layout, or element when it no longer serves the answer.

3.3 Show each process or comparison step's actor, inputs, outputs, and how its output determines the next step. State conditions and actions for branches, repeats, stops, and rejected inputs. Keep inputs, transformations, and outputs together, and changed and fixed variables together. State what a reduction keeps and discards.

3.4 After establishing the explanation under 3.1 and its page grouping under 3.10, draft each content page in this order:

1. Start with what the reader already knows from the audience context and preceding pages. State the next question and the one answer the page must establish. Select its supporting evidence under Article 2 before choosing page elements.
2. Construct the relationship that establishes the answer as a diagram, equation, table, or plot under Article 5. Give it the objects, operations, conditions, and evidence needed at this point, choosing terms under 4.1 as each object or action is named. For a relationship that gains nothing from a diagram, use the alternatives in 5.1.
3. Add words only for meanings, distinctions, conditions, or guidance the visual and established context do not convey. Place needed definitions before their use, and reuse established ones under 3.5. State goals or constraints when needed to explain a choice or omission.
4. Name the subject in the title under 4.6. If using a lead, name the problem under 4.7. Write the takeaway from what the visible explanation establishes. After rendering the page, write the script under Article 6.

Build one element at a time in reading order, using only prerequisites already established. Resolve a missing prerequisite or relationship before adding dependent content. Let this order, rather than source order or available panel space, determine what comes next.

3.5 Explain an object or relationship where it first raises a question, or just before. Show outputs where produced and their uses where consumed. Refer to objects, not earlier page titles or locations. Repeat prerequisites only as needed to avoid looking elsewhere or recalling hidden detail. Move a page that needs a later value. In visible content and scripts, refer forward only to locate the answer to a deliberately open question, not to preview later titles or contents.

3.6 Establish each claim once in the explanation. Necessary local context under 3.5 does not require proving it again. Elsewhere, add a consequence or interpretation. An overview's expansion must answer a further question, not repeat the topic. Combine subjects only through a real connection. Resolve or report conflicts with earlier pages.

3.7 Before introducing a concept, identify the concrete problem that makes it needed. Trace a mechanism or calculation through its primary source from inputs, operations, and conditions to outputs and their use in the next step, through to the required result. Check simplifications against that trace. Mark unresolved steps as unverified in the plan and dependent drafts.

For an unfamiliar mechanism, show what happens to named objects, what changes, what stays fixed, and what follows before attaching the technical name and definition. Explain its referent and defining rule at the page's level, then build the formal explanation on those relationships. In writing and review, accept introductory simplifications that preserve the relationships and agree with the formal explanation and 2.6.

To justify a model over a simpler one, show what the simpler model misses, why it matters, and how the chosen model accounts for it. Compare under conditions that isolate that difference.

3.8 Order sections by prerequisite knowledge. Distinguish background from the subject by its explanatory role, not source or novelty. Make headings match that role or subject. Clarify broad required headings with subheadings or introductory text. By default, present method, experimental setup, then results.

3.9 A progress update can use this example sequence:

Cover → Recap → Summary of Progress → Methods → Experimental Setup → Results → optional Discussion → Next Plan.

Recap connects prior context to the result now needed. Summary of Progress covers only work since that context. Next Plan is exactly one final page with evidence-derived actions or a statement that none is needed.

3.10 Derive page boundaries and count from the explanation required under 3.1. First remove content that fails 1.3 and repeated claims under 3.6, preserving necessary local context under 3.5. Arrange the remaining questions and answers with their prerequisites and evidence. Group connected steps by causal chain, comparison, mechanism, or decision. Divide the explanation into pages, each with one distinct question, evidence to check its answer, and a diagram, equation, table, or plot, all at a readable size. Put independent questions on separate pages. Record this sequence and page grouping before proposing a count. Existing pages and proposed counts are provisional unless explicitly fixed by the requester under 8.2.

Before adjusting layout, check definitions, evidence, and relationships. Change obstructive page divisions, order, figures, panels, or tables before continuing. If the explanation still cannot fit, split it into successive complete answers. Do not preserve structure or page count by inventing terms, obscuring relationships, shrinking content, or omitting needed explanation. Apply 8.3 to changes beyond scope or approved structural constraints.

3.11 Count only content carrying the answer as occupied space. If a page looks half empty, check completeness. If incomplete, supply missing content, merge without repetition, or remove it. Replan wrong questions, evidence chains, or claim ownership rather than patching wording or coordinates. Cover, contents, and divider pages are orientation pages. They and marked pending placeholders are exempt from density and evidence requirements.

## Article 4. Make words and notation clear

Judge language by what the reader understands, not the author's intention.

4.1 Before wording an action or object, start from how the audience and field name it in the deck's language, including established loanwords. Choose expressions with clear meanings and actual common use, including in titles, labels, and takeaways. Do not form them by literally translating an internal code name or a word from another language. Avoid rarely used words even when their dictionary meanings are valid. Do not replace established terms with paraphrases or coinages merely to sound plainer. If no established term fits, describe the concept's relevant objects, properties, and relationships. Preserve the source's meaning. Do not substitute unexplained identifiers, working labels, or type signatures for an explanation. Retain command, option, and data structure names when needed to identify the subject. Explain unfamiliar terms, including ordinary words used technically, under 4.3.

4.2 Identify actors, objects, and their relationships. When describing an action or change, first state what acts or changes and what happens to the affected object. Carry the action and participants needed to identify that event into any shorter title, label, definition, or summary. Use a general verb or placeholder only when its specific action or referent is already clear there. Name steps by their object and operation at the level explained, not a hidden substep. Describe special cases through conditions and effects. State when a claim holds instead of narrating the author's act of assuming it. Do not invent a domain explanation for an implementation condition without evidence of their correspondence.

4.3 Define unfamiliar terms and symbols at first use by what kind of thing they name and what they represent or do, using vocabulary selected under 4.1. For a quantity, first identify what it counts or measures using an established term when one fits, keeping the object and its interval or unit together. Put needed conditions and how the value is obtained afterwards. Do not replace or interrupt that meaning with its role in the equation, another symbol's role, or a demonstrative referring to another symbol. Describing a drawing's appearance or listing its parts is not a definition. Leave structure and operation to the figure rather than retelling them in the definition. A specific index of an established symbol is a later use when its meaning is unchanged. For later uses, repeat only the prerequisite information needed under 3.5. Build legends, glossaries, and notation tables from those established meanings.

If an abbreviation is unfamiliar to the audience or confusable with another name in the deck, write the full name followed by the abbreviation in parentheses at first use. Otherwise, leave routine field abbreviations unexpanded regardless of source. Apply this separately to visible reading order, including titles, labels, and tables, and to spoken order in scripts. Use the abbreviation alone afterwards unless local clarity requires repeating the full name.

4.4 Use one term and visual notation per meaning. Preserve qualified names when the kind matters or the requester specifies them. Keep distinct names or indices where differences matter, including in later uses. Do not redefine established notation while simplifying it.

4.5 In text and scripts, including summaries and takeaways, identify quantities and drawn elements by their established names or the same wording used to define them. Use appearance, position, or descriptions such as 'the second term' only to locate them. When an equation's form is the subject, name its mathematical terms and operations directly. Explain the relation a quantity describes, including direction or endpoints when needed.

Use digits for counts and separate numeric assignments visually. Reserve mathematical symbols for mathematics. Write words and explanatory text inside mathematical expressions in English, keeping surrounding explanations in the deck's language. Explain the new quantity or relationship an equation establishes when it is not already clear from the drawing and established context. Use one equation per definition step. Name computation inputs, outputs, and sources. Give each symbol one role and keep assumed and solved values distinct. Example values must participate in the example without private context.

4.6 For sectioned decks, use the section name alone when sufficient. Otherwise, append a short noun phrase naming the page's object, process, or comparison, separated by an em dash. Name the subject at the level explained, not its conclusion, incidental source, or an action used merely to obtain it. A defined interface, format, or dataset can itself be the subject. Within the topic, use a group or stage name followed by a colon only for an established grouping or sequence the reader needs. Make the title, visual, and takeaway address the same point.

4.7 By default, give content pages one lead and one takeaway. Write the lead as a short noun phrase directly naming the one problem the page addresses, using established terms. It may share the title's words. Do not repeat the title verbatim or use roundabout wording merely to avoid its terms. Do not use joined clauses, a question, or a list of figure contents. Keep the explanation and answer out of the lead. The takeaway states the single conclusion supported by the visible content. For measurement results, state what they show about the claim or mechanism tested, within the scope of the evidence. Include a value only when it carries that conclusion. Orientation pages are exempt.

4.8 Separate distinct statements in prose, captions, cells, scripts, and planning records. Use an explicit conjunction when their relationship matters.

## Article 5. Show the relationships

Make needed relationships visible without implying unsupported ones.

5.1 Plan drawings before prose for mechanisms, arrangements, sequences, branches, merges, loops, and changes. Draw essential relationships, not just their objects. Use an equation, short sentences, or parallel list items when a diagram adds nothing. If a relationship cannot yet be drawn, report what is missing and continue independent pages. Add a second representation only for needed guidance or a check.

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

Put operations on their operands. Label relations the visual convention does not explain. Try another form or arrangement before rejecting an approach for its presentation. Reuse established explanations where they fit the goal and constraints.

5.3 Default to left-to-right and top-to-bottom order, or clearly sequenced columns. Complete independent columns in reading order and align matching items across compared columns. Use placement, grouping, and connections to show prerequisites before explanations and results without backtracking. Put outputs after the steps producing them even if reversing that order would shorten a connector.

5.4 Choose each connection's endpoints, entries, exits, labels, and direction from the relationship it represents before routing it. In processes read left to right and top to bottom, prefer inputs at the top or left and outputs at the bottom or right when sides make no visible difference. Use another side for a visibly simpler route that preserves direction, junctions, and reading order. These defaults exclude feedback, return lines, and fixed symbol pins. Merge paths only when direction and junctions show which sources reach which targets.

5.5 Choose pictograms with established meanings for object kinds and roles in conceptual explanations unless standard symbols or the drawing already convey them.

In every diagram, enclose separately labeled parts and stages in separate panels with their labels and explanations inside. Spacing or divider lines do not replace panels. Only parts compared on shared axes may share a panel. Add an outer figure panel only for a needed grouping or distinction. Neighboring panels need not contain equal amounts of text. Do not add content merely to match panel shapes or fill unused space. Extend or rearrange drawings for additions instead of squeezing them into gaps.

5.6 Explain mechanisms with the smallest set of instances the reader can check by hand. For general rules, default to generic examples with short placeholder names and simple values. Use real names or measured values when identity or magnitude matters to the claim. Show purpose and operation, including input and response for model claims, and the conditions and scope beyond the instance. When connecting concepts to code, formats, or records, retain source excerpts and show their correspondence.

5.7 Draw unchanged structure once with changing values unless understanding, comparison, counting, or a later question requires repeated instances. Group work per item or combination with its inputs and results. Connect shared inputs from outside the group, showing which items share them. Distinguish independent work from work per combination without implying unintended order or concurrency.

Make counted marks distinguishable. Mark abbreviated depictions and give their total. Redraw changed structures, showing both states and their difference. Show full curves only when shape matters, and calculation-only quantities only when their relationship is the claim.

5.8 Keep necessary data, conditions, limitations, and brief attribution visible. Put other supporting detail in records. Label multiple figures and their parts, including stages, with (a), (b), (c) in reading order. Give labels, numbers, captions, and notes visible referents and identify compared cases. Explain visual distinctions through the drawing, a convention, or a legend using actual mark or line samples beside their meanings. Keep labels only for identification or information not otherwise clear. Repair unclear relationships and misleading notation in the drawing rather than explaining or disclaiming them in notes.

5.9 Use table rows for entities or conditions unless transposing makes comparison clearer. Rows and columns must belong to their header's set at the same grouping level. Put conclusions and facts of another kind outside the table. Aggregates computed from member rows or columns may remain if labeled and visually set apart. Order entries meaningfully, state units once, identify sources of differing measurements, and keep group conditions with results. A full-page table must complete its comparison.

5.10 When extending an existing deck or restyling any of its pages, use representative pages as visual references. Reuse palette, typography, panel and header shapes, line and arrow styles, and panel label placement. Use existing visual distinctions before adding new ones and preserve their meanings when adapting figures.

5.11 For a plotted quantity with a defined range, choose the axis range by the claim. Show the full defined range when the claim concerns the value's size, and draw a reference line when a stated threshold matters. When the claim concerns differences between close values, crop the axis to show those differences and visibly mark the cropped range.

## Article 6. Speak from the page

Speak to what the page shows.

6.1 Give each page one script. Read its current rendering before drafting or revising the script. Use that page and established context so the presenter need not memorize later content. Revise page and script together, keeping concepts, claims, and values needed to understand or check the answer visible.

Apply Article 2 to script claims, keeping required attribution on the page. Name a source aloud only to distinguish whose evidence or settings are being discussed. When needed, attribute shared borrowed settings once, repeating only to preserve that distinction.

Apply 1.3 to each script sentence using the audience's knowledge, visible page, and prior speech. Preserve needed guidance even when it adds no new information, including the opening orientation in 6.2. Greetings and necessary transitions need not be drawn.

6.2 Begin each paragraph about visible content with an unspoken bracketed direction naming a place and order, not a topic. Follow 5.3 from the first explanatory region, adding inspection pauses where needed. Bind speech to the indicated objects and relationships. Repair the drawing, paragraph, or order if they cannot be followed together.

Discuss the subject directly without reading visible text line by line or announcing what a slide, card, or figure shows. Keep established names and exact wording when needed to identify or explain it. Add reasons or implications only when their omission would leave a necessary relationship unclear. Use transitions only to connect the current question to established context when that connection would otherwise be missed. Use concise, concrete, complete sentences in the deck's spoken language without spoken page numbers or note labels. Apply 3.5–3.6 to context and repetition across scripts.

State the presenter's own design choices as first person decisions, using I or we accurately. Distinguish adopted settings from original work and do not claim another person's decisions. Keep necessary limitations and open items visible as facts. Speak them only when needed to judge a claim or decision, without advance apologies or wording that diminishes the presenter.

Do not read out displayed measurements or calculated values. Explain their meaning for the claim or decision when interpretation is needed. Ratios, multiples, and values defining a rule may be spoken when they carry the explanation, including ratios and multiples computed from displayed values.

Keep the cover script to the opening. It may include one short sentence recalling an earlier presentation or discussion to establish today's starting point, even if already known. A divider announces only its displayed section, and a contents page introduces only its displayed organization. Do not add later page details.

Let speaking time follow the needed explanation. For a specified duration, check at a natural pace with time for pointing and inspection. Adjust scope or sequence within authorized constraints rather than padding, repeating, rushing, or omitting needed meaning.

## Article 7. Check the finished explanation

Read the finished deck as its reader and check what each change affects.

7.1 Read every rendered page for a new deck or deck-wide review. After changing content or the system, configuration, or data it describes, read all affected pages, including unedited dependents and other explanations of the same point. Check definitions, claims, examples, summaries, conclusions, and layout at each page's level. After deletions or moves, relocate needed prerequisites and update dependents.

7.2 Check rendered content against Articles 1–6 before consulting the script. Follow visible reading order using only the audience's established knowledge, earlier pages, and preceding elements. Check whether the reader can answer the page question and interpret its quantities and visual distinctions without mentally filling gaps from sources, review history, or author intent.

Then read scripts at a natural pace with their pointing directions and pauses. Check wording under Articles 4 and 6, agreement with indicated content, and prerequisite order. Apply 1.3 to visible content and speech, preserving the opening orientation in 6.2. Compare rendering with requested visual references and representative deck pages. Check orientation pages for purpose, scripts, and geometry.

7.3 A layout draft must fix defects affecting the requested visual comparison. Complete remaining repairs in the redraw before acceptance. Report content findings separately from production checks. A successful build, preserved edits, or clean geometry does not establish an understandable explanation.

## Article 8. Resolve the review request

Restore the understanding requested, not merely the requested words.

8.1 Answer questions without editing unless a change is explicitly requested. Preserve wording the requester explicitly specifies as exact. Report conflicts with other rules without silently changing that wording.

8.2 Read the request, discussion, and referenced material before responding. For supplied rewrites, identify the failure corrected and apply the underlying requirement to other affected passages.

Before editing, gather the page's purpose and active requirements, including those carried with moved content. Check planning records, content notes, generator comments, and relevant commit messages for decisions required or approved by the requester or a delegated reviewer. Record their authority and scope together, separating current requirements from replaced or withdrawn ones. Recorded author choices and reviewed drafts do not by themselves establish constraints.

Treat reviewer findings as proposals. Check them against the active requirements and hold and report conflicts rather than applying them. Read connected instructions together after moves or removals, preserving distinctions and excluding rejected content. If materially different readings remain, ask one focused question.

8.3 Repair the explanation within authorized scope and placement constraints. For a reconstruction, establish the required explanation under 3.1 and regroup it under 3.10 before moving content between pages. Ask before exceeding scope or an explicit page limit. Add notes only to help the reader understand or assess a claim, not to document the review response.

Read the revision against each active requirement under 8.2, including earlier requests affected by the fix, and identify where it is satisfied. Report conflicts rather than dropping required content. Repair the same defect across affected pages under 7.1. Report unrelated defects with the rule broken and pages checked. If the same question returns, reconsider structure, missing premises, and interpretation under 3.11.

8.4 Before regenerating a page, carry applied review changes into its source and check that they survive regeneration.

8.5 Report changes, remaining defects, and unfinished or unchecked scope. When a check confirms an error, state what was wrong before explaining the correction. For a deck-wide defect review, inspect every rendered page and report counts by defect type. Omit search mechanics and details the reviewer does not need to assess the change or decide the next step.
