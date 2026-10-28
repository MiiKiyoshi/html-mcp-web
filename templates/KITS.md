# Artifact Kits

Artifact Kits are what every artifact is built from, whatever its template, skin or layout. These articles say how content uses them. Consult the article needed for the current figure or page, and read [PRODUCTION.md](PRODUCTION.md) in full for production rules.

## Article 1. Principles

1.1 One feature has one markup. A feature in Articles 2 to 8 is written the same way in a deck, under any skin, and in a report, and every template takes it from the same code.

1.2 One feature has one result on every output. What the browser shows, the printed PDF and the PowerPoint export carry the same text, marks, numbers and figures. Article 8 names what an export turns into another form.

1.3 Content names a role, never a look. A highlight, a table, a citation or a formula is marked by what it is, and the skin and the layout decide its colour, size and face. A style attribute does not restate what a component already sets.

1.4 A layout adds only what its kind of document has. Article 9 lists what only a deck has and Article 10 what only a report has, and the look each gives the shared features. A component of Article 9 is not drawn in a report.

## Article 2. The content file

2.1 `<title>` is the document's title. `<body>` carries `data-author`, the author line, and `data-meta`, further lines separated by `|`. Optional `data-sub` adds a subtitle.

2.2 `data-lang` on `<body>` names the language the content is written in, `en` when it is absent. A document declared `ko` breaks Korean lines only between words, in every layout, and sets Hangul in Noto Serif CJK KR and Noto Sans CJK KR, which the builder subsets to the characters the document uses and embeds, so the layout check, the PDF and every reader break the same lines. In a document declared `ko`, `ja` or `zh`, the builder marks each run of Latin letters outside math and code as English, so a layout that hyphenates breaks those words by English rules. A justified line of a `ko` document spreads its slack between Korean letters as well as between words, and inside those English words only between words. In such a document a line may also end before an opening parenthesis written against a word of two letters or more, as in `SGS-LoRA(Self-Gated`.

2.3 Each direct `<section>` of `<body>` is one part of the document with its name in `data-title`. Article 9 says what a part is in a deck and Article 10 in a report.

2.4 `<ol class="references">` directly in `<body>`, outside all sections, defines the references under Article 7.

## Article 3. Text

3.1 `p` carries prose. `p.note` carries one explanatory note and `ul.notes` several, one per `li`. `p.lead` is an optional introduction whose inclusion and wording the configured content guideline governs.

3.2 `pos` and `neg` mark an improvement and a regression. `nw` keeps a short label or status on one line.

3.3 `code` carries identifiers. `pre` carries a code or file excerpt over several lines and keeps its line breaks. Both are set in Deck Mono, a subset of Noto Sans Mono that the builder embeds whenever either occurs, so the layout check and every reader use the same code face. How each is drawn is the layout's, under 9.12 and 10.7.

3.4 `<mark data-hl="N">` colours a span by its role, with `N` from 1 to 5. A `<mark>` without `data-hl` takes role 1. It works in prose, table cells, lists, `code`, `pre`, and the HTML of an SVG `<foreignObject>`. The roles are light tints and the text keeps its own colour. The skin sets `--hl-1` to `--hl-5`, so content marks a role and never writes a colour. The browser fits the colour to the letters, so a figure needs no rectangles sized to its text. Fields in the lines of a file shown in a figure are marked in a `pre` inside a `<foreignObject>`:

```html
<foreignObject x="20" y="40" width="400" height="60">
  <pre style="margin: 0"><mark data-hl="1">key</mark> item <mark data-hl="2">0.5</mark></pre>
</foreignObject>
```

3.5 `p.hl-legend` names the roles with the same marks, each holding its role's name, as in `<p class="hl-legend"><mark data-hl="1">key</mark> <mark data-hl="2">value</mark></p>`. It also works inside a `<foreignObject>`.

## Article 4. Tables and units

