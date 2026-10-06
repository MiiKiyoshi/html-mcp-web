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
  running MCP uses, as reported by `setup_info()`. Inspect each directory's absolute path and
  entries, including empty or missing directories, without showing this inventory to the user.
  For duplicate names, identify the effective user override. Mark entries whose required
  build.py or GUIDELINE.md is missing rather than silently falling back to the installed copy.

## 2. Confirm

Show one short choice list in the user's language, using the available choices found in
section 1. Explain each choice in one line and mark the defaults. For the included choices, use
this form:

    Layout    : slides, 16:9 (default), or report, A4
    Template  : neutral-slides, plain slides without organization marks (slide default)
                neutral-report, a cover and one page per section (report default)
    Guideline : neutral, writing rules the agent follows for slides (slide default)
                none, no writing guideline (report default)
    File      : slides.html (to be created)

Adapt the selected choices and filename to the user's request and existing files. Show whether
the document file will be created or reused. Include available user templates and guidelines
beside the included choices, without grouping them by directory. If a user copy replaces an
included choice of the same name, say only "uses your version" beside it.

Tell the user they can accept the defaults or name what to change. Ask only about choices they
have not already authorized. Apply explicit choices or a request for defaults without asking
again. Do not treat silence as agreement.

Keep configuration paths, source directories, content and build details, ports, and watch
patterns out of the summary. Show a file location only when needed to distinguish the user's
choices. Handle an occupied port by selecting a free one as in section 1, without asking the
user.

If a documented default is missing or unusable, check the installation, lookup paths, and
overrides before presenting the list as complete or writing the configuration. If a problem
remains, explain which choice is unavailable and what decision is needed, without showing
internal details unless that decision requires them. Do not present the remaining entries as
the complete set of choices.

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
