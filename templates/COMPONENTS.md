# Component reference

Read the sections needed for the current figure or page.

## Page kinds

A section is a body page with a title bar unless `data-layout` names one of the two
full-bleed pages. Those two drop the title bar and fill the page, which is how a deck
marks where one part ends and the next begins. On these pages, the layout check reports
overflow anywhere above the footer bar, just as it reports body overflow.

```html
<section data-layout="contents" data-title="Contents">
  <ol>
    <li>Background
      <ul>
        <li>Context</li>
        <li>Question</li>
      </ul>
    </li>
    <li><span class="venue">Venue</span>Name of the work<span class="by">(authors)</span></li>
  </ol>
</section>

<section data-layout="divider" data-no="01">
  <p class="label">Section name</p>
  <img class="shot" src="figures/opening.png" alt="">
</section>
```

- `contents`: `data-title` draws the heading and the rule under it, and each `<li>`
  takes its number from a CSS counter, so list order is the numbering. `span.venue` sets
  smaller text before the name and `span.by` after it. For sub-items, end the `<li>`
  with one `<ul>` after its own text. The sub-items do not affect numbering and appear
  as unnumbered lines aligned under the item's text, each in smaller type with a short
  solid bar in the text colour before it. A list with sub-items and at least two outer
  items stays in one column while it fits there and takes two columns when one column
  overflows, which the deck measures in the skin's type. Items fill the left column from
  top to bottom, then the right, without splitting an outer item across columns. Set
  `data-columns` on the section to a whole number from 1 to 9 to choose the column count.
  For example, `data-columns="1"` keeps one column, and `data-columns="2"` gives two
  columns even without sub-items. In columns, long items wrap and the layout check reports a wasted
  last line. With columns, any skin picture behind the list fades to keep the text
  readable. To fit or fill the page, try columns at full size before scaling. When the
  list looks too large or does not fit, set `data-scale` on the section to a positive
  number, as in `data-scale="0.8"`, to scale the whole list, numbers and sub-items
  included, from its top left. Reducing the scale leaves unused space on the right even
  with columns. The heading and its rule keep their size, and the layout check uses the
  scaled list size.
- `divider`: `data-no` is the number in the capsule, `p.label` is its text, and an
  optional `img.shot` places a picture to the right.

`data-appendix` on a section, usually the `divider` that opens one, says that it and
every page after it are an appendix: pages held back for questions rather than shown in
order. The footer then counts the deck the audience is told to expect, cover included,
and stops before the appendix, whose own pages read `A1 / A8`. A deck that marks no
section counts the whole of itself, so `divider` on its own changes nothing: it parts one
chapter from the next as often as it opens an appendix.

## Body components

Blocks spread down the body rather than stacking at its top, so a page with little on it
does not leave a dead band above the footer. A first `p.lead` stays with the title and
an optional final `p.takeaway` stays near the bottom of the body, above any references.
Neither participates in the spread, so only the content between them shares the
remaining height.

- `p.lead` is an optional introduction on one line under the title. Follow the
  configured content guideline for whether to include it and what it says. Normal `p`
  carries prose.
- `p.takeaway` is the concluding line at the bottom. Put at most one as the last direct
  paragraph of a body section, after its figure, table, or other content. It works with
  or without a lead. The common builder applies the skin's `lead` class to it, so both
  lines share the same typography in every skin. The takeaway spans the body width so
  PowerPoint has room for minor font-metric differences; its text is centred, while the
  lead keeps its own alignment and width.
  Write `<p class="takeaway">The concluding statement.</p>`; skins only style its appearance.
- `p.note` carries one explanatory note, and `ul.notes` carries several, one per `li`
- `<ol class="references">` defines the deck's references once, directly in `<body>`
  outside all sections, with one `<li id="key">…</li>` per reference. Cite a key with
  `<cite>key</cite>` or several with `<cite>key1, key2</cite>`, in text or inside the
  `<text>` of an inline `<svg>`. References are numbered in the order first cited across
  the deck. Each citation shows bracketed numbers such as `[1]` or `[2, 1]`, kept on one
  line in a wrapped label. Each citing body page lists only its own references with those
  numbers in small type at the bottom right of the body, below the takeaway, one per line
  with their left edges aligned and the longest line ending at the body's right edge.
  Uncited references are not shown. Missing or duplicate reference IDs and
  undefined citation keys stop the build, as do citations in scripts or on cover,
  contents, or divider pages.
- `p.units` sits directly above a measurement table and states the units once
  (`ΔTNS: ns · power: %`), instead of repeating them in footnotes; keep the same form on
  every slide that shows measurements
