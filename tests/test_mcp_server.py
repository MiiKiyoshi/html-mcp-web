import asyncio
import json
import os
import shutil
import socket
import select
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from html_mcp_web import config as config_module
from html_mcp_web.config import load_config
from html_mcp_web.mcp_client import CLI, INIT_GUIDE, ProjectBinding
from html_mcp_web.mcp_contract import agent_comment, agent_comment_summary, revision_of, short_time
from html_mcp_web.mcp_server import create_server
from html_mcp_web.project_server import SharedProjectServer


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
        "artifacts": {"slides": {"label": "Slides", "layout": "slides", "main": "slides.html"}},
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
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
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
                "layout",
                "listen",
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
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
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
        # The setup guide's path is as long as the install location; the rest is bounded.
        assert len(mcp.instructions) - len(str(INIT_GUIDE)) < 550
        for needed in ("read_comments(new=True)", "guide()", "layout()", "image()", "write_comments",
                       "listen()", "init.md"):
            assert needed in mcp.instructions, needed
        for needed in ("asks to listen", "do not poll", "duplicate"):
            assert needed in mcp.instructions.lower(), needed
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
            "layout",
            "listen",
        ]
        assert schemas["guide"]["required"] == ["artifact"]
        assert schemas["read_comments"]["required"] == ["artifact"]
        assert schemas["write_comments"]["required"] == ["artifact", "action"]
        assert schemas["image"]["required"] == ["artifact", "page"]
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
        guided = answer(mcp.call_tool("guide", {"artifact": "slides"}))
        assert guided["edit_file"] == str(tmp_path / "slides.html")
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
        guided = answer(mcp.call_tool("guide", {"artifact": "slides"}))
        assert guided["edit_file"] == str(tmp_path / "slides.html")
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


def test_clients_with_same_config_share_server_and_follower_takes_over(tmp_path: Path) -> None:
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
        guided = answer(mcp.call_tool("guide", {"artifact": "slides"}))
        assert guided["edit_file"] == str(tmp_path / "slides.html")

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

        revision = revision_now()
        with urllib.request.urlopen(f"{base}/state", timeout=3) as response:
            served = json.loads(response.read().decode("utf-8"))["static"]
        post_json(f"{base}/artifacts/slides/layout", {
            "revision": revision,
            "static": served,
            "errors": [],
            "space": space_snapshot(),
        })
        measured = answer(mcp.call_tool("layout", {"artifact": "slides", "page": 1, "clearance": 12}))
        assert measured["errors"] == [] and "note" not in measured
        assert measured["children"][0]["ref"] == "p1:0"
        assert measured["clearance"] == 12

        # A thread's status is the reviewer's, from the page: the server refuses a resolve
        # from an agent, and the tool that only reopened is gone with it.
        post_json(f"http://127.0.0.1:{binding._shared.port}/artifacts/slides/comments/update", {
            "comment_ids": [created["id"]], "status": "resolved", "author": "human",
        })
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
        "artifacts": {"slides": {"label": "Slides", "layout": "slides", "main": "slides.html"}},
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
        post_json(f"{base}/artifacts/slides/comments/update",
                  {"comment_ids": [answered["id"]], "status": "resolved", "author": "human"})
        assert read_new(since=follow["from"])["comments"][0]["id"] == asked["id"]
        assert len(read_new(since=follow["from"])["comments"]) == 1
        with pytest.raises(Exception, match="takes no ids"):
            asyncio.run(mcp.call_tool("read_comments", {"artifact": "slides", "new": True, "ids": [asked["id"]]}))
    finally:
        binding.stop()


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_image_save_writes_a_png_and_returns_its_path(tmp_path: Path) -> None:
    # save exists so a page can be handed to the user without the image entering the
    # transcript; the tool returns a path, not pixels.
    project(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        content = asyncio.run(mcp.call_tool(
            "image", {"artifact": "slides", "page": 1, "save": True}))
        saved = json.loads(content[0].text)
        target = Path(saved["path"])
        assert target == tmp_path / ".html-mcp-web" / "renders" / "slides-p1.png"
        assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert saved["bytes"] == target.stat().st_size
        with pytest.raises(Exception, match="inside the project"):
            asyncio.run(mcp.call_tool(
                "image", {"artifact": "slides", "page": 1, "save": True, "out": "../escape.png"}))
    finally:
        binding.stop()


def test_the_lock_names_its_holder(tmp_path: Path) -> None:
    """A lock held by a process that serves nothing used to say only that it was held,
    and finding the holder was a by-hand dig through /proc. The holder writes its pid
    into the file, and the refusal names it with the way out."""
    from html_mcp_web.project_server import SharedProjectServer

    config = project(tmp_path)
    lock_path = tmp_path / ".html-mcp-web" / "server.lock"
    shared = SharedProjectServer(load_config(config.config_path))
    try:
        shared.ensure()
        assert f"pid {os.getpid()}, port {config.port}" == lock_path.read_text()
    finally:
        shared.stop()

    # Another process holds the lock and serves nothing, the way a wedged session does.
    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import fcntl, sys, time\n"
         "handle = open(sys.argv[1], 'a+')\n"
         "fcntl.flock(handle.fileno(), fcntl.LOCK_EX)\n"
         "handle.truncate(0); handle.seek(0)\n"
         "handle.write('pid 424242, port 65000'); handle.flush()\n"
         "print('holding', flush=True)\n"
         "time.sleep(60)\n",
         str(lock_path)],
        stdout=subprocess.PIPE, text=True)
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
        [sys.executable, "-c",
         "import fcntl, sys, time\n"
         "handle = open(sys.argv[1], 'a+')\n"
         "fcntl.flock(handle.fileno(), fcntl.LOCK_EX)\n"
         "print('holding', flush=True)\n"
         "time.sleep(1)\n",
         str(lock_path)],
        stdout=subprocess.PIPE, text=True)
    try:
        assert dying.stdout.readline().strip() == "holding"
        taker = SharedProjectServer(load_config(config.config_path))
        taker.ensure()   # the holder dies about a second in; the poll claims the lock
        try:
            assert f"pid {os.getpid()}" in lock_path.read_text()
        finally:
            taker.stop()
    finally:
        dying.wait(timeout=10)


