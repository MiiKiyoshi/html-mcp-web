import asyncio
import json
import os
import queue
import socket
import shlex
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest
import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from html_mcp_web import config as config_module
from html_mcp_web.config import load_config
from html_mcp_web.mcp_client import CLI, INIT_GUIDE, ProjectBinding
from html_mcp_web.mcp_contract import agent_comment, agent_comment_summary, revision_of, short_time
from html_mcp_web.mcp_server import _listen_from_start, create_server
from html_mcp_web.project_server import SharedProjectServer
from html_mcp_web.server import HtmlReviewServer
from html_mcp_web.shared import plugin_monitor
from html_mcp_web.tool import TOOL
from tests.html_chrome import needs_browser


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def project(tmp_path: Path, port: int | None = None):
    (tmp_path / "slides.html").write_text(
        '<!doctype html><html><body><main class="pages"><section class="page"></section></main></body></html>',
        encoding="utf-8",
    )
    path = tmp_path / ".html-mcp-web.yaml"
    path.write_text(yaml.safe_dump({
        "artifacts": {"slides": {"layout": "slides", "main": "slides.html"}},
        "port": available_port() if port is None else port,
    }, sort_keys=False), encoding="utf-8")
    return load_config(path)


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def space_snapshot() -> list[dict]:
    return [{
        "number": 1,
        "bbox": [0, 0, 1280, 720],
        "children": ["p1:0"],
        "nodes": {
            "p1:0": {
                "kind": "text",
                "element": "p#target",
                "bbox": [100, 100, 300, 100],
                "padding": [0, 0, 0, 0],
                "children": [],
                "lines": [[100, 100, 260, 24]],
                "overflow": False,
            },
        },
    }]


def answer(call):
    """What a tool call hands the agent: its one text, read back as JSON."""
    return json.loads(asyncio.run(call)[0].text)


def guided(mcp, artifact: str = "slides") -> dict:
    """What guide() hands the agent: the file to edit, the files to read, the reference."""
    return answer(mcp.call_tool("guide", {"artifact": artifact}))


def test_source_comments_are_compact_until_the_agent_reads_detail() -> None:
    comment = {
        "id": "c-12345678",
        "anchor": {
            "kind": "source", "file": "content.html", "quote": "exact words",
            "prefix": "large private context", "suffix": "more private context",
            "line_start": 12, "line_end": 12, "column_start": 8, "column_end": 19,
            "stale": False,
        },
        "thread": [{"id": "e-00000001", "author": "human", "at": "2026-09-14T00:00:00+00:00", "text": "Revise this"}],
        "updated": "2026-09-14T00:00:00+00:00",
        "status": "open",
        "created": "2026-09-14T00:00:00+00:00",
    }
    listed = agent_comment_summary(comment, True)
    assert listed["anchor"] == {
        "kind": "source", "file": "content.html", "line_start": 12,
        "line_end": 12, "stale": False,
    }
    assert "quote" not in listed["anchor"]
    detailed = agent_comment(comment)
    assert detailed["anchor"]["quote"] == "exact words"
    assert "prefix" not in detailed["anchor"] and "suffix" not in detailed["anchor"]


@pytest.mark.asyncio
async def test_stdio_mcp_starts_without_project_config(tmp_path: Path) -> None:
    server = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from html_mcp_web.cli import main_mcp; raise SystemExit(main_mcp())"],
        cwd=tmp_path,
        # The child imports the package by name, which the installed copy answers first;
        # the copy under test goes ahead of it, or a worktree's change is never spoken to.
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
             "XDG_CACHE_HOME": str(tmp_path / "cache")},
    )
    async with stdio_client(server, errlog=sys.stderr) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            assert initialized.instructions is not None
            assert "read_comments(new=True)" in initialized.instructions
            tools = await session.list_tools()
            assert [tool.name for tool in tools.tools] == [
                "guide",
                "read_comments",
                "write_comments",
                "image",
                "figure",
                "layout",
                "listen",
                "setup_info",
            ]
            assert all(initialized.instructions not in (tool.description or "") for tool in tools.tools)
            # Before setup, the answer is where to set up, not a tool that half works.
            unready = await session.call_tool("guide", {"artifact": "slides"})
            assert unready.isError is True and "init.md" in unready.content[0].text
            project(tmp_path)
            guided = await session.call_tool("guide", {"artifact": "slides"})
            assert guided.isError is False
            # One text, one line of JSON: no structured copy beside it.
            assert guided.structuredContent is None and "\n" not in guided.content[0].text
            assert json.loads(guided.content[0].text)["edit_file"] == str(tmp_path / "slides.html")


@pytest.mark.asyncio
async def test_stdio_mcp_serves_existing_project_at_startup(tmp_path: Path) -> None:
    config = project(tmp_path)
    server = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from html_mcp_web.cli import main_mcp; raise SystemExit(main_mcp())"],
        cwd=tmp_path,
        # The child imports the package by name, which the installed copy answers first;
        # the copy under test goes ahead of it, or a worktree's change is never spoken to.
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
             "XDG_CACHE_HOME": str(tmp_path / "cache")},
    )
    async with stdio_client(server, errlog=sys.stderr) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            with urllib.request.urlopen(f"http://127.0.0.1:{config.port}/state") as response:
                state = json.loads(response.read().decode("utf-8"))
            assert state["config_path"] == str(config.config_path)


def test_mcp_connects_after_config_is_created_without_restarting(tmp_path: Path) -> None:
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        # The setup guide's path is as long as the install location, the rest is bounded.
        assert len(mcp.instructions) - len(str(INIT_GUIDE)) < 900
        # Setup lives in the guide: the instructions give its path and nothing else about it.
        assert mcp.instructions.endswith(f"Setup: read {INIT_GUIDE}.")
        for needed in ("read_comments(new=True)", "guide()", "layout()", "image()", "write_comments",
                       "listen()", "init.md"):
            assert needed in mcp.instructions, needed
        for needed in ("asks to listen", "do not poll", "duplicate",
                       "write in chat only what no thread carries", "not the replies or the edits they report"):
            assert needed in mcp.instructions.lower(), needed
        # A comment asking what a page means is met where the comment is handled, as a
        # report on the page rather than a question about the quoted words, judged from what
        # the pages show rather than from what the author knows.
        assert "as a confusion report on that page" in mcp.instructions
        assert "judged from the rendered pages alone" in mcp.instructions
        assert "repaired in the content guideline's repair order" in mcp.instructions
        # Read only when it applies: the geometric advice rides on a layout answer with errors.
        for gone in ("templates/README.md", "Monitor", "inspect", "resource_uri", "geometric"):
            assert gone not in mcp.instructions, gone
        tools = asyncio.run(mcp.list_tools())
        schemas = {tool.name: tool.inputSchema for tool in tools}
        assert list(schemas) == [
            "guide",
            "read_comments",
            "write_comments",
            "image",
            "figure",
            "layout",
            "listen",
            "setup_info",
        ]
        # A project with one artifact needs no name: nothing else would tell the agent it.
        assert "required" not in schemas["guide"]
        assert schemas["read_comments"]["required"] == ["artifact"]
        assert schemas["write_comments"]["required"] == ["artifact", "action"]
        # Without a page, save writes every page.
        assert schemas["image"]["required"] == ["artifact"]
        assert schemas["image"]["properties"]["dpi"]["minimum"] == 36
        assert schemas["image"]["properties"]["dpi"]["maximum"] == 300
        assert set(schemas["image"]["properties"]) >= {"save", "out", "target"}
        assert schemas["layout"]["required"] == ["artifact"]
        assert set(schemas["layout"]["properties"]) == {
            "artifact", "page", "target", "clearance", "min_width", "min_height"}

        with pytest.raises(Exception, match="not set up for review") as unready:
            asyncio.run(mcp.call_tool("guide", {"artifact": "slides"}))
        assert str(INIT_GUIDE) in str(unready.value) and str(CLI) in str(unready.value)

        project(tmp_path)
        assert guided(mcp)["edit_file"] == str(tmp_path / "slides.html")
    finally:
        binding.stop()


def test_setup_info_reports_paths_and_choices_without_connecting(tmp_path: Path, monkeypatch) -> None:
    user_config = tmp_path / "user"
    monkeypatch.setattr(config_module, "USER_CONFIG_DIR", user_config)
    # A user template without build.py, and one that hides the built-in of its name.
    (user_config / "templates" / "house").mkdir(parents=True)
    (user_config / "templates" / "neutral-slides").mkdir(parents=True)
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    project(parent)
    config_path = str((parent / ".html-mcp-web.yaml").resolve())
    binding = ProjectBinding(child)
    try:
        mcp = create_server(binding)
        files = sorted(tmp_path.rglob("*"))
        info = answer(mcp.call_tool("setup_info", {}))
        assert info["startup_dir"] == str(child.resolve())
        assert info["discovered_config_path"] == config_path
        assert info["bound_config_path"] is None
        templates = info["templates"]
        assert templates["user"] == {"dir": str(user_config / "templates"),
                                     "entries": ["house", "neutral-slides"]}
        assert {"neutral-report", "neutral-slides"} <= set(templates["built_in"]["entries"])
        assert templates["used"]["neutral-slides"] == "user"
        assert templates["used"]["neutral-report"] == "built_in"
        assert set(templates["incomplete"]) == {"user/house", "user/neutral-slides"}
        # A missing user folder is reported as missing, not left out.
        assert info["guidelines"]["user"] == {"dir": str(user_config / "guidelines"), "entries": None}
        assert {"neutral-slides", "neutral-report"} <= set(info["guidelines"]["built_in"]["entries"])
        # A report only: no binding, no server, no file.
        assert binding.bound_config_path() is None
        assert sorted(tmp_path.rglob("*")) == files
        guided(mcp)
        assert answer(mcp.call_tool("setup_info", {}))["bound_config_path"] == config_path
    finally:
        binding.stop()


