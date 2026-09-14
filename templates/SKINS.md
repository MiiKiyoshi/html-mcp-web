# Developing a skin

Copy `templates/neutral-slides` and edit `skin.css`. The variables a skin may set are
listed at the top of two files: `html_mcp_web/components.css` holds the ones a deck
shares with a report (`--accent`, `--paper`, `--line`, `--muted`, …), and
`html_mcp_web/slides/skeleton.css` the ones only a slide has (`--primary`, the title bar
and body box measurements `--tbar-height`, `--body-height`, `--body-padding`, …, and the
footer bar). A skin restates only what it changes.

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
no pptx of its own; its look already lives in `skin.css`. The only thing `skin.json` can
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