def test_guide_names_the_file_to_edit_and_what_to_read(tmp_path: Path) -> None:
    """Paths only: a document is read when it is needed, not carried in the answer."""
    project(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        guided = answer(mcp.call_tool("guide", {"artifact": "slides"}))
        assert set(guided) == {"edit_file", "read"}
        assert guided["edit_file"] == str(tmp_path / "slides.html")
        assert [Path(path).name for path in guided["read"]] == ["README.md", "COMPONENTS.md"]
        assert all(Path(path).is_file() for path in guided["read"])
        assert "reader-facing unit" not in json.dumps(guided, ensure_ascii=False)
        with pytest.raises(Exception, match="unknown artifact"):
            asyncio.run(mcp.call_tool("guide", {"artifact": "report"}))
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
        guided = answer(mcp.call_tool("guide", {"artifact": "slides"}))
        # The content file is what a templated artifact is written in; the main file is built.
        assert guided["edit_file"] == str(tmp_path / "content.html")
        notes = Path(guided["read"][-1])
        assert notes.parent.name == "neutral-slides" and notes.name == "README.md"
        for path in guided["read"]:
            assert Path(path).read_text(encoding="utf-8") not in json.dumps(guided)
    finally:
        binding.stop()





def test_layout_reports_the_revisions_errors_and_a_pages_detail(tmp_path: Path) -> None:
    config = project(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        binding.require_client()
        with urllib.request.urlopen(f"http://127.0.0.1:{config.port}/state") as response:
            state = json.loads(response.read().decode("utf-8"))
        revision = state["artifacts"]["slides"]["revision"]
        post_json(f"http://127.0.0.1:{config.port}/artifacts/slides/layout", {
            "revision": revision,
            "static": state["static"],
            "errors": [
                "page 1 exceeds the slides height at p1:0",
                "page 2 exceeds the slides height at p2:0",
            ],
            "space": space_snapshot(),
        })

        whole = answer(mcp.call_tool("layout", {"artifact": "slides"}))
        assert whole["revision"] == revision
        assert len(whole["errors"]) == 2
        # The advice on fixing them comes with errors, not with every session.
        assert "smallest size or spacing change" in whole["note"]
        detailed = answer(mcp.call_tool("layout", {"artifact": "slides", "page": 1}))
        assert detailed["errors"] == ["page 1 exceeds the slides height at p1:0"]
        assert detailed["children"][0]["ref"] == "p1:0"
        assert "page 2" not in json.dumps(detailed)
        with pytest.raises(Exception, match="target needs page"):
            asyncio.run(mcp.call_tool("layout", {"artifact": "slides", "target": "p1:0"}))
    finally:
        binding.stop()


def test_guide_lists_the_configured_guideline_by_path(
    tmp_path: Path, monkeypatch,
) -> None:
    user_config = tmp_path / "user-config"
    guideline_path = user_config / "guidelines" / "eda-domain-meeting" / "GUIDELINE.md"
    guideline_path.parent.mkdir(parents=True)
    guideline_text = "# EDA domain meeting\n\nNever inline this marker in discovery.\n"
    guideline_path.write_text(guideline_text, encoding="utf-8")
    monkeypatch.setattr(config_module, "USER_CONFIG_DIR", user_config)
    config = project(tmp_path)
    data = yaml.safe_load(config.config_path.read_text(encoding="utf-8"))
    data["guideline"] = "eda-domain-meeting"
    config.config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        guided = answer(mcp.call_tool("guide", {"artifact": "slides"}))
        assert guided["read"][-1] == str(guideline_path)
        assert "Never inline this marker" not in json.dumps(guided)
        # Paths are the whole of it: no resources beside them to keep in step.
        assert asyncio.run(mcp.list_resources()) == []
    finally:
        binding.stop()


@pytest.mark.parametrize("codex", [False, True])
def test_listen(tmp_path: Path, monkeypatch, codex) -> None:
    # The tool returns at once with a script for the harness to watch in the background;
    # blocking here would freeze the agent, which is what the button exists to avoid.
    project(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        context = SimpleNamespace(session=SimpleNamespace(client_params=SimpleNamespace(
            clientInfo=SimpleNamespace(name="claude-code"))))
        monkeypatch.setattr(mcp, "get_context", lambda: context)
        told = answer(mcp.call_tool("listen", {}))
        script = Path(told["script"])
        assert script == tmp_path / ".html-mcp-web" / "wait-review.sh"
        assert script.stat().st_mode & 0o111
        body = script.read_text(encoding="utf-8")
        # The script carries no watermark: the server keeps consumption, so a press made
        # before this call is picked up at once and a restarted script parks again. It
        # acks after printing, so a press is only marked consumed once its line was
        # delivered, and it never exits on an empty 204 or a curl timeout.
        assert "since" not in body
        assert f":{binding._shared.port}/wait-review\"" in body
        assert f":{binding._shared.port}/wait-review/ack?upto=$press" in body
        assert body.index('deliver "$out"') < body.index("/wait-review/ack")
        assert "[gone]" in body and "timeout" not in body
        assert "Monitor" in told["how"] and "persistent=true" in told["how"]
        assert "write_stdin" not in told["how"]
        for name in ("codex-mcp-client", "other-client"):
            context.session.client_params.clientInfo.name = name
            selected = answer(mcp.call_tool("listen", {}))
            assert "Monitor" not in selected["how"]
            assert ("codex queue" in selected["how"]) == (name == "codex-mcp-client")
            assert ('sandbox_permissions="require_escalated"' in selected["how"]) == (name == "codex-mcp-client")
        tool = next(t for t in asyncio.run(mcp.list_tools()) if t.name == "listen")
        assert "ctx" not in tool.inputSchema["properties"]
        # One monitor serves the whole session: a press is printed, not exited on.
        assert "exit 0" not in body

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
            stub = tmp_path / "codex"
            stub.write_text("#!/bin/sh\n"
                            '[ "$1" = queue ] && [ "$2" = --thread ] && [ "$3" = test-thread ] && [ "$4" = --message ] || exit 2\n'
                            '[ -f "$0.ready" ] || { touch "$0.failed"; exit 1; }\n'
                            'printf "%s\\n" "$5" | tail -n +2\n')
            stub.chmod(0o755)
            monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
            args = ["--codex", "test-thread"]
        press()
        waiter = subprocess.Popen(["/bin/sh", str(script), *args],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            if codex:
                deadline = time.monotonic() + 5
                while not (tmp_path / "codex.failed").exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                assert (tmp_path / "codex.failed").exists()
                assert review()["consumed"] == 0
                (tmp_path / "codex.ready").touch()
            pending = b""

            def line(timeout):
                # Read raw and keep the remainder: two lines written together left the
                # second in a buffered reader, where select on the pipe could not see it.
                nonlocal pending
                deadline = time.monotonic() + timeout
                while b"\n" not in pending:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return ""
                    ready, _, _ = select.select([waiter.stdout], [], [], remaining)
                    if not ready:
                        return ""
                    chunk = os.read(waiter.stdout.fileno(), 4096)
                    if not chunk:
                        return ""
                    pending += chunk
                head, pending = pending.split(b"\n", 1)
                return head.decode("utf-8")

            assert line(15).startswith("[review]")
            time.sleep(1.0)
            assert waiter.poll() is None
            assert review() == {"calls": 1, "consumed": 1, "waiters": 1}    # parked again
            assert line(1.5) == ""                                           # and silent
            press()
            assert line(15).startswith("[review]")
            time.sleep(1.0)
            assert waiter.poll() is None
            assert review() == {"calls": 2, "consumed": 2, "waiters": 1}

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


def test_read_comments_offers_the_reference_view(tmp_path: Path) -> None:
    """A thread the reviewer keeps as reference is listed apart from open and resolved,
    and the agent asks for that view by name."""
    mcp = create_server(ProjectBinding(tmp_path))
    schemas = {tool.name: tool.inputSchema for tool in asyncio.run(mcp.list_tools())}
    assert schemas["read_comments"]["properties"]["status"]["enum"] == ["open", "resolved", "reference", "all"]


def test_write_comments_takes_edits_of_the_agents_own_entries(tmp_path: Path) -> None:
    mcp = create_server(ProjectBinding(tmp_path))
    schemas = {tool.name: tool.inputSchema for tool in asyncio.run(mcp.list_tools())}
    assert set(schemas["write_comments"]["properties"]) == {
        "artifact", "action", "text", "edited_files", "draft"}
    assert "'c-1a2b3c4d/e-5e6f7a8b@<rev>: '" in json.dumps(schemas["write_comments"]["properties"]["text"])