4.1 Every cell of a `table` aligns left. `table.num` marks a table of numbers: its first column aligns left and the others right, and each cell aligns by the column it occupies under `rowspan` and `colspan`. A head cell spanning several columns is centred over them. `sep` on a cell draws a column boundary at its left.

4.2 `p.units` carries shared metrics, units, values shared by every row, brief metric definitions, and notation keys for a table or plot. Production clause 2.2 governs its placement and its consistency across pages.

4.3 `div.table-fit` sizes a compact table to its contents and centres it, as in `<div class="table-fit"><p class="units">…</p><table>…</table></div>`. The table's `p.units` goes inside the same wrapper, before the table, so it ends at the table's right edge, and a key longer than the table wraps to its width.

4.4 The rows of `th` cells at the top of a table are its head, written in a `thead` or not. Rows after it may be split into several `tbody` groups, such as a row of averages after the designs.

4.5 A table too wide for its place shares the width as LaTeX's tabularx does. A column whose longest line fits in an even share of the width left keeps that line whole, and the columns of longer text divide the rest and wrap.

## Article 5. Figures

5.1 Inline `<svg>` carries a figure with exact labels that stay sharp in print. The element takes the width it is given, and in a deck it stops at its `max-height`. The drawing keeps its `viewBox` proportions inside that box, so a differently shaped `viewBox` leaves unused bands. Production clause 2.3 governs the box and drawing size.

5.2 A formula or other HTML in a figure goes in a `<foreignObject>` placed and sized where it belongs, holding HTML such as `<div style="font-size: 18px">$…$</div>`, directly in the `<svg>` and not in a `<g>`. The `<svg>` needs a `viewBox` and the default `preserveAspectRatio`. A `<foreignObject>` can hold an equation followed by its HTML definition list within the same panel or column. The builder draws the HTML over the figure at that place and scale, in the middle of the `<foreignObject>` from top to bottom, and it renders like body text on screen and in print, with no margin around a display formula. A formula in an SVG `<text>` stops the build.

5.3 One `<text>` holds a complete label. `data-wrap="<width>"` gives its available width in `viewBox` units, and the document breaks it into lines when it opens, in the document's own face. Lines break at spaces and, inside a run of Latin letters, at an English hyphenation point with at least two letters before it and three after, where the line keeps a hyphen. A word in another script, such as a Korean word, is never broken. `x` and `y` start the first line. `data-align` is `left` (the default), `center` (`x` is the middle of every line), `justify` (spaces widen every line but the last to the full width) or `balance` (the same line count at the narrowest width, so the last line is no shorter than the rest). `data-line-height` gives the step between lines in font sizes, 1.35 by default. Text is plain, and a nested `tspan` contributes only its words. `data-max-lines="<n>"` sets the allowed line count.

5.4 `data-fit="<width>x<height>"` gives a label a whole box instead, and `data-fit-range="<smallest> <largest>"` its font sizes, 8 to the document's own size by default. The largest size in half-pixel steps whose lines fit the height is chosen, and the smallest is drawn when none fits. `data-fit-stretch` sets when lines are reported loose, 2 by default: under `justify` a space may widen to that multiple of a natural space, otherwise a line may fall to the width divided by it. 1.5 suits a row of cards that must read evenly.

5.5 `<img>` carries a raster figure. Production clause 2.4 governs `max-height`, proportions and readability.

5.6 `data-center` on a `<text>` sets the middle of its letters at `x` and `y`, so a label set on a shape takes the shape's middle there, as in `<text x="150" y="120" data-center>+</text>` on `<circle cx="150" cy="120" r="10"/>`. The letters' extent is measured in the label's own face, italic overhang included, and the label is moved by `dx` and `dy`. Its `dominant-baseline` is replaced. `data-center="x"` centres across only and keeps the baseline at `y`, and `data-center="y"` centres down only and keeps `text-anchor`. A centred label is one line of plain text, and the build stops on one holding markup or with `data-wrap` or `data-fit`. On a `<foreignObject>`, `data-center` sets the middle of its HTML's letters, a fraction's rule and a root's sign included, at the middle of the `<foreignObject>`, with the same `"x"` and `"y"`. A report keeps the positions measured when its pages were set (10.13), and a deck measures them when it opens.