- standard `table`; `table.dense` when the rows outgrow its spacing; `table.tight` for a
  wide numeric table whose cells must not wrap. The first column aligns left and the
  others right, each cell by the column it stands in under `rowspan` and `colspan`
- `pos` and `neg` mark an improvement and a regression, `sep` draws a column boundary,
  and `nw` keeps a short label or status cell on one line
- `grid3` containing `metric` cards, optionally marked `win` or `lose`
- `two` containing normal content and `card`; its two columns share the row's height, and
  a column wrapped in a `div` spreads its blocks over that height, so a short stack beside
  a tall figure does not sit in a clump at the top
- `flow` containing four `step` blocks, `flow.cycle` when the last step feeds the first
- `p.feedback` for received feedback
- `div.concerns` for points raised about the work: a `<b>` label on its own line, then the
  points as a list or a paragraph
- `code` for identifiers
- `pre` for a code or file excerpt of several lines; it draws one box and keeps the line
  breaks, and a `code` inside it drops the inline chip so the block reads as one piece.
  A long line overflows rather than wraps, so the layout check reports it
- inline `<svg>` for a figure the components above do not carry: its labels stay exact
  and stay sharp in print, so prefer it over a picture of a drawing. Settle the box the
  figure is to fill first (the column width by the height left on the page; `two` splits a
  1200px body into 622px and 541px), give the `viewBox` those proportions, and draw inside
  it. The element takes the width it is given and stops at its `max-height`, and the
  drawing keeps the `viewBox` proportions inside that, so a `viewBox` of another shape
  leaves a band down both sides or across the top and bottom that nothing can use.
  Within each SVG panel, lay out the content for that panel's width and height while
  preserving grouping and reading order.
  Give the `viewBox` the size the figure is drawn at, not a smaller box scaled up: a
  browser misplaces its own selection inside an svg that scales, by the scale factor, so
  the handles a reader drags to widen a selection on a touch screen sit away from the
  letters and collapse the selection when pressed. The review page's highlight and comment
  button are computed from the letters themselves and are right either way
