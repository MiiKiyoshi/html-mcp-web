# Set up a folder for html review

The user said "do html init", or `listen` found no config. Set up review for the current MCP
session. Read setup paths from `setup_info()`, not from the shell's current directory. Its
startup directory is the setup directory, and the config belongs there. Configuration
discovery searches the MCP startup directory and its parents, never its subfolders. The
discovered config and an existing binding may differ. A successful binding is retained until
the MCP process is restarted.

A subfolder requested for the document belongs in main and content, which are resolved
relative to the config's directory and name files in it or its subfolders. A document outside
the startup directory is served by a config in a folder that holds both, found from the
startup directory as its parent. A project's artifacts are gathered in one folder the user
chooses, `artifacts/` by default, and each has a folder of its own in it named after the
artifact, `artifacts/<name>/`, holding its main, its content and its floorplan. Two artifacts
never keep their main or content in one folder: the configuration stops on it. Inspect first,
then ask the user every choice in section 2 before writing anything. Setup is complete only
when the current MCP connection resolves the intended document.

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
- Port to recommend: the first free one from 8765 (`ss -ltn`, or `lsof -iTCP -sTCP:LISTEN -P -n` on macOS), also skipping the port in a
  `.tex-mcp-web.yaml` in this folder, since both tools default to 8765.
- List templates and guidelines from the same installation and user directories that the
  running MCP uses, as reported by `setup_info()`. Inspect each directory's absolute path and
  entries, including empty or missing directories, without showing this inventory to the user.
  For duplicate names, identify the effective user override. Mark entries whose required
  build.py or GUIDELINE.md is missing rather than silently falling back to the installed copy.

## 2. Confirm

Six choices are the user's to make: the artifact's name, the folder the project's artifacts
are gathered in, the layout, the template, the guideline and the page's port. Write nothing
until the user has answered every one of them. A request to set up, such as "do html init" or
"do it yourself", answers none of them. A choice the user has named, in this request or
earlier, or "use the defaults", settles what it covers, and a settled choice is not asked
again.

Recommend a value for each: a short name for the artifact taken from the user's request,
`artifacts/` for the folder, the layout the request implies, that layout's default template
and guideline, and the free port found in section 1. The artifact's own folder is then
`<folder>/<name>/`.

When your client has a tool that lets the user pick among options, ask every choice with it,
the recommended value first, in as few calls as the tool allows. Where there are more entries
than the tool takes, offer the recommended one and the user's own first, and name the rest in
the question. Ask the name, the folder and the port with it only when the tool also takes an
answer the user types; otherwise ask them in plain chat with their recommended values.
Without such a tool, show every choice in one short list in the user's language and wait for
the answer:

    Name      : talk  (the page's tab and the tools call the artifact by it)
    Folder    : artifacts/  (the project's artifacts, each in a folder named after it: artifacts/talk/)
    Layout    : slides, 16:9 (default), or report, A4
    Template  : neutral-slides, plain slides without organization marks (slide default)
                neutral-report, a two-column paper (report default)
    Guideline : neutral-slides, writing rules the agent follows for slides (slide default)
                neutral-report, writing rules the agent follows for a paper (report default)
    Port      : 8765  (the page opens at http://localhost:8765)
    File      : artifacts/talk/slides.html (to be created)

Show whether the document file will be created or reused. Include available user templates
and guidelines beside the included choices, without grouping them by directory. If a user copy
replaces an included choice of the same name, say only "uses your version" beside it. Keep the
config path, content and build details and watch patterns out of the choices. A port the user
names must be free: if it is taken, say so and recommend the first free one.

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

    html-mcp-web init --name <name> --layout <slides|report> --main <file> --port <port> \
      [--template <name> --content <file>] [--guideline <name>]

For example, `--name talk --main artifacts/talk/slides.html --content artifacts/talk/content.html`.

## 4. Verify

Run `html-mcp-web config` from the MCP startup directory and confirm the selected config path
and values. Resolve main and content relative to that config's directory and confirm that they
point to the intended files and that those files exist.

Then call `guide()` for the intended artifact through the current MCP connection and confirm that
`edit_file` in its answer names the intended content file, or main when no template is used. A
successful init command or CLI config check alone does not establish this.

If this MCP process already connected successfully using a different config, restart the MCP
server process through the client and repeat the guide check. A tool call that found no config
or failed before binding does not by itself require a restart.

## 5. Tell the user

Report setup as ready only after the current MCP connection passes the guide check. If
restarting the MCP process remains necessary, say that the files are prepared but this session
is not ready yet, and state the remaining action. Saying "do html listen" starts the review
page. With the plugin, Claude Code started in the folder later listens on its own. Start
listening only when the user asks for it.
