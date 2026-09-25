<img src="docs/logo.png" alt="" width="96">

# html-mcp-web

Review an AI agent's HTML slides or report from the rendered page, on a desktop, tablet, or phone, while Claude Code or Codex edits the source. Hand the finished slides over as an editable PowerPoint deck.

**[Slides example](examples/neutral-slides/)**

![A phrase highlighted on a rendered slide, the reviewer's question, and the agent's proposed rewrite of the sentence with Apply suggestion.](docs/hero.png)

**[Report example](examples/neutral-report/)**

![A sentence highlighted on a rendered report page, and the reviewer's question with the agent's answer beside it.](docs/report.png)

You comment on the rendered page itself: select the words you mean, the way you would mark
a printout, and say what should change. The agent reads the comments, edits the HTML, and
replies in the same thread, or proposes the exact change and leaves it to you to apply with
one click. Saving a file refreshes only the artifact frame, so
your scroll position and drafts stay put.

```
you:    select text -> write a comment -> press Call agent
                  |
agent:  read comments -> edit HTML, or propose a change -> reply
                  |
you:    read the refreshed page -> comment again
```

## Install

Paste this into Claude Code or Codex:

```
Install html-mcp-web by following https://raw.githubusercontent.com/MiiKiyoshi/html-mcp-web/main/INSTALL.md
```

The agent checks for Python and Firefox, shows you what it will install, and registers
html-mcp-web for every folder once you agree. Start the agent again afterwards.

## Init

Once per folder, start the agent in the folder that holds (or will hold) your artifact and say:

```
do html init
```

The agent asks whether it is slides (16:9) or a report (A4), proposes the file, a template,
and a free port, and writes `.html-mcp-web.yaml` once you agree.

## Listen

To review, say:

```
do html listen
```

Open `http://localhost:<port>` with the port you chose at init. Say it again after the
agent restarts. Presses of **Call agent** made meanwhile wait for it.

## Suggested edits

When the wording is yours to decide, the agent proposes it instead of making it. The thread
shows the source it would change as a −/+ pair, the Source view marks the same text in red,
and **Apply suggestion** writes the change the way saving does, so a templated slide
rebuilds at once. Proposing again replaces the proposal, and nothing reaches the source
until you apply it. If the change rewrites the words you selected, your comment moves to
what replaced them.

## Export to PowerPoint and PDF

Slides reviewed here leave as a PowerPoint deck you can keep editing: press **PPTX** in the
topbar. Text stays editable text, tables stay tables, inline SVG drawings stay vector, math
becomes an image, and the script under each slide becomes its speaker notes. A skin can
name TrueType files to embed the deck font, as [`templates/SKINS.md`](templates/SKINS.md) explains.
**PDF** prints every page, slides or report, at the layout's fixed size. Both run through
headless Firefox.

## On a tablet or phone

The review page adapts to the screen: held upright, the comments dock below the artifact
and the bar between them drags with a finger. On a phone the comments start closed so the
slide has the screen, and **⇥** opens them. Pinch to zoom into the slide, and **Fit**
brings it back. On a touch screen the button that comments on selected text sits clear of
your finger.

![The review page on a tablet and a phone, zoomed into a slide: the commented phrase above, its thread below.](docs/mobile.png)

The server listens on `127.0.0.1` only, so reach it from another device through a
forwarded port: an SSH tunnel, VS Code port forwarding, or `tailscale serve`.

## Reviewing

- Select text on the rendered page and press the **Comment** button that appears beside it.
  This is the usual way to review: you point at what you see, and the agent finds the
  source behind it.
- **Source** and **Split** show the source as well, for when you want to point at the
  markup itself. A comment made there covers exactly the selected characters and follows
  them when the surrounding source moves. Drag the divider to resize. A templated artifact
  shows its smaller content file.
- **+ Note** comments on the whole artifact, the **Pages** tab jumps between pages, and
  **Edit** fixes your own message.
- Press **Call agent** when your comments are ready.
- Resolving is yours: **Resolve** closes a thread. **Reference** sets one aside to read again,
  and it still takes replies and returns with **Reopen** or **Resolve**.
- The page flags content off the page, clipped SVG drawings, and overlapping labels, and
  reports them to the agent.

Comments are stored in `.html-mcp-web/comments/<artifact>.json` and hold the text you
selected, so whether to track them in git is a privacy choice.

## Templates

A template builds the artifact from a small content file, so you edit content while the
cover, bars, and page numbers stay consistent. Pick one at init. This repo ships
[`templates/neutral-slides/`](templates/neutral-slides/) and
[`templates/neutral-report/`](templates/neutral-report/), and the content format is in
[`templates/README.md`](templates/README.md). Your own templates go in
`~/.config/html-mcp-web/templates/<name>/`, and a writing guideline the agent follows in
`~/.config/html-mcp-web/guidelines/<name>/GUIDELINE.md`.

## Configuration

`.html-mcp-web.yaml` sits in the project folder. Ask the agent to change a field, or edit it.

| Field | Effect |
|---|---|
| `artifacts.<id>.layout` | `slides` (16:9) or `report` (A4). |
| `artifacts.<id>.main` | The HTML file the page shows, with one `section.page` per printed page inside `main.pages`. |
| `artifacts.<id>.template`, `.content` | A template name and the content file it builds `main` from. |
| `guideline` | A guideline name under `~/.config/html-mcp-web/guidelines/`. |
| `watch`, `ignore` | Files whose saves refresh the page. `ignore` is checked first. |
| `port` | This folder's review page port. |

## Security

An agent-generated artifact runs JavaScript with the local page's privileges, so html-mcp-web is for trusted local artifacts and binds to `127.0.0.1` only.

## Acknowledgements

MIT licensed. See [`LICENSE`](LICENSE). The source editor uses [Ace](https://ace.c9.io/) under the BSD license, and its license is included with the bundled files. Full-screen wheel navigation adapts the intent-detection strategy from [Swiper's Mousewheel module](https://github.com/nolimits4web/swiper/tree/master/src/modules/mousewheel) by Vladimir Kharlampidi and the Swiper contributors, under the MIT license.