def test_binding_retries_after_invalid_config_is_fixed(tmp_path: Path) -> None:
    config_path = tmp_path / ".html-mcp-web.yaml"
    config_path.write_text("artifacts: [\n", encoding="utf-8")
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        with pytest.raises(Exception, match="while parsing a flow node") as broken:
            asyncio.run(mcp.call_tool("guide", {"artifact": "slides"}))
        assert str(config_path) in str(broken.value)
        config_path.unlink()
        project(tmp_path)
        assert guided(mcp)["edit_file"] == str(tmp_path / "slides.html")
    finally:
        binding.stop()


def test_binding_retries_after_port_collision_is_fixed(tmp_path: Path) -> None:
    port = available_port()
    owner_dir = tmp_path / "owner"
    peer_dir = tmp_path / "peer"
    owner_dir.mkdir()
    peer_dir.mkdir()
    owner_config = project(owner_dir, port=port)
    project(peer_dir, port=port)
    owner = SharedProjectServer(owner_config)
    binding = ProjectBinding(peer_dir)
    try:
        owner.ensure()
        with pytest.raises(RuntimeError, match="serves"):
            binding.connect()
        peer_path = peer_dir / ".html-mcp-web.yaml"
        peer_data = yaml.safe_load(peer_path.read_text(encoding="utf-8"))
        peer_data["port"] = available_port()
        peer_path.write_text(yaml.safe_dump(peer_data, sort_keys=False), encoding="utf-8")
        assert binding.connect() is not None
    finally:
        binding.stop()
        owner.stop()


async def no_check(self, runtime, host) -> None:
    """The tests give the layout result themselves, so the server's own check is held off."""


def server_check(shared: SharedProjectServer, **report) -> dict:
    """A layout report the server records: one carrying its running check's token."""
    review = shared.runner.app["review_server"]
    runtime = review.artifacts["slides"]
    runtime.check_token = "token-of-the-running-check"
    return {"revision": runtime.revision, "static": review.static_tag(), "check": runtime.check_token,
            "settled": True, "errors": [], "warnings": [], "space": space_snapshot(), **report}


