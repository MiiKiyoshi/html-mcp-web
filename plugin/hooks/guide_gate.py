#!/usr/bin/env python3
"""Claude Code hooks that keep an agent from editing a deck without the rules in its context.

The rules come in full from the html-mcp guide() tool. A context that has called it in a
project is marked, the mark is cleared whenever a context starts again (a new session, a
resumed one, a cleared one, or the summary a compaction leaves), and an edit to a deck file
in a project the context has no mark for is refused with the reason. A subagent starts
without its parent's context and has a mark of its own.

  session-start  SessionStart: clear the mark, and in a project say how to get the rules.
  guide-read     PostToolUse on guide(): mark the project of the file guide() names.
  before-edit    PreToolUse on Edit, Write, MultiEdit and NotebookEdit: refuse an edit to a
                 .html file in a project without a mark.

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
MARKS = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "html-mcp-web" / "guide-read"
DECK_FILES = (".html", ".htm")

REMINDER = ("html-mcp: guide() has not succeeded for this project in this context. Call it for the "
            "intended artifact and read the whole answer before editing. Edit and Write calls for "
            "deck .html files are blocked until guide() succeeds.")
REFUSAL = ("guide() has not succeeded for {project} in this context. Call it for the intended "
           "artifact and read the whole answer before retrying this edit.")


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


def mark_of(event: dict) -> Path:
    agent = event.get("agent_id")
    return MARKS / (event["session_id"] + (f"-{agent}" if agent else ""))


def marked(event: dict) -> set[str]:
    try:
        return set(json.loads(mark_of(event).read_text(encoding="utf-8")))
    except FileNotFoundError:
        return set()


def session_start(event: dict) -> None:
    mark_of(event).unlink(missing_ok=True)
    if project_of(Path(event["cwd"])) is not None:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": REMINDER}}))


def guide_read(event: dict) -> None:
    response = event.get("tool_response")
    blocks = response if isinstance(response, list) else [response]
    text = "\n".join(block.get("text", "") if isinstance(block, dict) else str(block) for block in blocks)
    # A server started before guide() carried the rules answers with their paths, under
    # "edit_file". Not taken, its sessions could edit no deck until the server restarted.
    found = re.search(r"^Edit file: (.+)$", text, flags=re.MULTILINE) or re.search(r'"edit_file": "([^"]+)"', text)
    if found is None:
        return
    project = project_of(Path(found.group(1)).parent)
    if project is None:
        return
    mark = mark_of(event)
    mark.parent.mkdir(parents=True, exist_ok=True)
    mark.write_text(json.dumps(sorted(marked(event) | {identity(project)})), encoding="utf-8")


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
    if project is None or identity(project) in marked(event):
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": REFUSAL.format(project=project),
    }}))


if __name__ == "__main__":
    {"session-start": session_start, "guide-read": guide_read, "before-edit": before_edit}[sys.argv[1]](json.load(sys.stdin))
