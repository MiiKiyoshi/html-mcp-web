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


@pytest.fixture()
def rules(tmp_path: Path) -> list[Path]:
    """Two files guide() lists to read in full, and a reference it lists to consult."""
    folder = tmp_path / "rules"
    folder.mkdir()
    for name, text in (("PRODUCTION.md", "# Production\n\nOne rule.\n"), ("GUIDELINE.md", "# Guideline\n\nTwo rules.\nThree.\n"),
                       ("COMPONENTS.md", "# Components\n")):
        (folder / name).write_text(text, encoding="utf-8")
    return [folder / "PRODUCTION.md", folder / "GUIDELINE.md", folder / "COMPONENTS.md"]


def deck_project(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / ".html-mcp-web.yaml").write_text("artifacts: {}\n", encoding="utf-8")
    (root / "docs").mkdir()
    return root


def with_context(event: dict, session: str, agent: str | None) -> dict:
    event["session_id"] = session
    if agent is not None:
        event["agent_id"] = agent
    return event


def call(session: str, project: Path, tool: str = "read_comments", agent: str | None = None) -> dict:
    """What the PreToolUse hook receives when an html-mcp tool is called."""
    return with_context({"cwd": str(project), "tool_name": f"mcp__html-mcp__{tool}", "tool_input": {}},
                        session, agent)


def guided(session: str, edit_file: Path, rules: list[Path], agent: str | None = None, answer: dict | None = None) -> dict:
    """What the PostToolUse hook receives after guide(): one line of JSON in a text block."""
    answer = answer or {"edit_file": str(edit_file), "read": [str(path) for path in rules[:2]], "consult": [str(rules[2])]}
    return with_context({"cwd": str(edit_file.parent), "tool_name": "mcp__html-mcp__guide",
                         "tool_response": [{"type": "text", "text": json.dumps(answer)}]}, session, agent)


def read(session: str, path: Path, agent: str | None = None, start: int = 1, lines: int | None = None,
         content: str | None = None) -> dict:
    """What the PostToolUse hook receives after Read, as Claude Code reports a returned file."""
    text = path.read_text(encoding="utf-8")
    total = len(text.splitlines())
    returned = {"filePath": str(path), "content": text if content is None else content,
                "numLines": total if lines is None else lines, "startLine": start, "totalLines": total}
    tool_input = {"file_path": str(path)} if start == 1 and lines is None else {"file_path": str(path), "offset": start, "limit": lines}
    return with_context({"cwd": str(path.parent), "tool_name": "Read", "tool_input": tool_input,
                         "tool_response": {"type": "text", "file": returned}}, session, agent)


def unchanged(session: str, path: Path, offset: int | None = None, limit: int | None = None) -> dict:
    """What the PostToolUse hook receives when Claude Code answers a Read of a file it already
    returned in this context: the file's path and no contents."""
    tool_input = {"file_path": str(path)} if offset is None else {"file_path": str(path), "offset": offset, "limit": limit}
    return with_context({"cwd": str(path.parent), "tool_name": "Read", "tool_input": tool_input,
                         "tool_response": {"type": "file_unchanged", "file": {"filePath": str(path)}}}, session, None)


def reason(answer: dict | None) -> str | None:
    if answer is None:
        return None
    assert answer["hookSpecificOutput"]["permissionDecision"] == "deny"
    return answer["hookSpecificOutput"]["permissionDecisionReason"]


def test_html_mcp_tools_wait_for_the_listed_files_and_wait_again_after_a_compaction(tmp_path: Path, run, rules) -> None:
    project = deck_project(tmp_path / "deck")
    content = project / "docs" / "content.html"
    production, guideline, components = rules
    # A context starts in the project: it is told what to do.
    started = run("session-start", {"session_id": "s1", "cwd": str(project), "source": "startup"})
    assert "read every file in its read list in full" in started["hookSpecificOutput"]["additionalContext"]
    # Before guide() the review tools are refused, and the reason says to call it. guide()
    # itself, and setup_info() for setting a project up, are open.
    for tool in ("listen", "read_comments", "write_comments", "layout", "image"):
        assert "guide() has not succeeded" in reason(run("before-tool", call("s1", project, tool)))
    assert run("before-tool", call("s1", project, "guide")) is None
    assert run("before-tool", call("s1", project, "setup_info")) is None
    # After guide() the tools wait for the files it lists to read, named in the reason. The
    # reference to consult by section is not among them.
    run("guide-read", guided("s1", content, rules))
    waiting = reason(run("before-tool", call("s1", project, "write_comments")))
    assert str(production) in waiting and str(guideline) in waiting and str(components) not in waiting
    run("file-read", read("s1", production))
    waiting = reason(run("before-tool", call("s1", project)))
    assert str(production) not in waiting and str(guideline) in waiting
    # A Read of part of a file, or one that came back cut short, does not count.
    run("file-read", read("s1", guideline, start=2, lines=2))
    run("file-read", read("s1", guideline, content="# Guideline\n"))
    assert str(guideline) in reason(run("before-tool", call("s1", project)))
    run("file-read", read("s1", guideline))
    for tool in ("listen", "read_comments", "write_comments", "layout", "image"):
        assert run("before-tool", call("s1", project, tool)) is None
    # guide() called again in the same context lists the files again. Reading them again finds
    # them unchanged, which counts for a whole Read and not for a part.
    run("guide-read", guided("s1", content, rules))
    assert reason(run("before-tool", call("s1", project))) is not None
    run("file-read", unchanged("s1", production))
    run("file-read", unchanged("s1", guideline, offset=2, limit=2))
    waiting = reason(run("before-tool", call("s1", project)))
    assert str(production) not in waiting and str(guideline) in waiting
    run("file-read", unchanged("s1", guideline))
    assert run("before-tool", call("s1", project)) is None
    # A compaction leaves a summary in place of what was read: refused again until guide()
    # answers and its files are read again.
    run("session-start", {"session_id": "s1", "cwd": str(project), "source": "compact"})
    assert "guide() has not succeeded" in reason(run("before-tool", call("s1", project)))
    run("guide-read", guided("s1", content, rules))
    assert reason(run("before-tool", call("s1", project))) is not None
    for path in rules[:2]:
        run("file-read", read("s1", path))
    assert run("before-tool", call("s1", project)) is None


