# Authoring a paged HTML document

Edit the file named by `edit_file` in `guide()`'s answer.

## Reading the documents

Read every file in the `read` list of `guide()`'s answer in full before editing. In each new or resumed context, and after a reset or compaction, call `guide()` again and reread those files in full. Content guidelines govern what the document says and shows.

Consult references in `consult`, including [COMPONENTS.md](COMPONENTS.md), only by the section needed for the current component or layout report. Read [SKINS.md](SKINS.md) when developing a skin. [REVIEWER.md](REVIEWER.md) is the instruction production Article 4 copies to an independent reviewer.

## Regenerating pages

A suggestion applied from the viewer is written only into the edit file. Regenerating from a script or an earlier copy loses it unless that source also contains the change. Before regenerating a page, carry applied review changes into its source and check that they survive regeneration.

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
