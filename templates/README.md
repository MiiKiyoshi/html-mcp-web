# Authoring a paged HTML document

Edit the `edit_file` that `guide()` names. Read this entry once when creating a document and reuse the existing markup conventions for later edits.

## Reading the documents

Read [PRODUCTION.md](PRODUCTION.md) in full for production rules and checks. Read the configured content guideline and the template's own README listed by `guide()`. Content guidelines govern what the document says and shows. [The guideline directory](../guidelines/README.md) describes the packages.

Consult [COMPONENTS.md](COMPONENTS.md) only by the section needed for the current component or layout report. Read [SKINS.md](SKINS.md) when developing a skin.

A suggestion the reviewer applies is written only into the edit file. Regenerating from a script or an earlier copy loses it unless that source also contains the change. For regeneration, follow [neutral clause 8.4](../guidelines/neutral/GUIDELINE.md#article-8-resolve-the-review-request).

## With a template

`init --template <name> --content content.html --main slides.html` creates missing source files and builds the output. Edit the content file. The template rebuilds the main file on save. Build failures appear as `build_error` in `layout()`.

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

The slide engine adds a cover, then one page per section. `data-meta` uses `|` for line breaks. Optional `data-sub` adds a cover subtitle. Each page can have one `aside.script`. Slide scripts become PowerPoint notes and are excluded from PDF and presentation view. Report templates have their own notes and page support.

Image paths are relative to the project directory containing `.html-mcp-web.yaml`, not the content file.

## Without a template

`init` creates a minimal document at `--main` if the file does not exist. Its body contains only `main.pages`, whose page children are `section.page`. The viewer, layout checker, and exporter use that structure. Each slide is 1280 × 720 CSS pixels. Each report page is A4 (210 × 297 mm).

## Before handoff

Follow production Article 3 to check an edit and Article 4 for independent review of a new deck or a revision across the deck.
