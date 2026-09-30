# Set up a folder for html review

The user said "do html init", or `listen` found no config. Set up review for the current MCP
session. Read setup paths from `setup_info()`, not from the shell's current directory. Its
startup directory is the setup directory, and the config belongs there. Configuration
discovery searches the MCP startup directory and its parents, never its subfolders. The
discovered config and an existing binding may differ. A successful binding is retained until
the MCP process is restarted.

A subfolder requested for the document belongs in main and content, which are resolved
relative to the config's directory. Inspect first and confirm any choices the user has not
already authorized. Setup is complete only when the current MCP connection resolves the
intended document.

These steps set up the current MCP session. If the user explicitly requests setup for another
session, use that session's intended startup directory and report its verification status
separately.

## 1. Inspect (write nothing)

- Call `setup_info()` before connecting or writing. Inspect the startup directory, discovered
  config, and any existing binding. For the current session, use the startup directory as the
  setup directory. Keep a document's subfolder in its configured paths rather than moving the
  config there.
- Check the discovered config's path, configured artifacts, and port against the user's
  request. A missing main file alone does not mean the config belongs to another project.
  If the config belongs to the requested project, reuse it or make only the authorized
  changes. If it is in a parent directory and belongs to a different project, propose a
  config in the setup directory that takes precedence for this session without changing the
  parent config. If a config already exists in the setup directory, do not run init over it.
  Resolve any requested changes to that config first.
- HTML files already in the setup directory or the subfolder the user named: `ls *.html *.htm`.
- Port: the first free one from 8765 (`ss -ltn`, or `lsof -iTCP -sTCP:LISTEN -P -n` on macOS), also skipping the port in a
  `.tex-mcp-web.yaml` in this folder, since both tools default to 8765.
- List templates and guidelines from the same installation and user directories that the
  running MCP uses, which `setup_info()` reports. Show each source directory's absolute path
  and its entries separately, including empty or missing directories. For duplicate names,
  identify the effective user override. Mark entries whose required build.py or GUIDELINE.md
  is missing rather than silently falling back to the built-in copy.

## 2. Confirm

Show one summary, in the user's language, like:

    config    : <startup directory>/.html-mcp-web.yaml
    layout    : slides  (slides = 16:9 / report = A4)
    main      : talk2/html/slides.html  (built from content, created if missing)
    content   : talk2/html/content.html
    template  : not selected  (recommended: neutral-slides)
                built-in  <absolute dir>: neutral-report, neutral-slides
                user      <absolute dir>: house
    guideline : not selected  (recommended: neutral)
                built-in  <absolute dir>: neutral
                user      <absolute dir>: team-meeting
    port      : 8766  (8765 is in use)
    watch     : *.html *.css *.js *.svg *.png *.jpg *.jpeg *.gif *.webp -> 3 files here

The defaults are slides with the neutral-slides template and the neutral guideline. For a
report they are the neutral-report template and no guideline, since neutral is written for
slides. With a template, main is the built file and content (default `content.html`) is the
file the user edits.

Show the template and guideline choices grouped by source directory, including each
directory's absolute path and which copy is used for duplicate names. Mark documented defaults
as recommendations. Ask only for choices the user has not already made, including no guideline
as an option. Apply an explicit choice or request for defaults without asking again. Do not
treat silence as agreement. A path choice the user has already approved is not asked again.

If a documented default is missing or unusable, check the installation, lookup paths, and
overrides before presenting the list as complete or writing the configuration. Report any
unresolved problem rather than claiming that the remaining entries are the only choices.

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