## Article 6. Math

6.1 `$…$` is inline math and `$$…$$` display math. `\(…\)` and `\[…\]` also work. A literal dollar sign is `\$`, since two plain dollar signs on one line otherwise read as a formula.

6.2 KaTeX renders the math, and its renderer and fonts are embedded, so the file is self-contained and prints as it displays. A document without math carries none of them. The same formula gives the same markup in every layout. Its size against the text is the layout's: a deck sets inline math at KaTeX's 1.21 times the text and a display formula at its paragraph's size, and a report sets both at the text's own size, as TeX does.

6.3 An equation with its definitions under production clause 2.8 keeps them in one wrapper:

```html
<div>
<p>$$A = \pi r^2$$</p>
<ul>
<li>$r$: circle radius · $A$: circle area</li>
</ul>
</div>
```

Short definitions may share an item, with the middle dot outside the math delimiters. In a report, write the equation as `<p class="eq">` inside the wrapper so it takes its number (10.5).

## Article 7. References and citations

7.1 Each reference in `ol.references` is one `<li id="key">…</li>`. A citation is `<cite>key</cite>` or `<cite>key1, key2</cite>`, in text or in the `<text>` of an inline `<svg>`.

7.2 References are numbered in the order first cited across the document, and citations show bracketed numbers such as `[1]` or `[2, 1]`, kept on one line in a wrapped label. Uncited references are not listed. Where the list stands is the layout's, under Articles 9 and 10.

7.3 A missing or duplicate reference ID or an undefined citation key stops the build.

## Article 8. Outputs

8.1 The printed PDF is the pages as the browser lays them out, with their backgrounds and highlights.

8.2 PowerPoint export makes each slide's text, tables and shapes editable at their places. A highlight becomes the run's highlight in its colour. An SVG figure stays a vector and the HTML over it becomes a picture over the vector. A paragraph, list item or table that holds math becomes one picture of itself, so its text is not editable. A report is printed, not exported to PowerPoint.

## Article 9. Decks

9.1 A section is a body page with a title bar unless `data-layout` is `contents` or `divider`, which omit the bar and fill the page.

9.2 A contents page lists the parts:

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

`data-title` draws the heading and the rule under it. Each outer `<li>` takes its number in list order, and a continuation page with `<ol start="3">` begins at 03. `span.venue` sets smaller text before the name and `span.by` after it. One `<ul>` at the end of an outer `<li>`, after its own text, defines subitems: unnumbered smaller lines under the item's text, each after a short solid bar in the text colour. Subitems do not affect the numbering.

A list with subitems and at least two outer items stays in one column while it fits and takes two when one overflows, measured in the skin's type. Items fill the left column, then the right, and an outer item does not split. `data-columns` from 1 to 9 sets the count: `1` keeps one column and `2` gives two even without subitems, with long items wrapping in their column. A skin picture behind a list in columns fades. `data-scale`, a positive number such as `0.8`, scales the whole list, numbers and subitems included, from its top left while the heading keeps its size, which leaves unused space on the right even with columns. Production clause 2.1 gives the order for adjusting columns and scale.

9.3 A divider opens a part:

```html
<section data-layout="divider" data-no="01">
  <p class="label">Section name</p>
  <img class="shot" src="figures/opening.png" alt="">
</section>
```

`data-no` is the part's number, set beside its name in `p.label`. An optional `img.shot` places a picture to the right.

9.4 `data-appendix` on a section marks it and every later page as an appendix held for questions, usually on the divider that opens it. The footer counts the main deck, cover included, and stops before the appendix, whose pages count on their own, as `A1 / A8`. Without `data-appendix` the footer counts the whole deck, and a divider alone does not start appendix numbering.