- `<img>` carries a raster figure. Give it a `max-height` so the body stays inside its
  box. Check [image proportions and readability](#image-proportions-and-readability).

Math is written as TeX between `$…$` (inline) or `$$…$$` (display); `\(…\)` and
`\[…\]` work too. The builder renders it with KaTeX and embeds the renderer and its fonts
in the file, so the deck stays self-contained and prints the same as it shows; a deck
with no math carries none of that. A literal dollar sign is written `\$`, since two
plain dollars on one line would otherwise read as a formula.

A long label inside an inline `<svg>` is written as one `<text>` holding the whole
sentence, with `data-wrap="<width>"`, the width in `viewBox` units it may take. The deck
breaks it into lines when it opens, measured with the skin's own font, so the content
file carries no hand-placed lines. The breaking is the Knuth-Plass algorithm, which TeX
uses: it weighs every way of splitting the whole sentence at once, hyphenation points
included, and takes the lines with the least total badness, which is what keeps a narrow
column's spaces from opening to several times their width. A word broken that way keeps a
hyphen at the end of its line. `x` and `y` are the start of the first line. `data-align`
is `left` (the default), `center` (`x` is then the middle of every line), `justify`
(every line but the last is widened to the full width through the spaces between its
words) or `balance` (the same lines at the narrowest width that still needs no more of
them, so the last line is no shorter than the rest). `data-line-height` is the step
between lines in font sizes (default 1.35). The
text is plain: a `tspan` written inside it contributes its words and nothing else. With
`data-max-lines="<n>"`, a label that needs more lines is reported by the layout check as
`needs N lines, box allows M`.

`data-fit="<width>x<height>"` names the whole box instead of a width, and the deck picks
the size as well: the largest half-pixel in `data-fit-range="<smallest> <largest>"` (the
skin's own size and 8 by default) whose lines fill no more of the box's height than
`data-line-height` gives them. Cards of a row written this way come out at the density
their sentences allow, rather than at one size with the short ones gaping between the
words. How far a line has to open is then reported rather than chosen for, since it
hardly moves with the size: `data-fit-stretch` (2 by default) says that under `justify`
a space may open to that multiple of a natural space, and otherwise that a line may fall
to the width divided by it. A narrow column opens its spaces half again as wide as a
matter of course, so the default names only the lines a reader would stop at; 1.5 is the
tighter setting to ask for where a row of cards must read evenly. The layout check
reports a label past it as `is loose in 196x92 at 12px`, and a label the box holds at no
size in the range, which is drawn at the smallest, as `does not fit 196x92 at 10px`.

A figure is content, not styling. CSS outside this vocabulary changes the measured
geometry, and the review server reports what that costs: an inline `<svg>` whose shapes
run past its `viewBox` is reported as cut off, a drawing that leaves a quarter
or more of a side empty is reported as holding space it does not draw in, two labels
printed over each other are reported as a collision, and a label that runs past the
sides of the rect it sits on is reported with the side and by how much.
The check also warns when an arrowhead or the line just before it overlaps a label or
crosses another connector, excluding endpoint joins and lines that lie along one another.
A separate warning names the box and the existing connection when a return arrow running
left or up enters an occupied side of the box while another side is unused.
The check also warns when a connector takes a short detour around its box and names
another permitted side that provides a straight route clear of connectors, labels and
boxes.

The layout check reports clipped body content and title text that extends outside the
title bar or overlaps an image in it.
Check the current artifact with `layout(artifact=...)`: it waits for the check, and an
empty `errors` means the current revision has no layout errors.

## Planning files

Keep `<artifact>.FLOORPLAN.md` beside the edit file and outside the deck. Update it before adding, splitting, or removing pages. Record page questions, sources, and revision history. Include a term ledger naming the page and element that defines each unfamiliar term. Fix missing or late definitions before handoff.

## Visual reference inputs

When a drafting tool accepts images, supply requested visual reference images as inputs. A description of the reference does not replace the images.

## Connector routing

For box-and-arrow diagrams, prefer horizontal and vertical connectors unless another route clarifies the relationship. Join connectors entering the same element near their sources. Split connectors leaving the same element near their targets. Keep branches short and the common segment long. Preserve direction and make each source-to-target relationship unambiguous. Follow the content guideline's rules for entry and exit sides and for which paths may merge. Remove a bend or detour when another permitted entry or exit side avoids it without changing reading order or intended connections, obscuring junctions, or adding crossings or label overlaps.

## Standard plots

Use a plotting tool that supplies the required axes, scales, and annotations for a standard plot. Do not rebuild these by hand.

## Image proportions and readability

Preserve the source width-to-height ratio of images, including `<img>` figures, images inside SVG, and CSS backgrounds. At the intended display or export size, check the rendered image itself, excluding padding and letterboxing, for correct proportions and readable text and marks needed by the page. A clean layout report does not establish correct proportions or readability.

## Independent review

Start after `layout()` returns an empty `errors` list and the content guideline's Article 7 checks pass. Run one review round by default, with another only at the requester's direction.

Use a reader who did not build the deck, such as a new agent or session. Give that reader only the built deck to view, page images from `image()`, and the instruction below. Do not provide the guideline, template documentation, planning files, sources, or an account of how the deck was made.

Record one row per finding in a table with columns `Page`, `Finding as stated`, `Kind`, `Decision`, and `Action or reason`. Use `wording`, `logic`, `inconsistency`, or `layout` for kind and `adopt`, `reject`, or `hold` for decision. Hold changes that alter meaning or structure for the requester's decision. Fix adopted findings, rerun your content and layout checks on affected pages, and include the table in the handoff report.

Copy this instruction to the reviewer:

```text
Review every supplied page as a reader, using only the rendered deck. Do not inspect markup or hidden notes, consult other material, or edit the deck.
Read for wording that interrupts understanding, including undefined terms, implementation names that replace needed explanations, phrases without an actor or action, and several terms used for one meaning. Read titles, leads, and takeaways in order for jumps, repetition, and conclusions without premises. On each page, check whether visible evidence supports the takeaway, how any difference used to justify it leads to the conclusion, whether comparisons identify both sides, and whether each visible citation clearly identifies the claim or evidence it refers to.
Always check for titles or takeaways that contradict figures, evaluative words such as sufficient, limited, or negligible without support on the page, later pages that repeat earlier ones, and contents or overviews that disagree with the body. Check for conflicting values of the same quantity under the same conditions, totals that do not add up, unexplained changes in units or periods, and values with no source or derivation that are not labeled illustrative or assumed.
Seek at least three specific findings and order them by what to fix first. For each, give the page number, quote the relevant visible text, and explain the problem. For conflicts across pages, identify and quote both pages. Report only findings supported by what is visible. If fewer than three are supported, report those and state that fewer were found.
```

## Report template

`neutral-report` builds an A4 report from the same content format (one section per
page). Its components: `p.lead`, `p`, `p.note`, `ul.notes`, `h3`, `div.callout`,
`div.metrics` with `div.metric`, tables with `pos`, `neg`, `nw`, `div.two`, `figure` with
`figcaption`, and `code`. It ships its own `build.py` and `template.css` rather than the
shared slide engine.
