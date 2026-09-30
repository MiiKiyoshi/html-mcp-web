# Set up a folder for html review

The user said "do html init", or `listen` found no config. Set up review for the current MCP
session. Use the MCP process's startup directory, reported in its instructions, as the setup
directory. The config belongs there. A subfolder requested for the document belongs in main
and content, which are resolved relative to the config's directory. Inspect first and confirm
any choices the user has not already authorized. Setup is complete only when the current MCP
connection resolves the intended document.

These steps set up the current MCP session. If the user explicitly requests setup for another
session, use that session's intended startup directory and report its verification status
separately.

## 1. Inspect (write nothing)

- Find the nearest `.html-mcp-web.yaml` at or above the setup directory. Check its path,
  configured artifacts, and port against the user's request. A missing main file alone does
  not mean the config belongs to another project.
  If the config belongs to the requested project, reuse it or make only the authorized
  changes. If it is in a parent directory and belongs to a different project, propose a
  config in the setup directory that takes precedence for this session without changing the
  parent config. If a config already exists in the setup directory, do not run init over it.
  Resolve any requested changes to that config first.
- HTML files already in the setup directory or the subfolder the user named: `ls *.html *.htm`.
- Port: the first free one from 8765 (`ss -ltn`, or `lsof -iTCP -sTCP:LISTEN -P -n` on macOS), also skipping the port in a
  `.tex-mcp-web.yaml` in this folder, since both tools default to 8765.
- Templates: directory names holding `build.py` in `templates/` two levels above this file
  and in `~/.config/html-mcp-web/templates/`.
- Guidelines: directory names holding `GUIDELINE.md` in `guidelines/` two levels above this
  file and in `~/.config/html-mcp-web/guidelines/`. A name in both means the user's copy.

## 2. Confirm

Show one summary, in the user's language, like:

    config    : <startup directory>/.html-mcp-web.yaml
    layout    : slides  (slides = 16:9 / report = A4)
    main      : talk2/html/slides.html  (built from content, created if missing)
    content   : talk2/html/content.html
    template  : neutral-slides  (available: neutral-slides, neutral-report, ...)
    guideline : neutral  (available: neutral, ...)
    port      : 8766  (8765 is in use)
    watch     : *.html *.css *.js *.svg *.png *.jpg *.jpeg *.gif *.webp -> 3 files here

The defaults are slides with the neutral-slides template and the neutral guideline. For a
report they are the neutral-report template and no guideline, since neutral is written for
slides. With a template, main is the built file and content (default `content.html`) is the
file the user edits. Ask once. A user who asks for the defaults gets them as shown, and
otherwise change only what the user corrects. A path choice the user has already approved is
not asked again.

## 3. Write

Run the command named in the error that sent you here, with the MCP startup directory as its
working directory. Keep the document's subfolder in `--main` and `--content` instead of
running init from that subfolder. Changing the shell's working directory does not change the
MCP process's startup directory.

    html-mcp-web init --layout <slides|report> --main <file> --port <port> \
      [--template <name> --content <file>] [--guideline <name>]

For example, `--main talk2/html/slides.html --content talk2/html/content.html`.

## 4. Verify

Run `html-mcp-web config` from the MCP startup directory and confirm the selected config path
and values. Resolve main and content relative to that config's directory and confirm that they
point to the intended files and that those files exist.

Then call `guide` for the intended artifact through the current MCP connection and confirm that
`edit_file` resolves to the intended content file, or main when no template is used. A
successful init command or CLI config check alone does not establish this.

If this MCP process already connected successfully using a different config, restart the MCP
server process through the client and repeat the guide check. A tool call that found no config
or failed before binding does not by itself require a restart.

## 5. Tell the user

Report setup as ready only after the current MCP connection passes the guide check. If
restarting the MCP process remains necessary, say that the files are prepared but this session
is not ready yet, and state the remaining action. Saying "do html listen" starts the review
page. Start listening only when the user asks for it.