9.5 Blocks are spread down the body. A first `p.lead`, one line under the title, stays with the title and an optional final `p.takeaway` near the bottom, and only the content between them shares the remaining height. The items of a `ul.notes` directly in the body or in a column of `two` (9.8) take that height first, up to one line between each pair. Related compact content under neutral clause 5.5 goes in one wrapper so it moves as one block.

9.6 `p.takeaway` is the concluding line, at most one per page, as the last direct paragraph after the page's figure, table or other content: `<p class="takeaway">The concluding statement.</p>`. It works with or without a lead, takes the lead's type, spans the body and is centred.

9.7 A table fills its container unless it is in a `div.table-fit` (4.3). `table` gives standard spacing, `table.dense` serves rows that outgrow it, and `table.tight` a wide numeric table whose cells must not wrap, as in `<div class="card table-fit"><table class="dense tight">…</table></div>`.

9.8 `card` is a boxed panel holding a short group of content. `grid3` holds three `metric` cards, each a large number over its label, optionally marked `win` or `lose`. `two` holds two columns of content and `card`, sharing the row's height: a column wrapped in a `div` spreads its blocks over it, while a `card` or `pre` alone in a column keeps its own height at the row's middle. In a 1200px body `two` splits the width into 622px and 541px.

9.9 `flow` holds four `step` blocks, and `flow.cycle` has the last step feed the first. `p.feedback` carries feedback received, and `div.concerns` points raised about the work, a `<b>` label on its own line followed by a list or paragraph.

9.10 Each page lists the references it cites, with their numbers, in small type at the bottom right of the body below the takeaway, one line each, their left edges aligned and the longest line ending at the body's right edge. A citation in a script or on a cover, contents or divider page stops the build.

9.11 One `aside.script` in a section is that page's speaker script. It becomes the PowerPoint notes and is left out of the PDF and the presentation view.

9.12 `code` is drawn as a chip. `pre` is one box whose long lines overflow rather than wrap, and a `code` inside it drops the chip.

## Article 10. Reports

10.1 A report is a two-column paper on A4. The text of all sections runs on as one flow from column to column and page to page: a paragraph cut at the foot of a column goes on at the head of the next, and a list is cut between its items.

10.2 The title, `data-sub`, `data-author` and the lines of `data-meta` stand centred across the top of the first page.

10.3 `<section data-title="Abstract" data-abstract>` is the abstract, with an unnumbered head. Every other section is numbered by the builder, so `data-title` carries the name alone, and an `h3` in a numbered section is a numbered subsection. A section with `data-layout` stops the build, since contents and divider pages belong to a deck.

10.4 A `figure` holds one `figcaption` with no number of its own. A figure holding a `table` is numbered as a table with its caption above, any other as a figure with its caption below. `figure.wide` spans both columns at the top of the next page, and wide figures stack there while they fill no more than 0.7 of it, the rest waiting for the page after. Any other figure or table stands at the top of a column, as LaTeX's `[t]` places it: at the top of the column it falls in while that column holds only figures, else at the top of the next, while the text goes on. Figures waiting for a column stack there in their order while they fill no more than 0.7 of it, so none comes before the place it is written and the numbers keep their order. On the first page a column's top is under the title block.

10.5 `p.eq` holds a displayed equation and takes its number at the right.

10.6 The cited references are listed after the last section.

10.7 `code` is set in the text without a chip, and `pre` in the column with long lines wrapped at its edge.

10.8 A report has no lead or takeaway line: `p.lead` is set as an ordinary paragraph and `p.takeaway` is not used.

10.9 A table is drawn as booktabs draws it, in 8pt: a heavy rule above and below, a light rule under the head and between `tbody` groups, and a short thin rule under each head cell that spans a group of columns. Neighbouring cells stand 9pt apart, and a figure or table stands 12pt from the text around it.

10.10 Text is set 9pt on a 10.95pt line, and a `ko` document on an 11.78pt line, which sets 53 lines in a column. Paragraphs and lists of a section stand 3pt apart besides each paragraph's indent, and text under the figures at a column's top stands 20pt below them. Every column but those of the last page ends on the foot of the text area: what is left goes first, evenly, to the space between paragraphs and list items, up to 4pt more each, then above heads, around figures and under the title block or wide figures, up to 12pt more each. The last page's two columns end level. All of this is the report engine's, so every report skin has it.

