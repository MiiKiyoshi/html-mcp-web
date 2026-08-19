# html-mcp-web

Review an AI agent's HTML slides or report from the rendered page while Claude Code or Codex edits the source.

![The review page: a slide on the left with a highlighted sentence, and the comment thread on the right where a reviewer's question is answered by the agent.](docs/hero.png)

You open the artifact in a local review page, select rendered text, and comment on it. The agent reads the comment over MCP, edits the HTML, and replies in the same thread. Because you point at the rendered page, you never hunt for the source, and saving a file refreshes only the artifact frame, so your scroll position and drafts stay put.

```
you:    select text on the page -> write a comment
                  |
agent:  read comments -> edit HTML -> reply or resolve
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

Ask the agent to call `inspect()`. The review page opens at [http://localhost:8766](http://localhost:8766), with tabs for the neutral slides and report examples. Select some text, press **Comment**, and ask the agent to process the comments.

## Set up your own artifact

In the directory that holds your artifact, create one project and pick a layout:

```bash
html-mcp-web init --layout slides --main artifact.html
```

Then ask the agent to call `inspect()`; the same session starts the review page at the configured port. `init` writes `.html-mcp-web.yaml`:

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

`artifacts` maps an id to its label, `layout` (`slides` is 16:9, `report` is A4), and `main` file, where every `section.page` is one printed page. `watch` refreshes on save, `ignore` is checked first, and `port` is the local address. Agent sessions that find the same config share one server, comments, and revisions.

## Use it

Select text and press **Comment**; the anchor reattaches to the quote after edits. Use **+ Note** for a whole-artifact comment, the **Pages** tab to jump between pages, and the **Edit** link to fix your own message in place. **Resolve** and **Dismiss** close a comment in one click. Then ask the agent:

> Process the open html-mcp-web comments.

The agent reads the comments, edits the source, and replies or resolves each one. The review page also flags anything off the page, clipped SVG drawings, and overlapping labels at the artifact's fixed size, and reports them to the agent so it can fix them. Comments are stored in `.html-mcp-web/comments/<artifact>.json`, which holds selected text, so whether to track it in git is a privacy choice.

## Templates

A template compiles a small content file into the artifact, so you edit content while the cover, bars, and page numbers stay consistent:

```bash
html-mcp-web init --layout slides --main slides.html --template neutral-slides --content content.html
```

The build reruns on every content save. This repo ships [`templates/neutral-slides/`](templates/neutral-slides/) and [`templates/neutral-report/`](templates/neutral-report/); the content format is in [`templates/README.md`](templates/README.md). Your own templates go in `~/.config/html-mcp-web/templates/<name>/` and stay out of this repository.

## Export

The topbar exports each artifact as a file. **PDF** prints every page at the layout's fixed size through headless Firefox. **PPTX** (slides only) builds an editable deck: text stays editable text, tables stay tables, inline SVG stays vector, and math becomes an image. A skin can embed the deck font and supply a PowerPoint template; see [`templates/README.md`](templates/README.md#writing-a-skin).

## Configuration

```bash
html-mcp-web config                                  # print the whole config
html-mcp-web config artifacts.slides.layout report   # change one value
html-mcp-web config port 8766
html-mcp-web config watch '*.html,assets/**'
```

`init` also takes `--port` and, for a templated artifact, `--template <name> --content <file>`. Config changes apply on the next save; a port change takes effect when the agent restarts.

## Security

An agent-generated artifact runs JavaScript with the local page's privileges, so html-mcp-web is for trusted local artifacts and binds to `127.0.0.1` only.

## Acknowledgements

MIT licensed; see [`LICENSE`](LICENSE). Full-screen wheel navigation adapts the intent-detection strategy from [Swiper's Mousewheel module](https://github.com/nolimits4web/swiper/tree/master/src/modules/mousewheel) by Vladimir Kharlampidi and the Swiper contributors, under the MIT license.
