#!/usr/bin/env python3
"""Claude Code hooks that keep an agent from working on a deck through html-mcp, or from editing
an artifact's files, before it has read the rules in the context it is working in.

guide() names, for one artifact, its edit file and the files to read in full: the templates'
README and PRODUCTION, the README of the artifact's template, and the guideline the artifact
follows with those it extends. Every html-mcp tool but guide(), setup_info() and image() is
refused while guide() has not answered in this context or a listed file has not been read in
full. Review work runs through these tools (listen, read_comments, write_comments, layout),
while image() only draws a page, which looking at needs no rules. A change with Edit, Write,
MultiEdit or NotebookEdit to an artifact's main or content file waits until guide() has
answered for that artifact in this context and the files it listed for it are read: the server
makes that list, so the hook keeps each artifact's from guide()'s answers. A change made by a
script in a shell is not seen. guide_record.py beside this file keeps what each context read,
says when a Read counts, and starts again with the context.

  session-start  SessionStart: clear the record, and in a project say what to do.
  guide-read     PostToolUse on guide(): record the files its answer lists to read, for the
                 project's tools and for edits to the artifact it answered for.
  file-read      PostToolUse on Read: take a file read whole off the record.
  before-tool    PreToolUse on html-mcp's tools: refuse one other than guide(), setup_info() and
                 image() while this context has not read the rules.
  before-edit    PreToolUse on Edit, Write, MultiEdit and NotebookEdit: refuse a change to an
                 artifact's main or content file while guide() has not answered for that
                 artifact in this context or a file it listed has not been read in full.

A project is a folder holding .html-mcp-web.yaml, found from the file or folder upward. The
script reads the artifacts from it, and needs only the standard library, since it runs outside
the server's environment.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guide_record import EDIT, UNREAD, Gate  # noqa: E402

CONFIG = ".html-mcp-web.yaml"
REMINDER = ("html-mcp: before using html-mcp tools in this context, call guide() and read every "
            "file in its read list in full. Use Read without offset or limit. html-mcp tools other "
            "than guide(), setup_info() and image() are blocked until guide() and the required Read calls "
            "are recorded. A [review] notification from the html-mcp monitor is the user pressing "
            "Call agent on the review page: it is the user's request to handle the review now, so "
            "handle it without asking first.")
NO_GUIDE = ("guide() has not succeeded in this context. Call it for the artifact you will work on, "
            "or for any of the project's artifacts when that is not known yet, then use Read "
            "without offset or limit for every file in its read list. Read each file in full "
            "before retrying this call.")
# The tools that come before the rules: guide() names them, and setup_info() serves setting
# a project up, before there is a guide() to call. image() only draws a page, so a context
# that looks at the deck without working on it need not read the rules.
GATE = Gate("html-mcp-web", CONFIG, REMINDER, NO_GUIDE, open_tools=("guide", "setup_info", "image"))
NO_GUIDE_EDIT = ("guide() has not answered for the artifact {alias!r} in this context. Call "
                 "guide(artifact={alias!r}), then use Read without offset or limit for every file in "
                 "its read list. Read each file in full before retrying this edit.")


def _key_and_rest(text: str) -> tuple[str, str]:
    """A `key: value` line or item split at its colon, a quoted key kept whole."""
    if text[:1] in "'\"" and (end := text.find(text[0], 1)) > 0:
        return text[1:end], text[end + 1:].lstrip()[1:].strip()
    key, _, rest = text.partition(":")
    return key.strip(), rest.strip()


def _scalar(text: str) -> str:
    text = text.strip()
    return text[1:-1] if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"" else text


def _flow(text: str, at: int = 0) -> tuple[dict[str, object], int]:
    """The flow mapping that opens at *text*[*at*], as {layout: slides, main: talk.html}, with
    the flow mappings in it, and where it ends."""
    found: dict[str, object] = {}
    at += 1
    while at < len(text):
        while at < len(text) and text[at] in " ,":
            at += 1
        if at >= len(text) or text[at] == "}":
            return found, at + 1
        if text[at] in "'\"":
            end = text.index(text[at], at + 1)
            key, at = text[at + 1:end], text.index(":", end) + 1
        else:
            end = text.index(":", at)
            key, at = text[at:end].strip(), end + 1
        while text[at] == " ":
            at += 1
        if text[at] == "{":
            found[key], at = _flow(text, at)
        elif text[at] in "'\"":
            end = text.index(text[at], at + 1)
            found[key], at = text[at + 1:end], end + 1
        else:
            end = min((text.find(stop, at) for stop in ",}" if text.find(stop, at) >= 0), default=len(text))
            found[key], at = text[at:end].strip(), end
    return found, at


def artifacts(project: Path) -> dict[str, dict[str, object]]:
    """The artifacts the project's configuration names, each alias with its keys, read with the
    standard library: artifacts: as a block mapping of aliases, each alias's keys a block or a
    flow mapping, or as one flow mapping."""
    lines = []
    for line in (project / CONFIG).read_text(encoding="utf-8").splitlines():
        text = line.split(" #", 1)[0].rstrip()
        if text.strip() and not text.lstrip().startswith("#"):
            lines.append((len(text) - len(text.lstrip()), text.strip()))
    found: dict[str, dict[str, object]] = {}
    for at, (indent, text) in enumerate(lines):
        if indent == 0 and _key_and_rest(text)[0] == "artifacts":
            break
    else:
        return found
    rest = _key_and_rest(text)[1]
    if rest.startswith("{"):
        return {alias: keys for alias, keys in _flow(rest)[0].items() if isinstance(keys, dict)}
    alias, level = None, None
    for indent, text in lines[at + 1:]:
        if indent == 0:
            break
        key, rest = _key_and_rest(text)
        if level is None or indent <= level:
            level, alias = indent, key
            found[alias] = _flow(rest)[0] if rest.startswith("{") else {}
        else:
            found[alias][key] = _scalar(rest)
    return found


def artifact_files(project: Path) -> dict[str, tuple[str, str | None]]:
    """Each artifact's main file and its content file, or None, as real paths."""
    files = {}
    for alias, keys in artifacts(project).items():
        main, content = keys.get("main"), keys.get("content")
        if isinstance(main, str) and main:
            files[alias] = (os.path.realpath(project / main),
                            os.path.realpath(project / content) if isinstance(content, str) and content else None)
    return files


