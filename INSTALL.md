# Installing html-mcp-web

This file is for the agent the user asked to install html-mcp-web. Fetch it with
`curl -fsSL`, since a summarizing fetch drops the commands. Inspect first, show one summary,
install after the user agrees. On a machine that already has it, the same steps update it.

## 1. Inspect (change nothing)

- Python 3.10 or newer (the `mcp` package has no release for older ones): `python3 --version`.
  When older, `command -v python3.13 python3.12 python3.11 python3.10`. None: stop and tell
  the user. Use the one found as `python3` below.
- Firefox: `command -v firefox`, and on macOS also `/Applications/Firefox.app/Contents/MacOS/firefox`.
  Record its directory. Missing: offer to install it.
- Install directory: `$HOME/.local/share/html-mcp-web`, unless the user named another.
  Note whether it already holds a checkout. The checkout stays: its templates and guidelines are read from it.
- Agents: `command -v claude` and `command -v codex`. Register with each one found.
- Existing registration: `claude mcp get html-mcp`, `codex mcp get html-mcp`. Note a
  command path that differs from the one below. `claude plugin list` shows whether the
  `html-mcp` plugin is already installed, in which case its install below is skipped.

## 2. Confirm

Show one summary, in the user's language: install directory (new or update), Python,
Firefox (found, or offered), the agents to register with, and any existing registration that
will be replaced.
Registration is user-level, available in every folder. Do not ask about scope. Ask once.

When Firefox is offered, give both outcomes so the user can choose:

- Install: `layout()` and `image()`, with which the agent checks the pages it edits, PDF
  and PPTX export, and building a report, whose pages are set in Firefox, work. Firefox is installed for the whole system, which needs administrator
  rights, and on Debian or Ubuntu Mozilla's package repository is added to the system's sources.
- Decline: the review page, comments, editing and building a deck work. `layout()`,
  `image()`, PDF and PPTX export and building a report do not, since all of them render the
  pages in a headless Firefox, until it is installed.

## 3. Install

    DIR="$HOME/.local/share/html-mcp-web"
    git clone https://github.com/MiiKiyoshi/html-mcp-web.git "$DIR"   # update: git -C "$DIR" pull --ff-only
    python3 -m venv "$DIR/.venv"
    "$DIR/.venv/bin/pip" install -q -U pip                              # editable installs need a recent pip
    "$DIR/.venv/bin/pip" install -e "${DIR}[mcp]"
    "$DIR/.venv/bin/html-mcp-web" mcp --check                          # lists the tools

Firefox, when the user chose to install it:

- macOS: `brew install --cask firefox`. Its directory is `/Applications/Firefox.app/Contents/MacOS`.
- Debian or Ubuntu: from Mozilla's APT repository, since Ubuntu's own package installs a snap,
  which containers and some systems cannot run. As root, or with sudo before each command:

      install -d -m 0755 /etc/apt/keyrings
      curl -fsSL https://packages.mozilla.org/apt/repo-signing-key.gpg -o /etc/apt/keyrings/packages.mozilla.org.asc
      echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" > /etc/apt/sources.list.d/mozilla.list
      printf 'Package: *\nPin: origin packages.mozilla.org\nPin-Priority: 1000\n' > /etc/apt/preferences.d/mozilla
      apt-get update && apt-get install -y firefox

- Elsewhere: the system's own firefox package.

Then `firefox --version` (on macOS, the full path above) confirms it, and its directory goes into
the PATH below.

## 4. Register

Remove a registration the user agreed to replace (`claude mcp remove --scope user html-mcp`,
`codex mcp remove html-mcp`), then:

    BIN="$DIR/.venv/bin"
    P="$BIN:<firefox directory, if any>:/usr/bin:/bin"
    claude mcp add --scope user html-mcp -e PATH="$P" -- "$BIN/html-mcp"
    codex mcp add html-mcp --env PATH="$P" -- "$BIN/html-mcp"

For Claude Code, also install the plugin from the checkout. It refuses html-mcp's tools other
than `guide()` and `setup_info()` until that context has read the files `guide()` lists, again
after each compaction. It loads from the checkout in place, so an update of the checkout
updates it.

    claude plugin marketplace add "$DIR"
    claude plugin install html-mcp@html-mcp-web

## 5. Tell the user

Tell the user in their language what is included and how to start. Keep it to the following
information:

- `neutral-slides`: plain 16:9 slides without organization marks. The default template for slides.
- `neutral-report`: a two-column paper on A4. The default template for reports.
- `neutral-slides` and `neutral-report` guidelines: writing rules the agent follows for slides
  and for a paper. Selected by default for each layout.

They can add their own templates and guidelines, which will also appear among the choices at
setup.

Ask them to restart the agent in the folder where they want to work, then say "do html init"
once per folder. At setup, they just choose from the available templates and guidelines. They
can accept the slide defaults or name a change, such as a report. After setup, say "do html
listen" to start reviewing. The agent gives them the review page address and gets ready to
handle their comments when they press **Call agent**. They open that address in their browser.
