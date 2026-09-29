# Set up a folder for html review

The user said "do html init", or `listen` found no config. Setting up writes
`.html-mcp-web.yaml` in the folder this agent session started in, and creates the main HTML
file when it is missing. Inspect first, show one summary, write only after the user agrees.

## 1. Inspect (write nothing)

- A config here or in a parent folder (`.html-mcp-web.yaml`): if one exists, show the user
  its values and stop. A change is an edit to that file, after the user agrees.
- HTML files already here: `ls *.html *.htm`.
- Port: the first free one from 8765 (`ss -ltn`, or `lsof -iTCP -sTCP:LISTEN -P -n` on macOS), also skipping the port in a
  `.tex-mcp-web.yaml` in this folder, since both tools default to 8765.
- Templates: directory names holding `build.py` in `templates/` two levels above this file
  and in `~/.config/html-mcp-web/templates/`.
- Guidelines: directory names holding `GUIDELINE.md` in `guidelines/` two levels above this
  file and in `~/.config/html-mcp-web/guidelines/`. A name in both means the user's copy.

## 2. Confirm

Show one summary, in the user's language, like:

    layout    : slides  (slides = 16:9 / report = A4)
    main      : slides.html  (built from content.html, created if missing)
    template  : neutral-slides  (available: neutral-slides, neutral-report, ...)
    guideline : neutral  (available: neutral, ...)
    port      : 8766  (8765 is in use)
    watch     : *.html *.css *.js *.svg *.png *.jpg *.jpeg *.gif *.webp -> 3 files here

The defaults are slides with the neutral-slides template and the neutral guideline. For a
report they are the neutral-report template and no guideline, since neutral is written for
slides. With a template, main is the built file and content (default `content.html`) is the
file the user edits. Ask once. A user who asks for the defaults gets them as shown, and
otherwise change only what the user corrects.

## 3. Write

In the session's folder, with the command named in the error that sent you here:

    html-mcp-web init --layout <slides|report> --main <file> --port <port> \
      [--template <name> --content <file>] [--guideline <name>]

## 4. Tell the user

The folder is set up. Saying "do html listen" starts the review page.