10.11 A section or subsection head stands with what can begin under it in the same column: two lines of a paragraph, all of a paragraph of three lines, or the first item of a list. Otherwise it goes on to the next column, and a section head right above a subsection head goes with it.

10.12 A justified line opens no word space wider than two thirds of the text's size, 6pt in 9pt text. A justified Korean line spreads its slack over its Hangul letters and word spaces alike, a letter taking no more than `--letter-cap`, 0.05em, and the word spaces the rest. A Latin word, a number, a bracket or a citation in a Korean line is never opened between its letters.

10.13 The pages are set once, when the report is built: Firefox pours the text into the columns, and every line it made is written into the file as a block of its own, with the column widths of every table. A justified line keeps the spacing Firefox spread it with, written as letter spacing between its Hangul letters and word spacing between its words, and is not justified by the browser again. Every line with word spaces also carries the width Firefox gave it, and a browser that advances a glyph or a formula a fraction of a pixel differently brings the line back to that width through its word spaces. A reader's browser, the review page, the layout check and the PDF all draw those lines and do not pour again. Building a report needs Firefox.

## Article 11. Layout check reports

11.1 `layout(artifact=...)` checks the current document and `layout(artifact=..., page=...)` one page. It waits for the check. An empty `errors` means the current revision has no layout errors. `warnings` lists likely faults the check cannot confirm and is left out when there are none: a report column ending short of its foot (11.2), and under the neutral guideline an SVG plot that numbers an axis without naming it in the drawing, which a title outside the drawing also clears. The same call returns blocks and free space. Build failures appear as described in [README.md](README.md#with-a-template).

11.2 The check reports clipped body content, title text outside the title bar or over an image in it, and on contents and divider pages overflow anywhere above the footer bar, using the scaled size of a contents list. On deck pages it reports a text block outside `pre` whose last line is no wider than six font sizes or a quarter of its widest other line, quoting that line's words, and overflowing lines in `pre`. On report pages it reports the same of a paragraph or list item outside the references, and a paragraph that runs on into the next column is judged by its last part against the lines of all its parts. It also reports a head standing at a column's foot without two lines of its text (10.11), and a paragraph or list item whose justified line opens a word space or its Korean letters past 10.12, naming the width and quoting the line. Under `warnings` it lists a column that ends more than 1pt above the foot of the text area on any page but the last (10.10), with how far.

11.3 For inline SVG it reports shapes beyond the `viewBox`, borders of rectangles, circles, ellipses and polygons cut at the `viewBox` edge, empty space of a quarter or more of a side, overlapping labels, and labels beyond the sides of the rectangle they sit on, naming the side and the excess. It reports a label whose letters' middle stands more than 0.5px from the middle of the shape it is set on, naming how far across and down, and 5.6 is the remedy. A label is taken as set on a rectangle, circle or ellipse when it is centred (`text-anchor="middle"` or `data-center`), its letters' middle is the only one in that shape, and the shape is at most five times as tall as its letters.

11.4 Connector errors cover an arrowhead or the line just before it over a label or crossing another connector, endpoint joins and lines along one another excepted. A separate error names the box and existing connection when a return arrow running left or up enters an occupied side while another side is unused. Another reports a short detour around a box and names a permitted side with a straight route clear of connectors, labels and boxes. A step that joins facing sides of two boxes and turns in the gap between them is not a detour.

11.5 For the HTML of a `<foreignObject>` it reports a line printed over a label and a line past the sides of the rectangle it sits on, as for labels. The `<foreignObject>`'s own box is not a limit.

11.6 A wrapped label past `data-max-lines` reports `needs N lines, box allows M`. A fitted label past `data-fit-stretch` reports such as `is loose in 196x92 at 12px`, and one no size fits such as `does not fit 196x92 at 10px`.
