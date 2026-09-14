# Component reference

Read the sections needed for the current figure or page. MCP resource: `html-mcp://docs/components`.

## Page kinds

A section is a body page with a title bar unless `data-layout` names one of the two
full-bleed pages. Those two drop the title bar and fill the page, which is how a deck
marks where one part ends and the next begins. Their guard covers the area above the
footer bar, so overflow is reported the same way.

```html
<section data-layout="contents" data-title="Contents">
  <ol>
    <li>Background</li>
    <li><span class="venue">Venue</span>Name of the work<span class="by">(authors)</span></li>
  </ol>
</section>

<section data-layout="divider" data-no="01">
  <p class="label">Section name</p>
  <img class="shot" src="figures/opening.png" alt="">
</section>
```

- `contents`: `data-title` draws the heading and the rule under it, and each `<li>` takes
  its number from a CSS counter, so list order is the numbering. `span.venue` sets
  smaller text before the name and `span.by` after it.
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
an optional final `p.takeaway` stays at the bottom of the body. Neither participates in
the spread; only the content between them shares the remaining height.

- `p.lead` is the one-line summary under the title; normal `p` carries prose
- `p.takeaway` is the concluding line at the bottom. Put at most one as the last direct
  paragraph of a body section, after its figure, table, or other content. It works with
  or without a lead. The common builder applies the skin's `lead` class to it, so both
  lines share the same typography and width in every skin. The takeaway's paragraph
  and text are centred in the body; the lead keeps its own alignment.
  Write `<p class="takeaway">The concluding statement.</p>`; skins only style its appearance.
- `p.note` is a single footnote, `ul.notes` takes over once two or more independent
  remarks pile up, one per `li`
- `p.units` sits directly above a measurement table and states the units once
  (`ΔTNS: ns · power: %`), instead of repeating them in footnotes; keep the same form on
  every slide that shows measurements
- standard `table`; `table.dense` when the rows outgrow its spacing; `table.tight` for a
  wide numeric table whose cells must not wrap
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
  Give the `viewBox` the size the figure is drawn at, not a smaller box scaled up: a
  browser misplaces its own selection inside an svg that scales, by the scale factor, so
  the handles a reader drags to widen a selection on a touch screen sit away from the
  letters and collapse the selection when pressed. The review page's highlight and comment
  button are computed from the letters themselves and are right either way
- `<img>` for a raster figure; give it a `max-height` so the body stays inside its box

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

The body box carries `data-layout-guard`, so clipped overflow is reported.
Check the current artifact with `inspect(artifact=...)`: `layout_error_count` is
`null` before verification and `0` when the current revision has no layout errors.

## Report template

`neutral-report` builds an A4 report from the same content format (one section per
page). Its components: `p.lead`, `p`, `p.note`, `ul.notes`, `h3`, `div.callout`,
`div.metrics` with `div.metric`, tables with `pos`, `neg`, `nw`, `div.two`, `figure` with
`figcaption`, and `code`. It ships its own `build.py` and `template.css` rather than the
shared slide engine.
