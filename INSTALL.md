# Installing html-mcp-web

This file is for the agent the user asked to install html-mcp-web. Fetch it with
`curl -fsSL`, since a summarizing fetch drops the commands. Inspect first, show one summary,
install after the user agrees. On a machine that already has it, the same steps update it.

## 1. Inspect (change nothing)

- Python 3.10 or newer (the `mcp` package has no release for older ones): `python3 --version`.
  When older, `command -v python3.13 python3.12 python3.11 python3.10`. None: stop and tell
  the user. Use the one found as `python3` below.
- Firefox: `command -v firefox`, and record its directory. Missing is not a stop: say that PDF
  and PPTX export, and layout checks while no review page is open, need it. Do not install it.
- Install directory: `$HOME/.local/share/html-mcp-web`, unless the user named another.
  Note whether it already holds a checkout. The checkout stays: its templates and guidelines are read from it.
- Agents: `command -v claude` and `command -v codex`. Register with each one found.
- Existing registration: `claude mcp get html-mcp`, `codex mcp get html-mcp`. Note a
  command path that differs from the one below.

## 2. Confirm

Show one summary, in the user's language: install directory (new or update), Python,
Firefox, the agents to register with, and any existing registration that will be replaced.
Registration is user-level, available in every folder. Do not ask about scope. Ask once.

## 3. Install

    DIR="$HOME/.local/share/html-mcp-web"
    git clone https://github.com/MiiKiyoshi/html-mcp-web.git "$DIR"   # update: git -C "$DIR" pull --ff-only
    python3 -m venv "$DIR/.venv"
    "$DIR/.venv/bin/pip" install -q -U pip                              # editable installs need a recent pip
    "$DIR/.venv/bin/pip" install -e "${DIR}[mcp]"
    "$DIR/.venv/bin/html-mcp-web" mcp --check                          # lists the tools

## 4. Register

Remove a registration the user agreed to replace (`claude mcp remove --scope user html-mcp`,
`codex mcp remove html-mcp`), then:

    BIN="$DIR/.venv/bin"
    P="$BIN:<firefox directory, if found>:/usr/bin:/bin"
    claude mcp add --scope user html-mcp -e PATH="$P" -- "$BIN/html-mcp"
    codex mcp add html-mcp --env PATH="$P" -- "$BIN/html-mcp"

## 5. Tell the user

Tell the user in their language what is included and how to start. Keep it to the following
information:

- `neutral-slides`: plain 16:9 slides without organization marks. The default template for slides.
- `neutral-report`: an A4 report with a cover and one page per section. The default template for reports.
- `neutral`: writing rules the agent follows for slides. Selected by default for slides. Reports
  use no guideline by default.

They can add their own templates and guidelines, which will also appear among the choices at
setup.

Ask them to restart the agent in the folder where they want to work, then say "do html init"
once per folder. At setup, they just choose from the available templates and guidelines. They
can accept the slide defaults or name a change, such as a report. After setup, say "do html
listen" to start reviewing. The agent gives them the review page address and gets ready to
handle their comments when they press **Call agent**. They open that address in their browser.
