# Authoring a paged HTML document

Edit the file named by `edit_file` in `guide()`'s answer.

## Reading the documents

In each new or resumed context, and after a reset or compaction, call `guide()` and read every file in its `read` list in full before editing.

Consult references in `consult`, including [COMPONENTS.md](COMPONENTS.md), only by the section needed for the current component or layout report. Read [SKINS.md](SKINS.md) when developing a skin. [REVIEWER.md](REVIEWER.md) is the text you copy verbatim to the independent reviewer under [PRODUCTION.md](PRODUCTION.md) Article 4.

## With a template

`init --template <name> --content content.html --main slides.html` creates missing source files and builds the output. Edit the content file. The template rebuilds the main file on save. Build failures appear as `build_error` in `layout()`.

```html
<!doctype html>
<meta charset="utf-8">
<title>Document title</title>
<body data-author="Author" data-meta="Affiliation|Second line">
<aside class="script"><p>Cover script.</p></aside>
<section data-title="Page title">
  <!-- Optional lead. Follow the configured guideline for its use and wording. -->
  <p class="lead">Page introduction.</p>
  <!-- Figure, table, or other content. -->
  <p class="takeaway">The answer supported by the content.</p>
  <aside class="script"><p>Script for this page.</p></aside>
</section>
</body>
```

The slide engine adds a cover, then one page per section. `data-meta` uses `|` for line breaks. Optional `data-sub` adds a cover subtitle. Each page can have one `aside.script`. Slide scripts become PowerPoint notes and are excluded from PDF and presentation view. The report template builds the same cover and pages and leaves scripts out.

Image paths are relative to the project directory containing `.html-mcp-web.yaml`, not the content file.

## Without a template

`init` creates a minimal document at `--main` if the file does not exist. Its body contains only `main.pages`, whose page children are `section.page`. The viewer, layout checker, and exporter use that structure. `--layout slides` makes each page a 1280 × 720 CSS pixel slide, and `--layout report` an A4 page (210 × 297 mm).
