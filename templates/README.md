# Authoring a paged HTML document

Edit the `edit_file` that `guide()` names. Read this guide once when creating a
document, and reuse the existing structure for later edits. Template-specific notes
and any configured guideline are listed by `guide()` beside it. A suggestion the
reviewer applies is written into that file only, so a page you regenerate from anything
else, such as a script or an earlier copy, loses it unless you carry the change there first.

## With a template

`init --template <name> --content content.html --main slides.html` creates missing
source files and builds the output. Edit the content file; the template rebuilds
the main file on save. Build failures appear as `build_error` in `layout()`.

```html
<!doctype html>
<meta charset="utf-8">
<title>Document title</title>
<body data-author="Author" data-meta="Affiliation|Second line">
<aside class="script"><p>Cover speaker notes.</p></aside>
<section data-title="Page title">
  <!-- Optional lead. Follow the configured guideline for its use and wording. -->
  <p class="lead">Page introduction.</p>
  <!-- Figure, table, or other content. -->
  <p class="takeaway">The answer supported by the content.</p>
  <aside class="script"><p>Speaker notes for this page.</p></aside>
</section>
</body>
```

The slide engine adds a cover, then one page per section. `data-meta` uses `|` for
line breaks; optional `data-sub` adds a cover subtitle. Each page can have one
`aside.script`; slide scripts become PowerPoint notes and are excluded from PDF
and presentation view. Report templates have their own notes and page support.

Image paths are relative to the project directory containing `.html-mcp-web.yaml`,
not the content file. Keep the template's page geometry. An inline SVG's `viewBox`
should match its displayed box; give raster images a maximum height and preserve
their aspect ratio.

For page kinds, tables, figures, math, or long SVG labels, consult only the relevant
section of [the component reference](COMPONENTS.md). For developing a template rather than writing content,
see [Developing a skin](SKINS.md).

## Without a template

`init` creates a minimal document at `--main` if the file does not exist. Its body
contains only `main.pages`, whose page children are `section.page`. Keep that
structure: the viewer, layout checker, and exporter use it. Each slide is
1280 × 720 CSS pixels; each report page is A4 (210 × 297 mm).

## Verify an edit

Render the affected page with `image()` and read it as the intended audience. Use
`layout(artifact=..., page=...)` for its errors. It waits for the check, and an empty
`errors` means the current revision has none. Fit alone does not establish that the
explanation is understandable. Read that page's blocks and free space, which the same
call returns, only when the rendered page leaves a placement or spacing question
unresolved.
After your own checks pass, complete the
[independent review](COMPONENTS.md#independent-review) before handing off a new deck
or a deck-wide revision.