def test_clients_with_same_config_share_server_and_follower_takes_over(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(HtmlReviewServer, "_ensure_layout_checked", no_check)
    config = project(tmp_path)
    first = SharedProjectServer(config)
    second = SharedProjectServer(config)
    binding = ProjectBinding(tmp_path)
    try:
        first.ensure()
        second.ensure()
        assert first.thread is not None
        assert second.thread is None
        with urllib.request.urlopen(f"http://127.0.0.1:{config.port}/state") as response:
            assert response.status == 200

        mcp = create_server(binding)
        assert guided(mcp)["edit_file"] == str(tmp_path / "slides.html")

        base = f"http://127.0.0.1:{config.port}"
        created = post_json(f"{base}/artifacts/slides/comments", {
            "anchor": {"kind": "artifact"},
            "text": "Reply without resolving",
        })
        text_comment = post_json(f"{base}/artifacts/slides/comments", {
            "anchor": {
                "kind": "text",
                "quote": "selected text",
                "prefix": "before ",
                "suffix": " after",
                "start": {"path": [1, 0], "offset": 0},
                "end": {"path": [1, 0], "offset": 13},
                "artifact_digest": "internal digest",
            },
            "text": "Check this text",
        })
        def revision_now() -> int:
            with urllib.request.urlopen(f"{base}/state", timeout=3) as response:
                return json.loads(response.read().decode("utf-8"))["artifacts"]["slides"]["revision"]

        revision_before = revision_now()
        listed = answer(mcp.call_tool("read_comments", {"artifact": "slides"}))
        # Newest first; a listing filtered by status does not repeat it on every row.
        assert [comment["id"] for comment in listed["comments"]] == [text_comment["id"], created["id"]]
        assert listed["comments"][1] == {
            "id": created["id"],
            "anchor": {"kind": "artifact"},
            "request": "Reply without resolving",
            "thread_entries": 1,
            "last_human_at": short_time(created["thread"][0]["at"]),
        }
        # A text comment is chosen by what it quotes, not read in full to learn it.
        assert listed["comments"][0]["anchor"] == {"kind": "text", "quote": "selected text"}
        everything = answer(mcp.call_tool("read_comments", {"artifact": "slides", "status": "all"}))
        assert everything["comments"][0]["status"] == "open"
        # A time names a minute, and the minute it names comes back rather than being missed.
        first_seen = listed["comments"][1]["last_human_at"]
        later = answer(mcp.call_tool("read_comments", {"artifact": "slides", "since": first_seen}))
        assert {comment["id"] for comment in later["comments"]} == {created["id"], text_comment["id"]}
        unanswered = answer(mcp.call_tool("read_comments", {"artifact": "slides", "unanswered": True}))
        assert len(unanswered["comments"]) == 2

        selected = answer(mcp.call_tool("read_comments", {
            "artifact": "slides",
            "ids": [text_comment["id"]],
        }))
        assert len(selected["comments"]) == 1
        assert created["id"] not in json.dumps(selected)
        stripped = selected["comments"][0]
        assert stripped["anchor"] == {
            "kind": "text",
            "quote": "selected text",
            "prefix": "before ",
            "suffix": " after",
        }
        assert "created" not in stripped
        # The thread's rev is the one thing a rewrite of an entry has to quote.
        assert stripped["rev"] == revision_of(text_comment["updated"])

        replied = answer(mcp.call_tool("write_comments", {
            "artifact": "slides",
            "action": "reply",
            "text": f"{created['id']}: Changed the wording",
            "edited_files": ["slides.html"],
        }))
        assert set(replied["updated"][0]) == {"id", "rev"}
        # A reply is a thread's business: the artifact's revision stays where it was.
        assert revision_now() == revision_before
        # The agent's reply leaves the thread answered; a later human entry reopens it.
        unanswered = answer(mcp.call_tool("read_comments", {"artifact": "slides", "unanswered": True}))
        assert [comment["id"] for comment in unanswered["comments"]] == [text_comment["id"]]
        newest_seen = listed["comments"][0]["last_human_at"]

        replied_read = answer(mcp.call_tool("read_comments", {
            "artifact": "slides",
            "ids": [created["id"]],
        }))
        replied_comment = replied_read["comments"][0]
        assert replied_comment["thread"][-1]["edited_files"] == ["slides.html"]
        assert "edits" not in replied_comment["thread"][-1]
        # A rewrite quotes the rev it read; the one it was handed after replying is current.
        own = replied_comment["thread"][-1]["id"]
        assert replied_comment["rev"] == replied["updated"][0]["rev"]
        rewritten = answer(mcp.call_tool("write_comments", {
            "artifact": "slides",
            "action": "edit",
            "text": f"{created['id']}/{own}@{replied_comment['rev']}: Changed the wording again",
        }))
        with pytest.raises(Exception, match="stale"):
            asyncio.run(mcp.call_tool("write_comments", {
                "artifact": "slides",
                "action": "edit",
                "text": f"{created['id']}/{own}@{replied_comment['rev']}: A third wording",
            }))
        reread = answer(mcp.call_tool("read_comments", {"artifact": "slides", "ids": [created["id"]]}))
        assert reread["comments"][0]["thread"][-1]["text"] == "Changed the wording again"
        assert reread["comments"][0]["rev"] == rewritten["updated"][0]["rev"]
        post_json(f"{base}/artifacts/slides/comments/{created['id']}/reply", {"text": "Still wrong"})
        unanswered = answer(mcp.call_tool("read_comments", {"artifact": "slides", "unanswered": True, "since": newest_seen}))
        assert [comment["id"] for comment in unanswered["comments"]] == [created["id"], text_comment["id"]]
        assert unanswered["comments"][0]["thread_entries"] == 3
        assert unanswered["comments"][0]["request"] == "Still wrong"

        post_json(f"{base}/artifacts/slides/layout", server_check(first))
        measured = answer(mcp.call_tool("layout", {"artifact": "slides", "page": 1, "clearance": 12}))
        assert measured["errors"] == [] and "note" not in measured
        assert measured["children"][0]["ref"] == "p1:0"
        assert measured["clearance"] == 12

        # A thread's status is the reviewer's, set from the page, and the agent reads it by
        # the page's names: an archived thread is listed, read and drafted as archived.
        page = f"http://127.0.0.1:{binding._shared.port}/artifacts/slides/comments"
        post_json(f"{page}/status", {"ids": [created["id"]], "status": "archived"})
        archived = [answer(mcp.call_tool("read_comments", {"artifact": "slides", "status": status}))
                    for status in ("archived", "all")]
        assert [row["id"] for row in archived[0]["comments"]] == [created["id"]]
        assert {row["id"]: row["status"] for row in archived[1]["comments"]}[created["id"]] == "archived"
        archived_read = answer(mcp.call_tool("read_comments", {"artifact": "slides", "ids": [created["id"]]}))
        assert archived_read["comments"][0]["status"] == "archived"
        drafted = answer(mcp.call_tool("read_comments", {"artifact": "slides", "ids": [created["id"]], "save": True}))
        told = json.dumps([archived, archived_read]) + Path(drafted["path"]).read_text(encoding="utf-8")
        assert "archived" in told and "reference" not in told
        post_json(f"{page}/status", {"ids": [created["id"]], "status": "resolved"})
        closed_read = answer(mcp.call_tool("read_comments", {
            "artifact": "slides",
            "ids": [created["id"]],
        }))
        assert closed_read["comments"][0]["status"] == "resolved"

        first.stop()
        second.ensure()
        assert second.thread is not None
        with urllib.request.urlopen(f"http://127.0.0.1:{config.port}/state") as response:
            assert response.status == 200
    finally:
        binding.stop()
        first.stop()
        second.stop()



def test_failed_start_releases_the_lock_so_a_retry_can_serve(tmp_path: Path) -> None:
    # The first start fails (the config breaks between the binding and the serve thread's
    # own load); the lock must be freed so that fixing the cause and retrying serves the
    # project instead of blocking forever on this process's lock. A missing main no longer
    # fails the start at all: that is one artifact's problem, reported on it.
    port = available_port()
    config_path = tmp_path / ".html-mcp-web.yaml"
    good = yaml.safe_dump({
        "artifacts": {"slides": {"layout": "slides", "main": "slides.html"}},
        "port": port,
    }, sort_keys=False)
    config_path.write_text(good, encoding="utf-8")
    (tmp_path / "slides.html").write_text(
        '<!doctype html><html><body><main class="pages"><section class="page"></section></main></body></html>',
        encoding="utf-8")
    shared = SharedProjectServer(load_config(config_path))
    config_path.write_text("artifacts: [broken", encoding="utf-8")
    try:
        with pytest.raises(RuntimeError, match="failed to start"):
            shared.ensure()
        assert shared.lock_handle is None  # the lock was released, not leaked
        config_path.write_text(good, encoding="utf-8")
        shared.ensure()  # would raise "lock is held but port is not reachable" before the fix
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/state", timeout=3) as response:
            assert response.status == 200
    finally:
        shared.stop()


def test_read_new_hands_over_what_is_unread_and_unanswered(tmp_path: Path) -> None:
    config = project(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        base = f"http://127.0.0.1:{config.port}"
        read_new = lambda **extra: answer(mcp.call_tool("read_comments", {"artifact": "slides", "new": True, **extra}))
        binding.require_client()
        asked = post_json(f"{base}/artifacts/slides/comments", {"anchor": {"kind": "artifact"}, "text": "First ask"})
        answered = post_json(f"{base}/artifacts/slides/comments", {"anchor": {"kind": "artifact"}, "text": "Old ask"})
        post_json(f"{base}/artifacts/slides/comments/update", {"comment_ids": [answered["id"]], "message": "Done"})

        # A first call has no cursor: what stands unanswered bounds it, not the history.
        first = read_new()
        assert "from" not in first
        assert [(c["id"], [e["text"] for e in c["entries"]]) for c in first["comments"]] == [(asked["id"], ["First ask"])]
        assert set(first["comments"][0]) == {"id", "rev", "anchor", "entries"}
        assert read_new()["comments"] == []

        post_json(f"{base}/artifacts/slides/comments/update", {"comment_ids": [asked["id"]], "message": "Fixed"})
        post_json(f"{base}/artifacts/slides/comments/{asked['id']}/reply", {"text": "Still wrong"})
        follow = read_new()
        assert [e["text"] for e in follow["comments"][0]["entries"]] == ["Still wrong"]
        assert follow["from"] == first["cursor"]
        assert read_new()["comments"] == []
        # A turn that went wrong is taken again from the moment it read from.
        again = read_new(since=follow["from"])
        assert [e["text"] for e in again["comments"][0]["entries"]] == ["Still wrong"]

        # A closed thread is not where a request arrives.
        post_json(f"{base}/artifacts/slides/comments/{answered['id']}/reply", {"text": "One more"})
        post_json(f"{base}/artifacts/slides/comments/status", {"ids": [answered["id"]], "status": "resolved"})
        assert read_new(since=follow["from"])["comments"][0]["id"] == asked["id"]
        assert len(read_new(since=follow["from"])["comments"]) == 1
        with pytest.raises(Exception, match="takes no ids"):
            asyncio.run(mcp.call_tool("read_comments", {"artifact": "slides", "new": True, "ids": [asked["id"]]}))
    finally:
        binding.stop()


def test_pages_name_single_pages_and_ranges_in_order_each_once() -> None:
    from aiohttp import web
    from html_mcp_web.server import page_numbers

    assert page_numbers("47-52,57,62-63", 78) == [47, 48, 49, 50, 51, 52, 57, 62, 63]
    assert page_numbers("3, 1-3", 5) == [3, 1, 2]
    for spec in ("0-2", "4-9", "5-3", "a", ""):
        with pytest.raises(web.HTTPBadRequest):
            page_numbers(spec, 8)


@needs_browser
def test_image_save_writes_a_png_and_returns_its_path(tmp_path: Path) -> None:
    # save exists so a page can be handed to the user without the image entering the
    # transcript; the tool returns a path, not pixels.
    project(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        content = asyncio.run(mcp.call_tool(
            "image", {"artifact": "slides", "page": 1, "save": True}))
        # The answer is the file's place, not the page, scale and colour the call named.
        target = Path(content[0].text)
        assert target == tmp_path / ".html-mcp-web" / "renders" / "slides-p1.png"
        # A grey picture does not say whether the page is grey: the answer says it.
        assert [part.text for part in content[1:]] == ["Grayscale render. Pass grayscale=false to see colour."]
        coloured_file = asyncio.run(mcp.call_tool(
            "image", {"artifact": "slides", "page": 1, "save": True, "grayscale": False, "out": "p1.png"}))
        assert [part.text for part in coloured_file] == [str(tmp_path / "p1.png")]
        # Without a page, save writes every page from one print and names the folder once.
        every = asyncio.run(mcp.call_tool(
            "image", {"artifact": "slides", "save": True, "grayscale": False, "out": "pages"}))
        written = sorted(path.name for path in (tmp_path / "pages").iterdir())
        assert every[0].text == f"{tmp_path / 'pages'}: p1.png to p{len(written)}.png" and len(every) == 1
        assert written == [f"p{number}.png" for number in sorted(range(1, len(written) + 1), key=lambda n: f"p{n}.png")]
        # The pages named go into a folder of the caller's choosing, outside the project too.
        outside = tmp_path.parent / f"{tmp_path.name}-renders"
        chosen = asyncio.run(mcp.call_tool(
            "image", {"artifact": "slides", "save": True, "grayscale": False, "pages": "1", "out": str(outside)}))
        assert chosen[0].text == f"{outside}: p<N>.png for pages 1" and len(chosen) == 1
        assert sorted(path.name for path in outside.iterdir()) == ["p1.png"]
        with pytest.raises(Exception, match=r"'1-2' is not within 1\.\.1"):
            asyncio.run(mcp.call_tool("image", {"artifact": "slides", "save": True, "pages": "1-2"}))
        with pytest.raises(Exception, match="goes without page"):
            asyncio.run(mcp.call_tool("image", {"artifact": "slides", "page": 1, "save": True, "pages": "1"}))
        with pytest.raises(Exception, match="page is needed unless save"):
            asyncio.run(mcp.call_tool("image", {"artifact": "slides"}))
        shown = asyncio.run(mcp.call_tool("image", {"artifact": "slides", "page": 1}))
        assert [part.type for part in shown] == ["image", "text"]
        assert shown[1].text == "Grayscale render. Pass grayscale=false to see colour."
        coloured = asyncio.run(mcp.call_tool("image", {"artifact": "slides", "page": 1, "grayscale": False}))
        assert [part.type for part in coloured] == ["image"]
        assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        with pytest.raises(Exception, match="inside the project"):
            asyncio.run(mcp.call_tool(
                "image", {"artifact": "slides", "page": 1, "save": True, "out": "../escape.png"}))
    finally:
        binding.stop()


def test_the_lock_names_its_holder(tmp_path: Path) -> None:
    """A lock held by a process that serves nothing used to say only that it was held,
    and finding the holder was a by-hand dig through /proc. The holder writes its pid
    into a file beside the lock, which Windows lets others read while the lock is held, and
    the refusal names it with the way out."""
    from html_mcp_web.project_server import SharedProjectServer

    config = project(tmp_path)
    lock_path = tmp_path / ".html-mcp-web" / "server.lock"
    holder_path = lock_path.with_name("server.holder")
    shared = SharedProjectServer(load_config(config.config_path))
    try:
        shared.ensure()
        assert f"pid {os.getpid()}, port {config.port}" == holder_path.read_text(encoding="utf-8")
    finally:
        shared.stop()

    # Another process holds the lock and serves nothing, the way a wedged session does.
    holding = ("import sys, time\n"
               "from pathlib import Path\n"
               "from html_mcp_web.shared import filelock\n"
               "handle = open(sys.argv[1], 'a+', encoding='utf-8')\n"
               "filelock.lock(handle)\n")
    holder = subprocess.Popen(
        [sys.executable, "-c", holding +
         "Path(sys.argv[1]).with_name('server.holder').write_text('pid 424242, port 65000', encoding='utf-8')\n"
         "print('holding', flush=True)\n"
         "time.sleep(60)\n",
         str(lock_path)],
        stdout=subprocess.PIPE, text=True, encoding="utf-8")
    try:
        assert holder.stdout.readline().strip() == "holding"
        fresh = SharedProjectServer(load_config(config.config_path))
        with pytest.raises(RuntimeError) as refusal:
            fresh.ensure()
        assert "held by pid 424242, port 65000" in str(refusal.value)
        assert "reconnect MCP in that session or kill" in str(refusal.value)
    finally:
        holder.terminate()
        holder.wait(timeout=5)

    # A holder that dies while the contender is polling frees the lock with it, and the
    # contender takes over instead of reporting a dead pid as alive.
    dying = subprocess.Popen(
        [sys.executable, "-c", holding +
         "print('holding', flush=True)\n"
         "time.sleep(1)\n",
         str(lock_path)],
        stdout=subprocess.PIPE, text=True, encoding="utf-8")
    try:
        assert dying.stdout.readline().strip() == "holding"
        taker = SharedProjectServer(load_config(config.config_path))
        taker.ensure()   # the holder dies about a second in; the poll claims the lock
        try:
            assert f"pid {os.getpid()}" in holder_path.read_text(encoding="utf-8")
        finally:
            taker.stop()
    finally:
        dying.wait(timeout=10)


def test_guide_names_the_file_to_edit_what_to_read_and_what_to_consult(tmp_path: Path) -> None:
    """Paths only, since clients cap a tool result at different sizes. The files to read in
    full and the reference looked up by section are listed apart."""
    project(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        answer_ = guided(mcp)
        assert set(answer_) == {"edit_file", "read", "consult"}
        assert answer(mcp.call_tool("guide", {})) == answer_
        templates = Path(__file__).resolve().parents[1] / "templates"
        assert answer_["edit_file"] == str(tmp_path / "slides.html")
        assert answer_["read"] == [str(templates / "README.md"), str(templates / "PRODUCTION.md")]
        assert answer_["consult"] == [str(templates / "KITS.md"), str(templates / "REVIEWER.md")]
        assert "reader-facing unit" not in json.dumps(answer_, ensure_ascii=False)
        with pytest.raises(Exception, match="unknown artifact"):
            asyncio.run(mcp.call_tool("guide", {"artifact": "report"}))
    finally:
        binding.stop()


def test_the_tools_take_the_alias_on_the_tab_and_name_the_aliases_otherwise(tmp_path: Path) -> None:
    """An artifact goes by its alias alone, which may hold spaces, a slash and any script.
    The tools take it as the tab shows it, or the path of the artifact's file, and a name
    that is neither is answered with the aliases."""
    alias = "Draft 2/3 (초안)"
    (tmp_path / "deck").mkdir()
    (tmp_path / "deck" / "deck.html").write_text(
        '<!doctype html><html><body><main class="pages"><section class="page"></section></main></body></html>',
        encoding="utf-8")
    path = tmp_path / ".html-mcp-web.yaml"
    path.write_text(yaml.safe_dump({
        "artifacts": {alias: {"layout": "slides", "main": "deck/deck.html"}},
        "port": available_port(),
    }, sort_keys=False, allow_unicode=True), encoding="utf-8")
    config = load_config(path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        assert guided(mcp, alias)["edit_file"] == str(tmp_path / "deck" / "deck.html")
        base = f"http://127.0.0.1:{config.port}"
        created = post_json(f"{base}/artifacts/Draft%202%2F3%20%28%EC%B4%88%EC%95%88%29/comments",
                            {"anchor": {"kind": "artifact"}, "text": "Tighten this."})
        handed = answer(mcp.call_tool("read_comments", {"artifact": alias, "new": True}))
        assert [comment["id"] for comment in handed["comments"]] == [created["id"]]
        assert (tmp_path / ".html-mcp-web" / "comments" / "Draft 2%2F3 (초안).json").is_file()
        # A path names the same artifact, and what was handed by its alias is not handed again.
        for name in ("deck/deck.html", str(tmp_path / "deck" / "deck.html")):
            assert answer(mcp.call_tool("read_comments", {"artifact": name, "new": True}))["comments"] == []
        with pytest.raises(Exception, match="unknown artifact: deck.html. The artifacts are 'Draft 2/3 \\(초안\\)'"):
            asyncio.run(mcp.call_tool("read_comments", {"artifact": "deck.html"}))
        with pytest.raises(Exception, match="The artifacts are 'Draft 2/3"):
            asyncio.run(mcp.call_tool("guide", {"artifact": "deck"}))
    finally:
        binding.stop()


def test_replies_are_one_text_with_a_comment_id_at_each_line_head() -> None:
    """An agent writing a list of objects serialized the prose inside them by hand, and
    by habit as \\uXXXX escapes: five or six tokens a character, and twice a miscounted
    code point that changed the word. A top-level string it writes as it is."""
    from html_mcp_web.mcp_contract import parse_replies

    parsed = parse_replies(
        "c-1244b790: 같은 mechanism 하나를 두 파일이 다른 수준에서 다룹니다.\n"
        "두 번째 문단도 이어집니다: 콜론이 있어도 같은 답글입니다.\n"
        "\n"
        "c-d1bcb60c: 맞습니다. §3.2 (2)의 첫 문장이 그렇습니다.\n")
    assert parsed == [
        ("c-1244b790", "같은 mechanism 하나를 두 파일이 다른 수준에서 다룹니다.\n"
                       "두 번째 문단도 이어집니다: 콜론이 있어도 같은 답글입니다."),
        ("c-d1bcb60c", "맞습니다. §3.2 (2)의 첫 문장이 그렇습니다."),
    ]
    # A blank line inside a reply belongs to it; only a line head with an id starts one.
    assert parse_replies("c-1244b790: first paragraph.\n\nsecond paragraph.") == [
        ("c-1244b790", "first paragraph.\n\nsecond paragraph.")]
    for bad, why in (
        ("just prose", "no reply"),
        ("prose first\nc-1244b790: then a reply", "before the first"),
        ("c-1244b790: \n", "is empty"),
        ("c-1244b790: one\nc-1244b790: twice", "at most once"),
    ):
        with pytest.raises(ValueError, match=why):
            parse_replies(bad)


def test_guide_for_a_templated_artifact_names_its_content_file_and_template_notes(
    tmp_path: Path, monkeypatch,
) -> None:
    from html_mcp_web.cli import main
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--layout", "slides", "--template", "neutral-slides",
                 "--content", "content.html", "--port", str(available_port())]) == 0
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        answer_ = guided(mcp)
        # The content file is what a templated artifact is written in; the main file is built.
        assert answer_["edit_file"] == str(tmp_path / "content.html")
        notes = Path(answer_["read"][-1])
        assert notes.parent.name == "neutral-slides" and notes.name == "README.md"
        for path in answer_["read"]:
            assert Path(path).read_text(encoding="utf-8") not in json.dumps(answer_)
    finally:
        binding.stop()





def test_layout_reports_the_revisions_errors_and_a_pages_detail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(HtmlReviewServer, "_ensure_layout_checked", no_check)
    config = project(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        binding.require_client()
        with urllib.request.urlopen(f"http://127.0.0.1:{config.port}/state") as response:
            state = json.loads(response.read().decode("utf-8"))
        revision = state["artifacts"]["slides"]["revision"]
        post_json(f"http://127.0.0.1:{config.port}/artifacts/slides/layout", server_check(binding._shared, errors=[
            "page 1 exceeds the slides height at p1:0",
            "page 2 exceeds the slides height at p2:0",
            'page 2 p "Some words…" wastes its last line on a 40px tail "tail"',
        ]))

        whole = answer(mcp.call_tool("layout", {"artifact": "slides"}))
        assert whole["revision"] == revision
        assert len(whole["errors"]) == 3
        # The advice on fixing them comes with errors, not with every session.
        assert "font size or padding only after" in whole["note"]
        # A wasted last line is cleared without touching the words: shortened to clear one,
        # a definition came out that no one could read. The advice comes only with a tail.
        assert "without shortening the text" in whole["note"]
        first = answer(mcp.call_tool("layout", {"artifact": "slides", "page": 1}))
        assert "font size or padding only after" in first["note"]
        assert "wasted last line" not in first["note"]
        detailed = answer(mcp.call_tool("layout", {"artifact": "slides", "page": 1}))
        assert detailed["errors"] == ["page 1 exceeds the slides height at p1:0"]
        assert detailed["children"][0]["ref"] == "p1:0"
        assert "page 2" not in json.dumps(detailed)
        with pytest.raises(Exception, match="target needs page"):
            asyncio.run(mcp.call_tool("layout", {"artifact": "slides", "target": "p1:0"}))
    finally:
        binding.stop()


def test_guide_gives_each_artifact_the_neutral_guideline_of_its_layout(tmp_path: Path, monkeypatch) -> None:
    """A deck and a report in one project, under a meeting guideline built on
    neutral-slides: the deck reads neutral-slides and the meeting guideline, the report
    neutral-report, and the neutral checks are on for both."""
    user_config = tmp_path / "user-config"
    meeting = user_config / "guidelines" / "team-meeting" / "GUIDELINE.md"
    meeting.parent.mkdir(parents=True)
    meeting.write_text("---\nextends: neutral-slides\n---\n# Team meeting\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "USER_CONFIG_DIR", user_config)
    config = project(tmp_path)
    (tmp_path / "paper").mkdir()
    (tmp_path / "paper" / "report.html").write_text(
        '<!doctype html><html><body><main class="pages"><section class="page"></section></main></body></html>',
        encoding="utf-8")
    data = yaml.safe_load(config.config_path.read_text(encoding="utf-8"))
    data["artifacts"]["report"] = {"layout": "report", "main": "paper/report.html"}
    data["guideline"] = "team-meeting"
    config.config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    built_in = Path(config_module.__file__).resolve().parent.parent / "guidelines"

    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        assert guided(mcp, "slides")["read"][-2:] == [str(built_in / "neutral-slides" / "GUIDELINE.md"), str(meeting)]
        assert guided(mcp, "report")["read"][-1] == str(built_in / "neutral-report" / "GUIDELINE.md")
        assert str(meeting) not in guided(mcp, "report")["read"]
        artifacts = asyncio.run(binding.require_client().request_json("GET", "/state"))["artifacts"]
        assert artifacts["slides"]["neutral_guideline"] and artifacts["report"]["neutral_guideline"]
    finally:
        binding.stop()


def test_guide_lists_the_configured_guideline_after_the_one_it_extends(
    tmp_path: Path, monkeypatch,
) -> None:
    user_config = tmp_path / "user-config"
    guideline_path = user_config / "guidelines" / "team-meeting" / "GUIDELINE.md"
    guideline_path.parent.mkdir(parents=True)
    guideline_text = "---\nextends: neutral-slides\n---\n# Team meeting\n\nNever inline this marker in discovery.\n"
    guideline_path.write_text(guideline_text, encoding="utf-8")
    monkeypatch.setattr(config_module, "USER_CONFIG_DIR", user_config)
    config = project(tmp_path)
    data = yaml.safe_load(config.config_path.read_text(encoding="utf-8"))
    data["guideline"] = "team-meeting"
    config.config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        answer_ = guided(mcp)
        # The guideline it extends comes first, so the general rules are read before
        # the ones that add to or override them.
        neutral = Path(config_module.__file__).resolve().parent.parent / "guidelines" / "neutral-slides" / "GUIDELINE.md"
        assert answer_["read"][-2:] == [str(neutral), str(guideline_path)]
        assert "Never inline this marker" not in json.dumps(answer_)
        # Paths are the whole of it: no resources beside them to keep in step.
        assert asyncio.run(mcp.list_resources()) == []
    finally:
        binding.stop()


def _session() -> subprocess.Popen:
    """A process that stands in for a session's Claude Code, alive until it is killed."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


def _runs_as(monitor: subprocess.Popen) -> set[str]:
    """The pids the plugin's monitor runs its Python as: the one started, whose shell execs it,
    and under Git Bash on Windows, where the exec starts the Python as a process of its own
    under the shell, that one, and the Python a virtual environment's launcher starts under it
    in turn, which is the one that writes the record."""
    try:
        return {str(monitor.pid), *(str(child.pid) for child in psutil.Process(monitor.pid).children(recursive=True))}
    except psutil.Error:
        return {str(monitor.pid)}


class Lines:
    """What a process prints, line by line, read on a thread of its own: Windows cannot wait on
    a pipe with select."""

    def __init__(self, stream) -> None:
        self.lines: queue.Queue = queue.Queue()
        threading.Thread(target=lambda: [self.lines.put(line) for line in stream], daemon=True).start()

    def next(self, timeout: float) -> str:
        """The next line, without its end, or "" when none comes within *timeout* seconds."""
        try:
            line = self.lines.get(timeout=timeout)
        except queue.Empty:
            return ""
        return (line.decode("utf-8") if isinstance(line, bytes) else line).rstrip("\r\n")


@pytest.mark.parametrize("codex", [False, True])
def test_listen(tmp_path: Path, monkeypatch, codex) -> None:
    # The tool returns at once with a command for the harness to watch in the background;
    # blocking here would freeze the agent, which is what the button exists to avoid.
    project(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        context = SimpleNamespace(session=SimpleNamespace(client_params=SimpleNamespace(
            clientInfo=SimpleNamespace(name="claude-code"))))
        monkeypatch.setattr(mcp, "get_context", lambda: context)
        told = answer(mcp.call_tool("listen", {}))
        # The waiter is Python, the same on every system: the interpreter the server runs in.
        command = shlex.split(told["command"])
        assert command[:3] == [Path(sys.executable).as_posix(), "-m", "html_mcp_web.waiter"]
        assert command[3] == str(binding._shared.port) and len(command) == 5
        # Claude Code's Monitor takes command, description and timeout_ms (at most 30 minutes).
        assert "Monitor" in told["how"] and "persistent" not in told["how"]
        assert 'description="' in told["how"] and "timeout_ms=1800000" in told["how"]
        assert "write_stdin" not in told["how"]
        # An expiry is not restarted: an agent cannot tell whether the user is still there.
        assert "When it expires, leave it stopped" in told["how"]
        # The user opens the page themselves, so the agent is handed the address to give.
        assert f"http://localhost:{binding._shared.port}," in told["how"]
        for name in ("codex-mcp-client", "other-client"):
            context.session.client_params.clientInfo.name = name
            selected = answer(mcp.call_tool("listen", {}))
            assert "Monitor" not in selected["how"]
            assert "the user asks" in selected["how"]
            assert ("codex queue" in selected["how"]) == (name == "codex-mcp-client")
            assert ('sandbox_permissions="require_escalated"' in selected["how"]) == (name == "codex-mcp-client")
        tool = next(t for t in asyncio.run(mcp.list_tools()) if t.name == "listen")
        assert "ctx" not in tool.inputSchema["properties"]

        # The whole loop, live: an early press is picked up and acked (the server's
        # watermark moves), the same process parks again instead of exiting or replaying
        # it, and the next press comes out of that process.
        base = f"http://127.0.0.1:{binding._shared.port}"

        def press():
            urllib.request.urlopen(urllib.request.Request(f"{base}/review-request", method="POST")).close()

        def review():
            with urllib.request.urlopen(f"{base}/state") as reply:
                return json.loads(reply.read().decode("utf-8"))["review"]

        args = []
        if codex:
            # Stands in for codex queue: it fails until codex.ready exists, and then prints the
            # message after its first line, the event's name.
            stub = tmp_path / "codex.py"
            stub.write_text(
                "#!python\n"
                "import sys\n"
                "from pathlib import Path\n"
                f"here = Path({str(tmp_path / 'codex')!r})\n"
                "if sys.argv[1:5] != ['queue', '--thread', 'test-thread', '--message'] or len(sys.argv) != 6:\n"
                "    sys.exit(2)\n"
                "if not Path(f'{here}.ready').exists():\n"
                "    Path(f'{here}.failed').touch()\n"
                "    sys.exit(1)\n"
                # It writes UTF-8, as the waiter does, whatever a Korean Windows writes a pipe in.
                "sys.stdout.reconfigure(encoding='utf-8')\n"
                "print('\\n'.join(sys.argv[5].split('\\n')[1:]), flush=True)\n", encoding="utf-8")
            programs = tmp_path / "bin"
            if os.name == "nt":
                # On Windows the waiter runs a codex.exe, which hands its arguments on whole, as
                # a program does: here a launcher, of the kind pip makes for a script, that
                # runs the stand-in with Python.
                from pip._vendor.distlib.scripts import ScriptMaker
                ScriptMaker(str(tmp_path), str(programs)).make(stub.name)
            else:
                programs.mkdir()
                (programs / "codex").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{stub}" "$@"\n', encoding="utf-8")
                (programs / "codex").chmod(0o755)
            monkeypatch.setenv("PATH", f"{programs}{os.pathsep}{os.environ['PATH']}")
            args = ["--codex", "test-thread"]
        press()
        # Each listen() call names a new listener, and the last one is the one presses go to.
        waiter = subprocess.Popen([*shlex.split(selected["command"]), *args],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        printed = Lines(waiter.stdout)
        line = printed.next
        try:
            if codex:
                deadline = time.monotonic() + 5
                while not (tmp_path / "codex.failed").exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                assert (tmp_path / "codex.failed").exists()
                assert review()["consumed"] == 0
                (tmp_path / "codex.ready").touch()
            assert line(15).startswith("[review]")
            time.sleep(1.0)
            assert waiter.poll() is None
            assert review() == {"calls": 1, "consumed": 1, "waiters": 1, "lanes": {}}    # parked again
            assert line(1.5) == ""                                           # and silent
            press()
            assert line(15).startswith("[review]")
            time.sleep(1.0)
            assert waiter.poll() is None
            assert review() == {"calls": 2, "consumed": 2, "waiters": 1, "lanes": {}}

            # The server going away is not the end of the waiter: a reconnect of the MCP
            # client restarted it and the monitor died with "[gone]", to be started again
            # by hand. It says so once, keeps trying, says when the server answers again,
            # and the next press still comes out of the same process.
            binding._shared.stop()
            assert line(15).startswith("[gone]")
            assert line(3) == ""                    # said once, not on every try
            binding._shared.ensure()
            press()
            assert line(40).startswith("[back]")   # the retry pauses grow to 30s at most
            assert line(15).startswith("[review]")
            assert waiter.poll() is None
        finally:
            waiter.terminate()
            waiter.wait(timeout=5)
    finally:
        binding.stop()


def test_listen_hands_the_waiter_to_the_plugin_monitor(tmp_path: Path, monkeypatch) -> None:
    """In a session the plugin's monitor serves, listen() hands it the waiter and tells the
    agent not to start one, and the monitor passes a press on as the waiter prints it."""
    project(tmp_path)
    cache = tmp_path / "cache"
    monkeypatch.setattr(TOOL, "monitors", cache / "html-mcp-web" / "monitor")
    session = _session()
    monkeypatch.setattr(plugin_monitor, "claude_pid", lambda: session.pid)
    monitor = subprocess.Popen(
        ["sh", str(Path(__file__).parents[1] / "plugin" / "monitors" / "review.sh"), str(session.pid)],
        stdout=subprocess.PIPE, text=True, encoding="utf-8", env={**os.environ, "XDG_CACHE_HOME": str(cache)})
    binding = ProjectBinding(tmp_path)
    try:
        record = TOOL.monitors / f"{session.pid}.monitor"
        deadline = time.monotonic() + 5
        while not record.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert record.read_text(encoding="utf-8").strip() in _runs_as(monitor)
        mcp = create_server(binding)
        context = SimpleNamespace(session=SimpleNamespace(client_params=SimpleNamespace(
            clientInfo=SimpleNamespace(name="claude-code"))))
        monkeypatch.setattr(mcp, "get_context", lambda: context)
        told = answer(mcp.call_tool("listen", {}))
        assert "plugin's monitor now runs the command" in told["how"]
        assert "Monitor(" not in told["how"] and "On [review]" in told["how"]
        handed = (TOOL.monitors / f"{session.pid}.command").read_text(encoding="utf-8").splitlines()
        assert handed[1] == told["command"]
        base = f"http://127.0.0.1:{binding._shared.port}"
        urllib.request.urlopen(urllib.request.Request(f"{base}/review-request", method="POST")).close()
        assert Lines(monitor.stdout).next(15).startswith("[review]")
        # The session ending ends the monitor, its waiter, and its record.
        session.kill()
        session.wait()                  # reaped, or kill -0 still finds it
        monitor.wait(timeout=10)
        assert not record.exists()
    finally:
        for process in (session, monitor):
            if process.poll() is None:
                process.kill()
                process.wait()
        binding.stop()


def test_a_session_with_the_plugin_listens_from_its_start(tmp_path: Path, monkeypatch) -> None:
    """Where the plugin's monitor runs for the session, the server starts listening with
    no listen() call, unless another session listens to the project already."""
    project(tmp_path)
    cache = tmp_path / "cache"
    monkeypatch.setattr(TOOL, "monitors", cache / "html-mcp-web" / "monitor")
    session = _session()
    monkeypatch.setattr(plugin_monitor, "claude_pid", lambda: session.pid)
    monitor = subprocess.Popen(
        ["sh", str(Path(__file__).parents[1] / "plugin" / "monitors" / "review.sh"), str(session.pid)],
        stdout=subprocess.PIPE, text=True, encoding="utf-8", env={**os.environ, "XDG_CACHE_HOME": str(cache)})
    ended = subprocess.Popen([sys.executable, "-c", ""])
    ended.wait()
    binding = ProjectBinding(tmp_path)
    try:
        port = binding.require_client().shared.port
        base = f"http://127.0.0.1:{port}"

        def post(path):
            with urllib.request.urlopen(urllib.request.Request(f"{base}{path}", method="POST")) as reply:
                return json.loads(reply.read())

        handed = TOOL.monitors / f"{session.pid}.command"
        assert post("/wait-review/listen?listener=other")["listening"]
        _listen_from_start(port)
        assert not handed.exists()
        # The other session's waiter ends: this one listens in its place.
        post("/review-request")
        with urllib.request.urlopen(f"{base}/wait-review?listener=other&pid={ended.pid}") as reply:
            assert reply.headers["X-Press"] == "1"
        post("/wait-review/ack?upto=1")
        _listen_from_start(port)
        assert shlex.split(handed.read_text(encoding="utf-8").splitlines()[1])[1:3] == ["-m", "html_mcp_web.waiter"]
        post("/review-request")
        relayed = Lines(monitor.stdout)
        assert relayed.next(15).startswith("[review] reviewer called (press #2)")
        # Asked to listen again, the session restarts its waiter, which hears of no takeover.
        mcp = create_server(binding)
        context = SimpleNamespace(session=SimpleNamespace(client_params=SimpleNamespace(
            clientInfo=SimpleNamespace(name="claude-code"))))
        monkeypatch.setattr(mcp, "get_context", lambda: context)
        assert "plugin's monitor now runs the command" in answer(mcp.call_tool("listen", {}))["how"]
        post("/review-request")
        assert relayed.next(15).startswith("[review] reviewer called (press #3)")
        session.kill()
        session.wait()
        monitor.wait(timeout=10)
    finally:
        for process in (session, monitor):
            if process.poll() is None:
                process.kill()
                process.wait()
        binding.stop()


def test_listen_from_a_client_of_a_named_agent_waits_in_its_lane(tmp_path: Path, monkeypatch) -> None:
    """A client whose name holds one the configuration lists for an agent gets the waiter of
    that agent's lane, which ends after one press, and its listen() does not take presses from
    the session listening. Without the configuration it listens as any client does."""
    config = project(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        context = SimpleNamespace(session=SimpleNamespace(client_params=SimpleNamespace(
            clientInfo=SimpleNamespace(name="second-cli-mcp-client"))))
        monkeypatch.setattr(mcp, "get_context", lambda: context)
        assert "--agent" not in answer(mcp.call_tool("listen", {}))["command"]
        data = yaml.safe_load(config.config_path.read_text(encoding="utf-8"))
        data["agents"] = {"second": {"clients": ["second", "other"]}}
        config.config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        context.session.client_params.clientInfo.name = "claude-code"
        assert "--agent" not in answer(mcp.call_tool("listen", {}))["command"]
        for name in ("second-cli-mcp-client", "Other"):
            context.session.client_params.clientInfo.name = name
            told = answer(mcp.call_tool("listen", {}))
            assert shlex.split(told["command"])[2:] == ["html_mcp_web.waiter", str(binding._shared.port), "-",
                                                        "--agent", "second", "--once"]
            assert "background shell command" in told["how"] and "Monitor" not in told["how"]
    finally:
        binding.stop()


class _Page:
    """A stand-in for the review page that answers every wait with press #3 and records what
    the waiter asks and acknowledges."""

    def __init__(self, line: bytes) -> None:
        import http.server
        import threading

        self.asked, self.acked = [], []
        page = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                page.asked.append(self.path)
                self.send_response(200)
                self.send_header("X-Press", "3")
                self.end_headers()
                self.wfile.write(line)

            def do_POST(self):
                page.acked.append(self.path)
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


def test_the_waiter_ends_when_no_one_reads_it_and_does_not_take_the_press() -> None:
    """A waiter whose reader is gone ends at the first line it cannot print, and leaves the
    press unacknowledged for the next waiter: a stopped monitor left a waiter that took
    presses no one heard."""
    page = _Page(b"[review] reviewer called (press #3)")
    try:
        waiter = subprocess.Popen([sys.executable, "-m", "html_mcp_web.waiter", str(page.port), "one"],
                                  stdout=subprocess.PIPE)
        waiter.stdout.close()
        assert waiter.wait(timeout=20) == 0
        assert page.acked == []
    finally:
        page.server.shutdown()


def test_the_waiter_of_a_lane_prints_one_press_and_ends() -> None:
    """--agent <name> --once: the waiter asks that agent's lane, prints the press, acknowledges it
    there, and ends."""
    page = _Page(b"[review] reviewer called (press #3): new comments: 1 on 'slides' [model=small effort=low]")
    try:
        done = subprocess.run([sys.executable, "-m", "html_mcp_web.waiter", str(page.port), "-",
                               "--agent", "second", "--once"], capture_output=True, text=True, encoding="utf-8",
                              stdin=subprocess.DEVNULL, timeout=20)
    finally:
        page.server.shutdown()
    assert done.returncode == 0
    assert done.stdout.strip().endswith("effort=low]")
    assert len(page.asked) == 1 and "agent=second" in page.asked[0]
    assert page.acked == ["/wait-review/ack?upto=3&agent=second"]


def _start_monitor(session: int, cache: Path) -> subprocess.Popen:
    """The plugin's monitor, as Claude Code starts it, for the session whose pid is *session*."""
    return subprocess.Popen(
        ["sh", str(Path(__file__).parents[1] / "plugin" / "monitors" / "review.sh"), str(session)],
        stdout=subprocess.PIPE, text=True, encoding="utf-8", env={**os.environ, "XDG_CACHE_HOME": str(cache)})


def test_a_monitor_killed_outright_leaves_nothing_a_later_session_takes(tmp_path: Path, monkeypatch) -> None:
    """A monitor killed outright leaves its record and the last command. A pid in that record
    now held by another process is no monitor, and the next monitor for a session with the
    same pid drops the command before it records itself."""
    cache = tmp_path / "cache"
    monkeypatch.setattr(TOOL, "monitors", cache / "html-mcp-web" / "monitor")
    TOOL.monitors.mkdir(parents=True)
    session = _session()
    other = _session()
    monkeypatch.setattr(plugin_monitor, "claude_pid", lambda: session.pid)
    record = TOOL.monitors / f"{session.pid}.monitor"
    handed = TOOL.monitors / f"{session.pid}.command"
    record.write_text(f"{other.pid}\n", encoding="utf-8")
    handed.write_text("1\necho left over\n", encoding="utf-8")
    monitor = None
    try:
        assert plugin_monitor.monitored_session(TOOL) is None
        monitor = _start_monitor(session.pid, cache)
        deadline = time.monotonic() + 5
        while record.read_text(encoding="utf-8").strip() not in _runs_as(monitor) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert plugin_monitor.monitored_session(TOOL) == session.pid
        assert not handed.exists()
    finally:
        for process in (monitor, other, session):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()


def test_the_monitor_ends_a_replaced_waiter_and_all_it_started(tmp_path: Path) -> None:
    """A waiter waits in a request, and what it started holds that open: the monitor ends the
    waiter and all it started when the session hands it another, and when the session ends,
    so that no waiter of an earlier listen() is left asking the page."""
    # Lengths no other run sleeps for: one left over from a run that failed is not this one's.
    first, second = f"61.{os.getpid()}", f"62.{os.getpid()}"
    cache = tmp_path / "cache"
    directory = cache / "html-mcp-web" / "monitor"
    session = _session()
    monitor = _start_monitor(session.pid, cache)
    # The waiter it is handed starts a process that sleeps, and starts it again whenever it ends.
    sleep = "import sys, time; time.sleep(float(sys.argv[1]))"
    waiter = f"import subprocess, sys; [subprocess.run([sys.executable, '-c', {sleep!r}, sys.argv[1]]) for _ in iter(int, 1)]"

    def sleeping(seconds: str) -> bool:
        return any((process.info["cmdline"] or [])[-2:] == [sleep, seconds]
                   for process in psutil.process_iter(["cmdline"]))

    def hand(name: str, seconds: str) -> None:
        command = f"{shlex.quote(Path(sys.executable).as_posix())} -c {shlex.quote(waiter)} {seconds}"
        (directory / f"{session.pid}.command.new").write_text(f"{name}\n{command}\n", encoding="utf-8")
        (directory / f"{session.pid}.command.new").replace(directory / f"{session.pid}.command")
        deadline = time.monotonic() + 5
        while not sleeping(seconds) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert sleeping(seconds)

    def gone(seconds: str) -> bool:
        deadline = time.monotonic() + 5
        while sleeping(seconds) and time.monotonic() < deadline:
            time.sleep(0.1)
        return not sleeping(seconds)

    try:
        deadline = time.monotonic() + 5
        while not (directory / f"{session.pid}.monitor").exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        hand("first", first)
        hand("second", second)
        assert gone(first) and sleeping(second)
    finally:
        session.kill()
        session.wait()
        monitor.wait(timeout=10)
    assert gone(second)


def test_the_monitor_looks_for_its_session_from_the_process_it_is_told(monkeypatch) -> None:
    """Where a monitor's own parents do not lead to Claude Code, its launcher names a process
    that does, and with no session above that one the monitor ends at once."""
    from html_mcp_web.shared import monitor

    asked = []
    monkeypatch.setattr(plugin_monitor, "session_of", lambda pid: asked.append(pid))
    monitor.main(TOOL, ["--from", "4242"])
    assert asked == [4242]


def test_read_comments_offers_the_archived_view(tmp_path: Path) -> None:
    """A thread the reviewer archives is listed apart from open and resolved, and the agent
    asks for that view by the name the page gives it."""
    mcp = create_server(ProjectBinding(tmp_path))
    schemas = {tool.name: tool.inputSchema for tool in asyncio.run(mcp.list_tools())}
    assert schemas["read_comments"]["properties"]["status"]["enum"] == ["open", "resolved", "archived", "all"]


def test_write_comments_takes_edits_of_the_agents_own_entries(tmp_path: Path) -> None:
    mcp = create_server(ProjectBinding(tmp_path))
    schemas = {tool.name: tool.inputSchema for tool in asyncio.run(mcp.list_tools())}
    assert set(schemas["write_comments"]["properties"]) == {
        "artifact", "action", "text", "anchor", "edited_files", "draft", "id", "rev", "changes"}
    assert schemas["write_comments"]["properties"]["action"]["enum"] == ["add", "reply", "edit", "suggest", "withdraw"]
    assert "'c-1a2b3c4d/e-5e6f7a8b@<rev>: '" in json.dumps(schemas["write_comments"]["properties"]["text"])


def test_a_suggestion_is_proposed_on_the_page_and_applied_by_the_reviewer(tmp_path: Path) -> None:
    """A reviewer points at the rendered page. The agent answers with the source change on
    that thread, and nothing reaches the file until the reviewer applies it."""
    import urllib.error

    config = project(tmp_path)
    source = tmp_path / "slides.html"
    source.write_text(
        '<!doctype html><html><body><main class="pages"><section class="page">'
        "<p>Old words here.</p></section></main></body></html>", encoding="utf-8")
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        binding.require_client()
        base = f"http://127.0.0.1:{config.port}/artifacts/slides"
        comment = post_json(f"{base}/comments", {
            "anchor": {"kind": "text", "quote": "Old words here", "prefix": "", "suffix": ".",
                       "start": {"path": [0, 0], "offset": 0}, "end": {"path": [0, 0], "offset": 14},
                       "artifact_digest": "any"},
            "text": "Say it plainly."})

        def call(**arguments):
            return answer(mcp.call_tool("write_comments", {"artifact": "slides", **arguments}))

        def thread():
            return answer(mcp.call_tool("read_comments", {"artifact": "slides", "ids": [comment["id"]]}))["comments"][0]

        def stamp():
            with urllib.request.urlopen(f"{base}/comments/{comment['id']}") as response:
                return json.loads(response.read())["updated"]

        rev = thread()["rev"]
        proposed = call(action="suggest", id=comment["id"], rev=rev, text="Plainer.",
                        changes=[{"old": "Old words", "new": "New words"}])
        assert proposed["id"] == comment["id"]
        read = thread()
        assert read["suggestion"] == [{"old": "Old words", "new": "New words"}]
        # Proposed, not written: the file is as the reviewer left it.
        assert "Old words here." in source.read_text(encoding="utf-8")
        for arguments, refusal in (
            ({"rev": rev, "changes": [{"old": "Old words", "new": "x"}]}, "stale"),
            ({"rev": read["rev"], "changes": [{"old": "not in the file", "new": "x"}]}, "not found in the source"),
        ):
            with pytest.raises(Exception, match=refusal):
                asyncio.run(mcp.call_tool("write_comments", {
                    "artifact": "slides", "action": "suggest", "id": comment["id"], "text": "x", **arguments}))
        with pytest.raises(Exception, match="changes go with suggest"):
            asyncio.run(mcp.call_tool("write_comments", {
                "artifact": "slides", "action": "withdraw", "id": comment["id"], "rev": read["rev"],
                "text": "x", "changes": [{"old": "a", "new": "b"}]}))

        applied = post_json(f"{base}/comments/{comment['id']}/apply-suggestion", {"updated": stamp()})
        assert "New words here." in source.read_text(encoding="utf-8")
        assert "suggestion" not in applied
        assert applied["thread"][-1]["author"] == "human"
        assert applied["thread"][-1]["edits"] == ["slides.html"]
        # The reviewer's own words were rewritten, and the comment follows them.
        assert applied["anchor"]["quote"] == "New words here"

        again = call(action="suggest", id=comment["id"], rev=thread()["rev"], text="Shorter.",
                     changes=[{"old": "New words", "new": "Words"}])
        call(action="withdraw", id=comment["id"], rev=again["rev"], text="Keep it.")
        assert "suggestion" not in thread()

        # A file that moved under the proposal refuses it rather than writing blind.
        call(action="suggest", id=comment["id"], rev=thread()["rev"], text="Once more.",
             changes=[{"old": "New words", "new": "Words"}])
        source.write_text(source.read_text(encoding="utf-8").replace("New words", "Other words"), encoding="utf-8")
        with pytest.raises(urllib.error.HTTPError) as refused:
            post_json(f"{base}/comments/{comment['id']}/apply-suggestion", {"updated": stamp()})
        assert refused.value.code == 409
        assert "Other words" in source.read_text(encoding="utf-8")
    finally:
        binding.stop()


def prose(tmp_path: Path) -> None:
    """A deck whose page holds four sentences, for suggestions to rewrite one each."""
    (tmp_path / "slides.html").write_text(
        '<!doctype html><html><body><main class="pages"><section class="page">'
        + "".join(f"<p>Sentence {n} is long.</p>" for n in range(4))
        + "</section></main></body></html>", encoding="utf-8")


def test_a_press_counts_the_threads_new_gives_by_the_rule_unanswered_lists_by(tmp_path: Path) -> None:
    """Of five open threads the reviewer wrote in, one waits for the agent: a suggestion
    applied asks nothing. The line a press prints, read_comments(new=True) and
    read_comments(unanswered=True) name that one alike. A word written after the record
    makes its thread wait again. The press and new=True leave out what new=True has
    carried before, which unanswered=True still lists while it has no answer."""
    config = project(tmp_path)
    prose(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        binding.require_client()
        server = HtmlReviewServer(config)
        base = f"http://127.0.0.1:{config.port}/artifacts/slides/comments"

        def ids(**arguments) -> list[str]:
            told = answer(mcp.call_tool("read_comments", {"artifact": "slides", **arguments}))
            return [comment["id"] for comment in told["comments"]]

        applied = []
        for n in range(4):
            asked = post_json(base, {"anchor": {"kind": "artifact"}, "text": f"Tighten sentence {n}."})
            proposed = post_json(f"{base}/{asked['id']}/suggest", {
                "updated": asked["updated"], "text": "Shorter.",
                "changes": [{"old": f"Sentence {n} is long", "new": f"Sentence {n}"}]})
            done = post_json(f"{base}/{asked['id']}/apply-suggestion", {"updated": proposed["updated"]})
            assert done["thread"][-1]["applied"] is True and "awaits_agent" not in done
            applied.append(asked["id"])
        request = post_json(base, {"anchor": {"kind": "artifact"}, "text": "Add a citation here."})

        assert "new comments: 1 on 'slides'" in server._review_line()
        assert ids(unanswered=True) == [request["id"]]
        assert ids(new=True) == [request["id"]]

        post_json(f"{base}/{applied[0]}/reply", {"text": "And the figure?"})
        assert "new comments: 1 on 'slides'" in server._review_line()
        assert ids(new=True) == [applied[0]]
        assert ids(unanswered=True) == [applied[0], request["id"]]
        assert "no new comments" in server._review_line()
    finally:
        binding.stop()


def test_a_suggestion_applied_is_told_to_the_agent_once(tmp_path: Path) -> None:
    """The reviewer applying a suggestion asks nothing, and the agent hears of it once: the
    press counts its thread, read_comments(new=True) carries the record with the files it
    changed, and neither does again though no reply follows. unanswered=True, which lists
    what waits for an answer, leaves it out."""
    config = project(tmp_path)
    prose(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        binding.require_client()
        server = HtmlReviewServer(config)
        base = f"http://127.0.0.1:{config.port}/artifacts/slides/comments"

        def read(**arguments) -> list[dict]:
            return answer(mcp.call_tool("read_comments", {"artifact": "slides", **arguments}))["comments"]

        asked = post_json(base, {"anchor": {"kind": "artifact"}, "text": "Tighten it."})
        assert [told["id"] for told in read(new=True)] == [asked["id"]]
        proposed = post_json(f"{base}/{asked['id']}/suggest", {
            "updated": asked["updated"], "text": "Shorter.",
            "changes": [{"old": "Sentence 0 is long", "new": "Sentence 0"}]})
        assert "no new comments" in server._review_line()

        post_json(f"{base}/{asked['id']}/apply-suggestion", {"updated": proposed["updated"]})
        assert "new comments: 1 on 'slides'" in server._review_line()
        assert read(unanswered=True) == []
        (told,) = read(new=True)
        assert told["id"] == asked["id"]
        (entry,) = told["entries"]
        assert entry["applied"] is True and entry["edited_files"] == ["slides.html"]
        assert "no new comments" in server._review_line()
        assert read(new=True) == []
    finally:
        binding.stop()


def test_a_suggestion_rejected_is_told_to_the_agent_once(tmp_path: Path) -> None:
    """The reviewer turns down a suggestion. The record it leaves holds what was turned
    down, which the press counts and read_comments(new=True) carries once, and the thread
    read by its id still shows. It waits for no answer, and what the reviewer writes after
    it is asked as ever."""
    config = project(tmp_path)
    prose(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        binding.require_client()
        server = HtmlReviewServer(config)
        base = f"http://127.0.0.1:{config.port}/artifacts/slides/comments"

        def read(**arguments) -> list[dict]:
            return answer(mcp.call_tool("read_comments", {"artifact": "slides", **arguments}))["comments"]

        here = post_json(base, {"anchor": {"kind": "artifact"}, "text": "Tighten it."})
        assert len(read(new=True)) == 1
        proposed = post_json(f"{base}/{here['id']}/suggest", {
            "updated": here["updated"], "text": "Shorter.",
            "changes": [{"old": "Sentence 0 is long", "new": "Sentence 0"}]})
        assert "no new comments" in server._review_line()
        assert read(unanswered=True) == []

        told = post_json(f"{base}/{here['id']}/reject-suggestion", {"updated": proposed["updated"]})
        assert told["thread"][-1]["text"] == "Rejected suggestion.\n− Sentence 0 is long\n+ Sentence 0"
        assert "new comments: 1 on 'slides'" in server._review_line()
        assert read(unanswered=True) == []
        (fresh,) = read(new=True)
        assert fresh["id"] == here["id"] and [entry["rejected"] for entry in fresh["entries"]] == [True]
        assert "no new comments" in server._review_line()
        assert read(new=True) == []
        # Read whole later, the thread still says what was turned down.
        (whole,) = read(ids=[here["id"]])
        assert whole["thread"][-1]["text"].startswith("Rejected suggestion.")

        # Why, the reviewer says in a reply, which asks the agent as any reply does.
        post_json(f"{base}/{here['id']}/reply", {"text": "Too curt."})
        assert [asked["id"] for asked in read(unanswered=True)] == [here["id"]]
        (told,) = read(new=True)
        assert [entry["text"] for entry in told["entries"]] == ["Too curt."]
    finally:
        binding.stop()


def test_layout_says_at_once_when_nothing_can_check(tmp_path: Path, monkeypatch) -> None:
    """With no browser to check in and no review page open, waiting could only end in the same
    answer."""
    import time

    from html_mcp_web import chrome

    project(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        binding.require_client()
        # Where its installer puts it counts as installed too, on Windows and macOS.
        monkeypatch.setattr(chrome, "binary", lambda: None)
        started = time.monotonic()
        result = answer(mcp.call_tool("layout", {"artifact": "slides"}))
        assert time.monotonic() - started < 5
        assert result["errors"] is None
        assert "Chrome or Edge is not installed" in result["unchecked"]
    finally:
        binding.stop()


def test_unknown_arguments_are_refused_and_schemas_are_compact(tmp_path: Path) -> None:
    from mcp.server.fastmcp.exceptions import ToolError

    from html_mcp_web.mcp_server import create_server

    mcp = create_server(ProjectBinding(tmp_path))
    with pytest.raises(ToolError) as error:
        asyncio.run(mcp.call_tool("image", {"artifact": "slides", "no_such": 1}))
    assert str(error.value).startswith("image does not take no_such. It takes: artifact, ")
    # FastMCP adds a title to every schema and a null default to every optional field.
    schemas = json.dumps([tool.inputSchema for tool in asyncio.run(mcp.list_tools())])
    assert '"title"' not in schemas and '"default": null' not in schemas


def test_new_never_hands_the_agent_a_thread_it_opened_until_the_reviewer_writes() -> None:
    from html_mcp_web.mcp_contract import new_requests

    opened = {"id": "c-1", "status": "open", "updated": "2026-11-03T10:00:00+00:00", "anchor": {"kind": "artifact"},
              "thread": [{"author": "agent", "at": "2026-11-03T10:00:00+00:00", "text": "agent note"}]}
    assert new_requests([opened], None) == ([], None)
    answered = {**opened, "thread": [*opened["thread"],
                                     {"author": "human", "at": "2026-11-03T10:05:00+00:00", "text": "why?"}]}
    fresh, _ = new_requests([answered], None)
    assert [entry["text"] for entry in fresh[0]["entries"]] == ["why?"]
