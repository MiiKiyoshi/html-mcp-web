import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / "plugin"
GATE = PLUGIN / "hooks" / "guide_gate.py"


@pytest.fixture()
def run(tmp_path: Path):
    """Runs one hook of the gate the way Claude Code does, with its own cache directory."""
    cache = tmp_path / "cache"

    def hook(kind: str, event: dict) -> dict | None:
        result = subprocess.run(
            [sys.executable, str(GATE), kind], input=json.dumps(event), capture_output=True, text=True,
            env={**os.environ, "XDG_CACHE_HOME": str(cache)}, check=True)
        return json.loads(result.stdout) if result.stdout.strip() else None

    return hook


def deck_project(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / ".html-mcp-web.yaml").write_text("artifacts: {}\n", encoding="utf-8")
    (root / "docs").mkdir()
    return root


def edit(session: str, path: Path, agent: str | None = None, tool: str = "Edit") -> dict:
    event = {"session_id": session, "cwd": str(path.parent), "tool_name": tool,
             "tool_input": {"file_path": str(path)}}
    if agent is not None:
        event["agent_id"] = agent
    return event


def guided(session: str, edit_file: Path, agent: str | None = None) -> dict:
    """What the PostToolUse hook receives after guide(): the answer names the file to edit."""
    event = {"session_id": session, "cwd": str(edit_file.parent), "tool_name": "mcp__html-mcp__guide",
             "tool_response": [{"type": "text", "text": f"Edit file: {edit_file}\n\nComponent reference ..."}]}
    if agent is not None:
        event["agent_id"] = agent
    return event


def refused(answer: dict | None) -> bool:
    return answer is not None and answer["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_a_deck_edit_waits_for_guide_and_waits_again_after_a_compaction(tmp_path: Path, run) -> None:
    project = deck_project(tmp_path / "deck")
    content = project / "docs" / "content.html"
    # A context starts in the project: it is told how to get the rules.
    started = run("session-start", {"session_id": "s1", "cwd": str(project), "source": "startup"})
    assert "guide() has not succeeded" in started["hookSpecificOutput"]["additionalContext"]
    # An edit to a deck file before guide() is refused, with the reason and what to do.
    answer = run("before-edit", edit("s1", content))
    assert refused(answer) and "guide()" in answer["hookSpecificOutput"]["permissionDecisionReason"]
    assert refused(run("before-edit", edit("s1", content, tool="Write")))
    # guide() answers for this project, and the edit goes ahead.
    run("guide-read", guided("s1", content))
    assert run("before-edit", edit("s1", content)) is None
    # A compaction leaves a summary in place of what was read: refused again until guide().
    run("session-start", {"session_id": "s1", "cwd": str(project), "source": "compact"})
    assert refused(run("before-edit", edit("s1", content)))
    run("guide-read", guided("s1", content))
    assert run("before-edit", edit("s1", content)) is None


def test_the_gate_keeps_to_deck_files_of_projects_this_context_has_read(tmp_path: Path, run) -> None:
    project = deck_project(tmp_path / "deck")
    other = deck_project(tmp_path / "other")
    loose = tmp_path / "loose"
    loose.mkdir()
    run("guide-read", guided("s1", project / "docs" / "content.html"))
    # Files that are not deck files, and folders outside any project, are left alone.
    assert run("before-edit", edit("s1", project / "docs" / "notes.md")) is None
    assert run("before-edit", edit("s1", loose / "page.html")) is None
    assert run("session-start", {"session_id": "s2", "cwd": str(loose), "source": "startup"}) is None
    # The rules read for one project do not open another.
    assert refused(run("before-edit", edit("s1", other / "docs" / "content.html")))
    # Another session, or a subagent of this one, has read nothing yet.
    assert refused(run("before-edit", edit("s2", project / "docs" / "content.html")))
    assert refused(run("before-edit", edit("s1", project / "docs" / "content.html", agent="a1")))
    run("guide-read", guided("s1", project / "docs" / "content.html", agent="a1"))
    assert run("before-edit", edit("s1", project / "docs" / "content.html", agent="a1")) is None
    # A server started before guide() carried the rules answers with paths, and still opens it.
    run("guide-read", {"session_id": "s4", "cwd": str(project), "tool_name": "mcp__html-mcp__guide",
                       "tool_response": [{"type": "text", "text": json.dumps(
                           {"edit_file": str(project / "docs" / "content.html"), "read": []})}]})
    assert run("before-edit", edit("s4", project / "docs" / "content.html")) is None
    # A guide() answer with no file to edit marks nothing.
    run("guide-read", {"session_id": "s3", "cwd": str(project), "tool_name": "mcp__html-mcp__guide",
                       "tool_response": [{"type": "text", "text": "not set up for review"}]})
    assert refused(run("before-edit", edit("s3", project / "docs" / "content.html")))


def test_a_worktree_of_the_project_counts_as_the_project(tmp_path: Path, run) -> None:
    """An agent isolated in a linked git worktree edits its copy of the deck, while guide()
    names the file in the main checkout the server serves. Taken as two projects, the edit
    stayed refused after guide() had answered."""
    main = tmp_path / "repo"
    deck_project(main / "deck")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "-q", str(main)], check=True)
    subprocess.run([*git, "-C", str(main), "add", "-A"], check=True)
    subprocess.run([*git, "-C", str(main), "commit", "-q", "-m", "deck"], check=True)
    copy = tmp_path / "copy"
    subprocess.run([*git, "-C", str(main), "worktree", "add", "-q", str(copy)], check=True)
    in_main, in_copy = main / "deck" / "docs" / "content.html", copy / "deck" / "docs" / "content.html"
    assert refused(run("before-edit", edit("s1", in_copy)))
    run("guide-read", guided("s1", in_main))
    assert run("before-edit", edit("s1", in_copy)) is None
    assert run("before-edit", edit("s1", in_main)) is None
    # And the other way round: guide() answered from a server started in the worktree.
    run("guide-read", guided("s2", in_copy))
    assert run("before-edit", edit("s2", in_main)) is None


def test_the_plugin_is_listed_and_wired_to_the_gate() -> None:
    root = PLUGIN.parent
    market = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert market["plugins"] == [{"name": manifest["name"], "source": "./plugin",
                                  "description": market["plugins"][0]["description"]}]
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    commands = {event: [hook["command"] for entry in entries for hook in entry["hooks"]]
                for event, entries in hooks.items()}
    assert commands == {
        "SessionStart": ['python3 "${CLAUDE_PLUGIN_ROOT}/hooks/guide_gate.py" session-start'],
        "PostToolUse": ['python3 "${CLAUDE_PLUGIN_ROOT}/hooks/guide_gate.py" guide-read'],
        "PreToolUse": ['python3 "${CLAUDE_PLUGIN_ROOT}/hooks/guide_gate.py" before-edit'],
    }
    assert hooks["PostToolUse"][0]["matcher"] == "mcp__html-mcp__guide"
    assert hooks["PreToolUse"][0]["matcher"] == "Edit|Write|MultiEdit|NotebookEdit"
