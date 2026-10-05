# Component reference

Consult the section needed for the current figure or page. Read [PRODUCTION.md](PRODUCTION.md) in full for production rules.

## Page kinds

A section is a body page with a title bar unless `data-layout` is `contents` or `divider`. These two page kinds omit the title bar and fill the page.

### Contents

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
```

`data-title` draws the heading and the rule under it. Each outer `<li>` takes its number from a CSS counter in list order. A continuation page with `<ol start="3">` begins at 03. `span.venue` sets smaller text before the name and `span.by` after it.

One `<ul>` at the end of an outer `<li>`, after its own text, defines subitems. They do not affect numbering. Each appears in smaller type as an unnumbered line aligned under the item's text, preceded by a short solid bar in the text colour.

A list with subitems and at least two outer items stays in one column while it fits and takes two columns when one overflows. Measurement uses the skin's type. Items fill the left column from top to bottom, then the right. An outer item does not split across columns.

`data-columns` on the section accepts a whole number from 1 to 9. `data-columns="1"` keeps one column. `data-columns="2"` gives two columns even without subitems. Long items wrap in columns. Any skin picture behind a list in columns fades.

`data-scale` on the section accepts a positive number. For example, `data-scale="0.8"` scales the whole list, including numbers and subitems, from its top left. Reducing the scale leaves unused space on the right even with columns. The heading and its rule keep their size. Production clause 2.1 gives the order for adjusting columns and scale.

### Divider

```html
<section data-layout="divider" data-no="01">
  <p class="label">Section name</p>
  <img class="shot" src="figures/opening.png" alt="">