def test_each_context_reads_the_rules_for_itself(tmp_path: Path, run, rules) -> None:
    project = deck_project(tmp_path / "deck")
    loose = tmp_path / "loose"
    loose.mkdir()
    content = project / "docs" / "content.html"
    run("guide-read", guided("s1", content, rules))
    for path in rules[:2]:
        run("file-read", read("s1", path))
    assert run("before-tool", call("s1", project)) is None
    # A context started outside any project is told nothing.
    assert run("session-start", {"session_id": "s2", "cwd": str(loose), "source": "startup"}) is None
    # Another session, or a subagent of this one, has read nothing yet.
    assert reason(run("before-tool", call("s2", project))) is not None
    assert reason(run("before-tool", call("s1", project, agent="a1"))) is not None
    run("guide-read", guided("s1", content, rules, agent="a1"))
    for path in rules[:2]:
        run("file-read", read("s1", path, agent="a1"))
    assert run("before-tool", call("s1", project, agent="a1")) is None
    # A guide() answer with no file to edit records nothing.
    run("guide-read", {"session_id": "s3", "cwd": str(project), "tool_name": "mcp__html-mcp__guide",
                       "tool_response": [{"type": "text", "text": "not set up for review"}]})
    assert "guide() has not succeeded" in reason(run("before-tool", call("s3", project)))


def test_the_reads_of_one_turn_are_all_recorded(tmp_path: Path, run) -> None:
    """The Reads of one turn run their hooks at once, and each rewrote the record from what it
    had read: one read the record while another had emptied it to write and failed, and others
    wrote back files already taken off, so a file read whole stayed unread."""
    from concurrent.futures import ThreadPoolExecutor

    project = deck_project(tmp_path / "deck")
    content = project / "docs" / "content.html"
    files = []
    for number in range(5):
        path = tmp_path / f"rule{number}.md"
        path.write_text(f"# Rule {number}\n\nText.\n", encoding="utf-8")
        files.append(path)
    answer = {"edit_file": str(content), "read": [str(path) for path in files], "consult": []}
    with ThreadPoolExecutor(len(files)) as pool:
        for turn in range(10):
            session = f"turn{turn}"
            run("guide-read", guided(session, content, files, answer=answer))
            list(pool.map(lambda path: run("file-read", read(session, path)), files))
            assert run("before-tool", call(session, project)) is None


def test_answers_from_servers_started_on_earlier_code_still_work(tmp_path: Path, run, rules) -> None:
    project = deck_project(tmp_path / "deck")
    content = project / "docs" / "content.html"
    # Paths with the reference among them: it is consulted by section, so it is not required.
    run("guide-read", guided("s1", content, rules, answer={"edit_file": str(content), "read": [str(path) for path in rules]}))
    for path in rules[:2]:
        run("file-read", read("s1", path))
    assert run("before-tool", call("s1", project)) is None
    # A record left by the earlier plugin, a list of projects, counts as no record.
    records = tmp_path / "cache" / "html-mcp-web" / "guide-read"
    (records / "s5").write_text(json.dumps([str(project)]), encoding="utf-8")
    assert "guide() has not succeeded" in reason(run("before-tool", call("s5", project)))
    # The documents themselves in the answer: they are already in the context.
    run("guide-read", {"session_id": "s2", "cwd": str(project), "tool_name": "mcp__html-mcp__guide",
                       "tool_response": [{"type": "text", "text": f"Edit file: {content}\n\n===== rules ====="}]})
    assert run("before-tool", call("s2", project)) is None


def test_the_plugin_is_listed_and_wired_to_the_gate() -> None:
    root = PLUGIN.parent
    market = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert market["plugins"] == [{"name": manifest["name"], "source": "./plugin",
                                  "description": market["plugins"][0]["description"]}]
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    wired = {(event, entry.get("matcher")): [hook["command"].split()[-1] for hook in entry["hooks"]]
             for event, entries in hooks.items() for entry in entries}
    assert wired == {
        ("SessionStart", None): ["session-start"],
        ("PostToolUse", "mcp__html-mcp__guide"): ["guide-read"],
        ("PostToolUse", "Read"): ["file-read"],
        ("PreToolUse", "mcp__html-mcp__.*"): ["before-tool"],
    }
    assert all(hook["command"].startswith('python3 "${CLAUDE_PLUGIN_ROOT}/hooks/guide_gate.py" ')
               for entries in hooks.values() for entry in entries for hook in entry["hooks"])
