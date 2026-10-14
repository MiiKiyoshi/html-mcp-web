#!/usr/bin/env python3
"""Claude Code hooks that keep an agent from editing a deck before it has read the rules in the
context it is working in.

guide() names the files to read in full. A context that calls it in a project records those
files as unread, a Read that returned a whole file takes it off, and an edit to a deck file is
refused while guide() has not answered for the project in this context or a listed file has not
been read in full. The record is cleared whenever a context starts again (a new session, a
resumed one, a cleared one, or the summary a compaction leaves), since what was read before is
no longer in it. A subagent starts without its parent's context and has a record of its own.
What is checked is that the Read calls returned the whole files, not that they were understood.

  session-start  SessionStart: clear the record, and in a project say what to do.
  guide-read     PostToolUse on guide(): record the files its answer lists to read.
  file-read      PostToolUse on Read: take a file read whole off the record.
  before-edit    PreToolUse on Edit, Write, MultiEdit and NotebookEdit: refuse an edit to a
                 .html file of a project whose rules this context has not read.

A project is a folder holding .html-mcp-web.yaml, found from the file or folder upward. A
project in a linked git worktree is the same project as its place in the main checkout: an
agent isolated in a worktree edits its copy while guide() names the file in the checkout the
server serves. The script needs only the standard library, since it runs outside the
server's environment.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

CONFIG = ".html-mcp-web.yaml"
RECORDS = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "html-mcp-web" / "guide-read"
DECK_FILES = (".html", ".htm")

REMINDER = ("html-mcp: before editing a deck file in this context, call guide() for the intended "
            "artifact and read every file in its read list in full. Use Read without offset or "
            "limit. Edit and Write calls for deck .html files are blocked until guide() and the "
            "required Read calls are recorded for this project.")
NO_GUIDE = ("guide() has not succeeded for {project} in this context. Call it for the intended "
            "artifact, then use Read without offset or limit for every file in its read list. "
            "Read each file in full before retrying this edit.")
UNREAD = ("The required Read calls have not been recorded for these files in this context: "
          "{files}. Use Read without offset or limit for each file, and read its full contents "
          "before retrying this edit.")


def project_of(start: Path) -> Path | None:
    for folder in (start, *start.parents):
        if (folder / CONFIG).is_file():
            return folder
    return None


def identity(project: Path) -> str:
    """The project named by its place in the main checkout. A linked worktree's .git is a file
    naming <main checkout>/.git/worktrees/<name>."""
    for folder in (project, *project.parents):
        git = folder / ".git"
        if git.is_file():
            found = re.match(r"gitdir:\s*(.+)", git.read_text(encoding="utf-8").strip())
            if found is not None:
                gitdir = (folder / found.group(1)).resolve()
                if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
                    return str(gitdir.parent.parent.parent / project.relative_to(folder))
            return str(project)
        if git.exists():
            return str(project)
    return str(project)


def record_of(event: dict) -> Path:
    agent = event.get("agent_id")
    return RECORDS / (event["session_id"] + (f"-{agent}" if agent else ""))


def unread(event: dict) -> dict[str, list[str]]:
    """The files still to read, by project, for this context."""
    try:
        return json.loads(record_of(event).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def keep(event: dict, projects: dict[str, list[str]]) -> None:
    record = record_of(event)
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps(projects), encoding="utf-8")


def response_text(event: dict) -> str:
    response = event.get("tool_response")
    blocks = response if isinstance(response, list) else [response]
    return "\n".join(block.get("text", "") if isinstance(block, dict) else str(block) for block in blocks)


def session_start(event: dict) -> None:
    record_of(event).unlink(missing_ok=True)
    if project_of(Path(event["cwd"])) is not None:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": REMINDER}}))


def guide_read(event: dict) -> None:
    text = response_text(event)
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
    project = project_of(Path(edit_file).parent)
    if project is None:
        return
    projects = unread(event)
    projects[identity(project)] = sorted(os.path.realpath(path) for path in to_read)
    keep(event, projects)


def file_read(event: dict) -> None:
    """A Read counts when it returned the whole file: from its first line, every line, and
    every character, so a file cut at a line or a size limit does not."""
    returned = (event.get("tool_response") or {}).get("file") or {}
    path = os.path.realpath(returned.get("filePath") or (event.get("tool_input") or {}).get("file_path", ""))
    try:
        whole = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    if not (returned.get("startLine") == 1 and returned.get("numLines") == returned.get("totalLines")
            and len(returned.get("content") or "") >= len(whole.rstrip("\n"))):
        return
    projects = unread(event)
    if any(path in files for files in projects.values()):
        keep(event, {project: [file for file in files if file != path] for project, files in projects.items()})


def before_edit(event: dict) -> None:
    tool_input = event.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not path:
        return
    target = Path(path)
    if not target.is_absolute():
        target = Path(event["cwd"]) / target
    if target.suffix.lower() not in DECK_FILES:
        return
    project = project_of(target.parent)
    if project is None:
        return
    projects = unread(event)
    if identity(project) not in projects:
        reason = NO_GUIDE.format(project=project)
    elif projects[identity(project)]:
        reason = UNREAD.format(files=", ".join(projects[identity(project)]))
    else:
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))


if __name__ == "__main__":
    hooks = {"session-start": session_start, "guide-read": guide_read, "file-read": file_read,
             "before-edit": before_edit}
    hooks[sys.argv[1]](json.load(sys.stdin))