</section>
```

`data-no` is the number in the capsule. `p.label` is its text. An optional `img.shot` places a picture to the right.

### Appendix

`data-appendix` on a section marks it and every later page as an appendix held for questions. It usually appears on the divider that opens the appendix. The footer counts the main deck, including the cover, and stops before the appendix. Appendix pages have their own count, such as `A1 / A8`. Without `data-appendix`, the footer counts the whole deck. A divider alone does not start appendix numbering.

## Body arrangement

Blocks spread down the body. A first `p.lead` stays with the title. An optional final `p.takeaway` stays near the bottom, above any references. Neither participates in the spread. Only the content between them shares the remaining height.

### Lead, takeaway, and notes

`p.lead` is an optional introduction on one line under the title. The configured content guideline governs its inclusion and wording. Normal `p` carries prose.

`p.takeaway` is the concluding line. A body section accepts at most one, as its last direct paragraph after its figure, table, or other content. It works with or without a lead. The common builder applies the skin's `lead` class to it, so both lines share typography. The takeaway spans the body width and its text is centred. The lead keeps its own alignment and width. Markup is `<p class="takeaway">The concluding statement.</p>`. Skins style its appearance.

`p.note` carries one explanatory note. `ul.notes` carries several, one per `li`.

## References and citations

`<ol class="references">` defines the deck's references once, directly in `<body>` outside all sections. Each reference is one `<li id="key">…</li>`. A citation is `<cite>key</cite>` or `<cite>key1, key2</cite>`, in text or inside the `<text>` of an inline `<svg>`.

References are numbered in the order first cited across the deck. Citations show bracketed numbers such as `[1]` or `[2, 1]`, kept on one line in a wrapped label. Each citing body page lists only its own references with those numbers in small type at the bottom right of the body, below the takeaway. Each reference occupies one line. Their left edges align and the longest line ends at the body's right edge. Uncited references are not shown.

Missing or duplicate reference IDs and undefined citation keys stop the build. Citations in scripts or on cover, contents, or divider pages also stop the build.

## Tables and units

`p.units` sits directly above a measurement table and states units once, as in `ΔTNS: ns · power: %`, instead of repeating them in footnotes. Production clause 2.2 governs consistency across slides.

`table` gives standard spacing. `table.dense` serves rows that outgrow that spacing. `table.tight` serves a wide numeric table whose cells must not wrap. The first column aligns left and the others right. Each cell aligns by the column it occupies under `rowspan` and `colspan`.

`pos` and `neg` mark an improvement and a regression. `sep` draws a column boundary. `nw` keeps a short label or status cell on one line.

## Cards and columns

`grid3` contains `metric` cards, optionally marked `win` or `lose`.

`two` contains normal content and `card`. Its two columns share the row's height. A column wrapped in a `div` spreads its blocks over that height. In a 1200px body, `two` splits the width into 622px and 541px.

## Flow and feedback

`flow` contains four `step` blocks. `flow.cycle` represents a last step that feeds the first.

`p.feedback` carries received feedback. `div.concerns` carries points raised about the work, with a `<b>` label on its own line followed by a list or paragraph.

## Code

`code` and `pre` use Deck Mono by default, a subset of Noto Sans Mono. The builder embeds this face whenever either element occurs, so the layout check and browsers use the same code face.

`code` carries identifiers. `pre` carries a code or file excerpt over several lines. It draws one box and preserves line breaks. A `code` inside it drops the inline chip. Long lines overflow rather than wrap.

## SVG figures

Inline `<svg>` carries a figure with exact labels that remain sharp in print. The element takes the width it is given and stops at its `max-height`. The drawing keeps its `viewBox` proportions inside that box. A differently shaped `viewBox` leaves unused bands at the sides or at the top and bottom. Production clause 2.3 governs the box and drawing size.

### Formulas in SVG

A formula inside inline SVG uses a `<foreignObject>` placed and sized where it belongs, holding HTML such as `<div style="font-size: 18px">$…$</div>`. The `<foreignObject>` belongs directly in `<svg>`, not in a `<g>`. The SVG needs a `viewBox` and the default `preserveAspectRatio`.

The builder draws the HTML over the figure at that place and scale. It renders like a body formula on screen and in print, with no margin around a display formula. A formula in SVG `<text>` stops the build. In PowerPoint export, the figure remains a vector and the formula becomes a picture over it.

### Wrapped labels

One `<text>` holds the complete label. `data-wrap="<width>"` gives its available width in `viewBox` units. The deck breaks it into lines when it opens, using the skin's font. The content file needs no manually placed lines. A word broken across lines keeps a hyphen at the end of its line.

`x` and `y` start the first line. `data-align` accepts these values:

| Value | Effect |
| --- | --- |
| `left` | Default alignment |
| `center` | `x` is the middle of every line |
| `justify` | Spaces widen every line except the last to the full width |
| `balance` | Keeps the same line count at the narrowest possible width so the last line is no shorter than the rest |

`data-line-height` gives the step between lines in font sizes, with a default of 1.35. Text is plain. A nested `tspan` contributes only its words. `data-max-lines="<n>"` sets the allowed line count.

### Labels fitted to a box

`data-fit="<width>x<height>"` gives the whole box. `data-fit-range="<smallest> <largest>"` sets the font size range. By default the bounds are 8 and the skin's own size. The deck chooses the largest size in half pixel steps whose lines fit the height under `data-line-height`. If no size fits, it draws at the smallest size.

`data-fit-stretch` sets the threshold for reporting loose lines, not for choosing font size. Its default is 2. Under `justify`, a space may widen to that multiple of a natural space. For other alignments, a line may fall to the available width divided by that value. A value of 1.5 gives a tighter threshold for rows of cards that must read evenly.

## Raster figures

`<img>` carries a raster figure. Production clause 2.4 governs `max-height`, proportions, and readability.

## Math

TeX delimiters are `$…$` for inline math and `$$…$$` for display math. `\(…\)` and `\[…\]` also work. The builder renders math with KaTeX and embeds the renderer and fonts in the file. The deck is self contained and prints as it displays. A deck without math carries none of these resources. A literal dollar sign is `\$`. Two plain dollar signs on one line otherwise read as a formula.

## Layout check reports

`layout(artifact=...)` checks the current document. `layout(artifact=..., page=...)` selects a page. It waits for the check. An empty `errors` means the current revision has no layout errors. The same call returns blocks and free space. Build failures appear as described in [README.md](README.md#with-a-template).

The check reports clipped body content and title text outside the title bar or overlapping an image in it. On contents and divider pages, it reports overflow anywhere above the footer bar. For contents lists, it uses the scaled list size and reports a wasted last line in columns. It also reports overflowing lines in `pre`.

For inline SVG, it reports shapes beyond the `viewBox`, empty space occupying a quarter or more of a side, overlapping labels, and labels beyond the sides of the rectangle they sit on. For the last case, it names the side and excess.

Connector warnings cover an arrowhead or the line just before it overlapping a label or crossing another connector. Endpoint joins and lines along one another are excluded. A separate warning names the box and existing connection when a return arrow running left or up enters an occupied side while another side is unused. Another warning reports a short detour around a box and names a permitted side with a straight route clear of connectors, labels, and boxes. A step that joins facing sides of two boxes and turns in the gap between them is not a detour.

For wrapped labels, exceeding `data-max-lines` reports `needs N lines, box allows M`. A fitted label past the `data-fit-stretch` threshold reports a message such as `is loose in 196x92 at 12px`. If no size in `data-fit-range` fits, the message is such as `does not fit 196x92 at 10px`.

## Report template

`neutral-report` builds an A4 report from the same content format, with one section per page. Its components are `p.lead`, `p`, `p.note`, `ul.notes`, `h3`, `div.callout`, `div.metrics` with `div.metric`, tables with `pos`, `neg`, `nw`, `div.two`, `figure` with `figcaption`, and `code`. It has its own `build.py` and `template.css` rather than the shared slide engine.