def guide_read(event: dict) -> None:
    text = GATE.response_text(event)
    try:
        answer = json.loads(text)
    except ValueError:
        answer = None
    if isinstance(answer, dict) and "edit_file" in answer:
        edit_file, to_read = answer["edit_file"], answer["read"]
        if "consult" not in answer:
            # A server started before the answer listed the reference apart put it in the
            # reading list, though it is consulted by section.
            to_read = [path for path in to_read if Path(path).name != "COMPONENTS.md"]
    else:
        # A server between the two forms answered with the documents themselves, already in
        # the context. Anything else names no file and records nothing.
        found = re.search(r"^Edit file: (.+)$", text, flags=re.MULTILINE)
        if found is None:
            return
        edit_file, to_read = found.group(1), []
    project = GATE.project_of(Path(edit_file).parent)
    if project is None:
        return
    # The project's tools take what guide() listed for any of its artifacts, and an edit to
    # one artifact's files what it listed for that one.
    GATE.listed(event, to_read, str(project), EDIT + os.path.realpath(edit_file))


def before_edit(event: dict) -> None:
    """The artifact of a file is found in the configuration of the project found from its
    folder upward, or else of the one found from the working folder. Its edit file is the one
    guide() answers with, the content file when it has one and the main file otherwise."""
    request = event.get("tool_input") or {}
    target = request.get("file_path") or request.get("notebook_path") or ""
    if not target:
        return
    cwd = Path(event["cwd"])
    path = os.path.realpath(cwd / target)
    for project in dict.fromkeys(p for p in (GATE.project_of(Path(path).parent), GATE.project_of(cwd)) if p):
        for alias, (main, content) in artifact_files(project).items():
            if path in (main, content):
                files = GATE.unread(event).get(EDIT + (content or main))
                if files is None:
                    GATE.deny(NO_GUIDE_EDIT.format(alias=alias))
                elif waiting := [file for file in files if Path(file).is_file()]:
                    GATE.deny(UNREAD.format(files=", ".join(waiting)).replace("this call", "this edit"))
                return


if __name__ == "__main__":
    GATE.run({"guide-read": guide_read, "before-edit": before_edit})
