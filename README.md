# html-mcp-web

Review an AI agent's HTML slides or report from the rendered page while Claude Code or Codex edits the source.

**[Slides example](examples/neutral-slides/)**

![A rendered slide, its highlighted HTML source, and the open review thread in Split view.](docs/hero.png)

**[Report example](examples/neutral-report/)**

![A rendered report page, its highlighted HTML source, and the open review thread in Split view.](docs/report.png)

You open the artifact in a local review page, select rendered text or an exact source range, and comment on it. The agent reads the comment over MCP, edits the HTML, and replies in the same thread. The rendered result, source, and thread stay together, and saving a file refreshes only the artifact frame, so your scroll position and drafts stay put.

```
you:    select text -> write a comment -> press Call agent
                  |
agent:  read comments -> edit HTML -> reply
                  |
you:    read the refreshed page -> comment again
```

## Requirements

- Python 3.10 or newer.
- Firefox, only for PDF or PPTX export.

## Install

```bash
git clone https://github.com/MiiKiyoshi/html-mcp-web.git
cd html-mcp-web
python -m venv .venv
.venv/bin/pip install -e '.[mcp]'
```

Keep this checkout after installation; the installed commands and built-in templates use it.

Register the MCP server once, using the executable inside the venv so it resolves without activation. Run this from the repository directory:

Claude Code:

```bash
claude mcp add --scope user html-mcp -- "$PWD/.venv/bin/html-mcp"
```

Codex:

```bash
codex mcp add html-mcp -- "$PWD/.venv/bin/html-mcp"
```

The `html-mcp-web` command (project setup) is also in `.venv/bin`; activate the venv or call it by that path.

## Quickstart

```bash
cd examples
# Start Claude Code or Codex here, with the html-mcp server enabled.
```

Tell the agent:

> Open the review page and listen for **Call agent**.

The agent opens [http://localhost:8766](http://localhost:8766) and starts listening. The page has tabs for the neutral slides and report examples. Select some text, press **Comment**, then press **Call agent**; the agent receives the request and handles the comment.

## Set up your own artifact

In the directory that holds your artifact, create one project and pick a layout:

```bash
html-mcp-web init --layout slides --main artifact.html
```

Then tell the agent to open the review page and listen for **Call agent**; the same session starts the review page at the configured port. `init` creates missing source files and writes `.html-mcp-web.yaml`:

```yaml
artifacts:
  slides:
    label: Slides
    layout: slides
    main: artifact.html
watch: ['*.html', '*.css', '*.js', '*.svg', '*.png', '*.jpg', '*.jpeg', '*.gif', '*.webp']
ignore: []
port: 8765
```

`artifacts` maps an id to its label, `layout` (`slides` is 16:9, `report` is A4), and `main` file. Its body contains `main.pages`, with one `section.page` per printed page. Only the directories that hold artifact files are watched, together with the project root for this config; within them `watch` refreshes on save, `ignore` is checked first, and `port` is the local address. Agent sessions that find the same config share one server, comments, and revisions.

An optional top-level `guideline` names
`~/.config/html-mcp-web/guidelines/<name>/GUIDELINE.md`. For example, use
`html-mcp-web init --layout slides --main artifact.html --guideline eda-domain-meeting`,
or add `guideline: eda-domain-meeting` to an existing config. The file must exist.
The agent uses the configured guideline when writing your artifact.

## Use it

Use **Preview**, **Source**, or **Split** to review the rendered artifact and edit its source in one page. A plain artifact opens its main HTML file; a templated artifact opens its smaller content file. Select exact characters in either view and add a comment. Source comments highlight only the selected characters, including selections that wrap visually across lines, and reattach when surrounding source moves. Drag the divider in Split view to resize the panes.

Use **+ Note** for a whole-artifact comment, the **Pages** tab to jump between pages, and the **Edit** link to fix your own message in place. Press **Call agent** when the comments are ready. **Resolve** closes a comment in one click, and **Reference** sets a thread aside to read again: it stays out of the open and resolved lists, still takes replies, and goes back to either with **Reopen** or **Resolve**.

The agent reads the comments, edits the source, and replies to each one; the reviewer resolves
the thread. The review page also flags anything off the page, clipped SVG drawings, and
overlapping labels at the artifact's fixed size, and reports them to the agent so it can fix
them. Comments are stored in `.html-mcp-web/comments/<artifact>.json`, which holds selected
text, so whether to track it in git is a privacy choice.

For a long answer, the agent can ask `read_comments(save=true)` for a Markdown draft of the selected threads under `.html-mcp-web/drafts/`, write its replies into the draft's Reply blocks, and send the file back with `reply_comments(replies_file=...)`; the whole batch is applied together, and a draft made before a thread changed is refused. The draft also holds an Edit block for each of the agent's earlier entries; a changed block rewrites that entry in place (author and time kept, `updated_at` recorded). Inline, `reply_comments(edits_text="c-.../e-...@<updated>: ...")` does the same by comment id, entry id and the thread's `updated` stamp, which `read_comments` reports.

If the agent restarts or stops receiving calls, ask it to listen for **Call agent** again. Calls made while it is disconnected stay queued.

## Templates

A template compiles a small content file into the artifact, so you edit content while the cover, bars, and page numbers stay consistent:

```bash
html-mcp-web init --layout slides --main slides.html --template neutral-slides --content content.html
```

Initialization builds a missing main file; the build then reruns on every content save. Existing source files are preserved. This repo ships [`templates/neutral-slides/`](templates/neutral-slides/) and [`templates/neutral-report/`](templates/neutral-report/); the content format is in [`templates/README.md`](templates/README.md). Your own templates go in `~/.config/html-mcp-web/templates/<name>/` and stay out of this repository.

## Export

The topbar exports each artifact as a file. **PDF** prints every page at the layout's fixed size through headless Firefox. **PPTX** (slides only) builds an editable deck: text stays editable text, tables stay tables, inline SVG stays vector, and math becomes an image. A skin can name TrueType files to embed the deck font; see [`templates/SKINS.md`](templates/SKINS.md).

## Configuration

```bash
html-mcp-web config                                  # print the whole config
html-mcp-web config artifacts.slides.layout report   # change one value
html-mcp-web config port 8766
html-mcp-web config watch '*.html,assets/**'
```

`init` also takes `--port`, `--guideline`, and, for a templated artifact, `--template <name> --content <file>`. Config changes apply on the next save; a port change takes effect when the agent restarts.

## Security

An agent-generated artifact runs JavaScript with the local page's privileges, so html-mcp-web is for trusted local artifacts and binds to `127.0.0.1` only.

## Acknowledgements

MIT licensed; see [`LICENSE`](LICENSE). The source editor uses [Ace](https://ace.c9.io/) under the BSD license; its license is included with the bundled files. Full-screen wheel navigation adapts the intent-detection strategy from [Swiper's Mousewheel module](https://github.com/nolimits4web/swiper/tree/master/src/modules/mousewheel) by Vladimir Kharlampidi and the Swiper contributors, under the MIT license.
