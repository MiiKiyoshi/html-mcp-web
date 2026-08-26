# Templates: one engine, many skins

A template directory under `templates/` (or `~/.config/html-mcp-web/templates/` for a
private one) is a **skin**. Everything about how a page is put together lives in the
engine inside the package; the skin supplies colours, chrome, and a few measurements.
An improvement to the engine reaches every skin at once, and a skin cannot drift from
the structure the review tools expect.

```
templates/<name>/
  build.py     three-line shim: html_mcp_web.slides.build(content, out, this_dir)
  skin.css     variable overrides and chrome styling
  skin.json    chrome slots and footer labels (optional)
  assets/      images the slots refer to (optional)
  README.md    what this skin looks like and what it changes; nothing else
```

Declare the pair in `.html-mcp-web.yaml` and html-mcp rebuilds on every content save
(build failures appear as `build_error` in the server state and `inspect()`):

```yaml
artifacts:
  slides:
    label: Slides
    layout: slides
    main: slides.html
    template: neutral-slides
    content: content.html
```

Agents edit the content file only. Each build overwrites the main file.

## Content format

```html
<!doctype html>
<meta charset="utf-8">
<title>Cover title</title>
<body data-author="Author line" data-meta="Affiliation 1|Affiliation 2"
      data-sub="Optional line under the cover title">
<aside class="script"><p>Cover greeting.</p></aside>
<section data-title="Slide title">
  ...body html...
  <aside class="script"><p>Speaker script for this slide.</p></aside>
</section>
</body>
```

The cover is generated. `|` in `data-meta` breaks lines. `data-sub` is optional and
carries a second cover line, such as the name of the work a review deck discusses.

An `aside.script` immediately after `body` belongs to the cover; one inside a section
belongs to that slide. Each script is emitted as a `div.script-block` right after its
page, so the normal flow keeps the two together at any window size; it is hidden in the
slide show and left out of print and PDF output. Script paragraphs carry no spacing
between them, so a break in the delivery comes from splitting the sentences rather than
from an empty `p`.

Image `src` paths resolve from the project directory that holds `.html-mcp-web.yaml`,
not from the folder the built file sits in.

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

## Body components

Blocks spread down the body rather than stacking at its top, so a page with little on it
does not leave a dead band above the footer. A first `p.lead` stays with the title and
takes no part in that spread; everything after it shares the remaining height.

- `p.lead` is the one-line summary under the title; normal `p` carries prose
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
- `two` containing normal content and `card`
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
  leaves a band down both sides or across the top and bottom that nothing can use
- `<img>` for a raster figure; give it a `max-height` so the body stays inside its box

Math is written as TeX between `$…$` (inline) or `$$…$$` (display); `\(…\)` and
`\[…\]` work too. The builder renders it with KaTeX and embeds the renderer and its fonts
in the file, so the deck stays self-contained and prints the same as it shows; a deck
with no math carries none of that. A literal dollar sign is written `\$`, since two
plain dollars on one line would otherwise read as a formula.

A figure is content, not styling. CSS outside this vocabulary changes the measured
geometry, and the review server reports what that costs: an inline `<svg>` whose shapes
run past its `viewBox` is reported as cut off, one that leaves a quarter or more of a
side empty is reported as holding space it does not draw in, and two labels printed
over each other are reported as a collision.

The body box carries `data-layout-guard`. Overflow is therefore reported even though
the box clips it. A valid result requires `layout_check.checked_revision == revision`
and an empty error list in `inspect()`.

## Writing a skin

Copy `templates/neutral-slides` and edit `skin.css`. The variables a skin may set are
listed at the top of `html_mcp_web/slides/skeleton.css`; colours (`--primary`,
`--accent`, `--paper`, …), the title bar and body box measurements (`--tbar-height`,
`--body-height`, `--body-padding`, …), and the footer bar. A skin restates only what it
changes.

Chrome images go through named slots declared in `skin.json`, so the builder places
them and the skin only styles them:

| slot | where |
|---|---|
| `cover_band_ornament` | top right of the cover band |
| `cover_band_left`, `cover_band_right` | inside the cover band |
| `cover_bottom_left` | stacked at the cover's bottom left (list allowed) |
| `tbar_logo` | right of the title bar |
| `page_bottom_left` | stacked at a body page's bottom left (list allowed) |
| `full_bottom_left` | same, on full-bleed pages (defaults to `page_bottom_left`) |
| `full_art` | filling a full-bleed page behind its content |

`footer_label` and `cover_footer_label` put text at the right of the footer bar;
`font_links` adds `<link>` or `<style>` tags to the head; `lang` sets the document
language. Images are embedded as data URIs, so the built file opens anywhere.

A skin can carry its own body face. Put the `.woff2` files under `fonts/` and declare
them in `skin.css` with `@font-face { src: url(fonts/NAME.woff2) format("woff2"); }`;
the builder embeds each file as a data URI, the way it embeds KaTeX's fonts, and the
deck then wraps text identically on every machine that opens it. That is also what
lets the review server's layout check speak for what the reader will see: left to the
reader's own fonts, a line that fits on one machine folds on another. Subset the face
to the characters decks use (`fontTools.subset` writes woff2) so two weights stay near
1 MB rather than 10.

The pptx export rebuilds every deck the same way from its rendered HTML, so a skin needs
no pptx of its own; its look already lives in `skin.css`. The one thing `skin.json` can
add for pptx is the deck font, so the file renders the same on a machine that lacks it:

```json
"pptx": {
  "fonts": {"family": "Noto Sans KR", "regular": "fonts/NotoSansKR-Regular.ttf", "bold": "fonts/NotoSansKR-Bold.ttf"}
}
```

`fonts` names static TrueType files beside `skin.json` (`regular`, `bold`, `italic`,
`boldItalic`, any subset) that the export subsets, embeds, and sets every run in as
`family`. The browser-side `.woff2` under `fonts/` cannot serve here because PowerPoint
reads only TrueType outlines (glyf) from a static file, so a skin keeps the `.ttf` next
to its `.woff2`. Without `fonts`, runs are set in Arial and nothing is embedded.
`html-mcp-web` documents the export under "PPTX export" in the repository README.

The neutral skins in this directory carry no organization identity, and the repository
test `tests/test_repository_is_neutral.py` keeps it that way: a private skin lives
under `~/.config/html-mcp-web/templates/` and is never committed here.

## Report template

`neutral-report` builds an A4 report from the same content format (one section per
page). Its components: `p.lead`, `p`, `p.note`, `ul.notes`, `h3`, `div.callout`,
`div.metrics` with `div.metric`, tables with `pos`, `neg`, `nw`, `div.two`, `figure` with
`figcaption`, and `code`. It ships its own `build.py` and `template.css` rather than the
shared slide engine.
