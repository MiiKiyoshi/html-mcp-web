# Set up a folder for html review

The user said "do html init", or `listen` found no config. Setting up writes
`.html-mcp-web.yaml` in the folder this agent session started in, and creates the main HTML
file when it is missing. Inspect first, show one summary, write only after the user agrees.

## 1. Inspect (write nothing)

- A config here or in a parent folder (`.html-mcp-web.yaml`): if one exists, show the user
  its values and stop. A change is an edit to that file, after the user agrees.
- HTML files already here: `ls *.html *.htm`.
- Port: the first free one from 8765 (`ss -ltn`), also skipping the port in a
  `.tex-mcp-web.yaml` in this folder; both tools default to 8765.
- Templates: directory names holding `build.py` in `templates/` two levels above this file
  and in `~/.config/html-mcp-web/templates/`.
- Guidelines: directory names in `~/.config/html-mcp-web/guidelines/`.

## 2. Confirm

Show one summary, in the user's language, like:

    layout    : ?  (slides = 16:9 / report = A4)   <- the only field without a default
    main      : artifact.html  (created if missing)
    template  : none  (available: neutral-slides, neutral-report, ...)
    guideline : none  (available: ...)
    port      : 8766  (8765 is in use)
    watch     : *.html *.css *.js *.svg *.png *.jpg *.jpeg *.gif *.webp -> 3 files here

Ask for layout unless the user already named it. With a template, main is the built file
and content (default `content.html`) is the file the user edits. Ask once; change only what
the user corrects.

## 3. Write

In the session's folder, with the command `inspect()` names as `setup_required.cli`:

    html-mcp-web init --layout <slides|report> --main <file> --port <port> \
      [--template <name> --content <file>] [--guideline <name>]

## 4. Tell the user

The folder is set up; saying "do html listen" starts the review page.
