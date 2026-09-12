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
from html_mcp_web.mcp_client import ProjectBinding
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
            await session.initialize()
            tools = await session.list_tools()
            assert [tool.name for tool in tools.tools] == [
                "inspect",
                "list_comments",
                "read_comments",
                "reply_comments",
                "render_page",
                "export_pptx",
                "measure_space",
                "wait_review",
            ]
            inspected = await session.call_tool("inspect", {})
            assert inspected.isError is False
            assert inspected.structuredContent["setup_required"]["project_dir"] == str(tmp_path)
            config = project(tmp_path)
            connected = await session.call_tool("inspect", {})
            assert connected.isError is False
            assert connected.structuredContent["config_path"] == str(config.config_path)
            assert connected.structuredContent["review_url"] == f"http://127.0.0.1:{config.port}"
            compact = await session.call_tool("inspect", {"artifact": "slides"})
            assert set(compact.structuredContent) == {"artifacts"}


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
        assert len(mcp.instructions) < 1000
        for needed in ("wait_review()", "docs=True", "configured guideline", "resource_uri"):
            assert needed in mcp.instructions, needed
        for needed in ("new connection", "do not poll", "duplicate"):
            assert needed in mcp.instructions.lower(), needed
        for gone in (
            "templates/README.md",
            "exactly once",
            "Monitor",
            "tells you to wait",
            "reader-facing unit",
        ):
            assert gone not in mcp.instructions, gone
        assert "no arguments first" in mcp.instructions
        assert "Pass page" in mcp.instructions
        tools = asyncio.run(mcp.list_tools())
        schemas = {tool.name: tool.inputSchema for tool in tools}
        assert list(schemas) == [
            "inspect",
            "list_comments",
            "read_comments",
            "reply_comments",
            "render_page",
            "export_pptx",
            "measure_space",
            "wait_review",
        ]
        assert schemas["read_comments"]["required"] == ["artifact", "comment_ids"]
        assert schemas["reply_comments"]["required"] == ["artifact", "replies_text"]
        assert schemas["reply_comments"]["properties"]["replies_text"]["type"] == "string"
        assert set(schemas["inspect"]["properties"]) == {"artifact", "docs", "page"}
        assert schemas["inspect"]["properties"]["page"]["anyOf"][0]["minimum"] == 1
        assert schemas["render_page"]["required"] == ["artifact", "page"]
        assert schemas["render_page"]["properties"]["page"]["minimum"] == 1
        assert schemas["render_page"]["properties"]["dpi"]["minimum"] == 36
        assert schemas["render_page"]["properties"]["dpi"]["maximum"] == 300
        assert set(schemas["render_page"]["properties"]) >= {"save", "out"}
        # revision is optional: left out, the server measures its current one, so a lone
        # measure_space needs no inspect round first just to learn the number.
        assert schemas["measure_space"]["required"] == ["artifact", "page", "clearance"]

        _, setup = asyncio.run(mcp.call_tool("inspect", {}))
        assert setup == {
            "setup_required": {
                "project_dir": str(tmp_path),
                "config_path": str(tmp_path / ".html-mcp-web.yaml"),
                "next_action": (
                    "Run html-mcp-web init in project_dir with the requested layout, main file, and port "
                    "(add --template and --content for a templated deck), then call inspect() again."
                ),
            }
        }

        config = project(tmp_path)
        _, inspected = asyncio.run(mcp.call_tool("inspect", {}))
        assert inspected["config_path"] == str(config.config_path)
        assert inspected["project_dir"] == str(tmp_path)
        assert inspected["review_url"] == f"http://127.0.0.1:{config.port}"
        _, compact = asyncio.run(mcp.call_tool("inspect", {"artifact": "slides"}))
        assert set(compact) == {"artifacts"}
    finally:
        binding.stop()


def test_binding_retries_after_invalid_config_is_fixed(tmp_path: Path) -> None:
    config_path = tmp_path / ".html-mcp-web.yaml"
    config_path.write_text("artifacts: [\n", encoding="utf-8")
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        _, setup_error = asyncio.run(mcp.call_tool("inspect", {}))
        assert setup_error["setup_error"]["config_path"] == str(config_path)
        assert "while parsing a flow node" in setup_error["setup_error"]["message"]
        config_path.unlink()
        config = project(tmp_path)
        _, inspected = asyncio.run(mcp.call_tool("inspect", {}))
        assert inspected["config_path"] == str(config.config_path)
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
        _, discovered = asyncio.run(mcp.call_tool("inspect", {}))
        assert discovered["artifacts"]["slides"]["edit_file"] == str(tmp_path / "slides.html")

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
        _, inspected = asyncio.run(mcp.call_tool("inspect", {"artifact": "slides"}))
        artifact = inspected["artifacts"]["slides"]
        assert set(artifact) == {"revision", "layout_error_count", "comment_counts"}
        assert artifact["comment_counts"]["open"] == 2
        assert "comments" not in artifact
        assert "artifact_digest" not in artifact

        _, listed = asyncio.run(mcp.call_tool("list_comments", {"artifact": "slides"}))
        assert len(listed["comments"]) == 2
        assert listed["comments"][0] == {
            "id": created["id"],
            "status": "open",
            "anchor": {"kind": "artifact"},
            "request": "Reply without resolving",
            "thread_entries": 1,
            "last_human_at": created["thread"][0]["at"],
        }
        assert "quote" not in json.dumps(listed)
        first_seen = listed["comments"][0]["last_human_at"]
        _, later = asyncio.run(mcp.call_tool("list_comments", {"artifact": "slides", "since": first_seen}))
        assert [comment["id"] for comment in later["comments"]] == [text_comment["id"]]
        _, unanswered = asyncio.run(mcp.call_tool("list_comments", {"artifact": "slides", "unanswered": True}))
        assert len(unanswered["comments"]) == 2

        _, selected = asyncio.run(mcp.call_tool("read_comments", {
            "artifact": "slides",
            "comment_ids": [text_comment["id"]],
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
        assert "updated" not in stripped

        _, replied = asyncio.run(mcp.call_tool("reply_comments", {
            "artifact": "slides",
            "replies_text": f"{created['id']}: Changed the wording",
            "edited_files": ["slides.html"],
        }))
        assert replied["updated"][0]["status"] == "open"
        assert set(replied["updated"][0]) == {"id", "status", "updated"}

        _, inspect_after_reply = asyncio.run(mcp.call_tool("inspect", {"artifact": "slides"}))
        assert inspect_after_reply == inspected
        # The agent's reply leaves the thread answered; a later human entry reopens it.
        _, unanswered = asyncio.run(mcp.call_tool("list_comments", {"artifact": "slides", "unanswered": True}))
        assert [comment["id"] for comment in unanswered["comments"]] == [text_comment["id"]]
        newest_seen = listed["comments"][1]["last_human_at"]
        _, since_all = asyncio.run(mcp.call_tool("list_comments", {"artifact": "slides", "since": newest_seen}))
        assert since_all["comments"] == []

        _, replied_read = asyncio.run(mcp.call_tool("read_comments", {
            "artifact": "slides",
            "comment_ids": [created["id"]],
        }))
        replied_comment = replied_read["comments"][0]
        assert replied_comment["thread"][-1]["edited_files"] == ["slides.html"]
        assert "edits" not in replied_comment["thread"][-1]
        post_json(f"{base}/artifacts/slides/comments/{created['id']}/reply", {"text": "Still wrong"})
        _, unanswered = asyncio.run(mcp.call_tool("list_comments", {"artifact": "slides", "unanswered": True, "since": newest_seen}))
        assert [comment["id"] for comment in unanswered["comments"]] == [created["id"]]
        assert unanswered["comments"][0]["thread_entries"] == 3
        assert unanswered["comments"][0]["request"] == "Still wrong"

        revision = inspected["artifacts"]["slides"]["revision"]
        with urllib.request.urlopen(f"{base}/state", timeout=3) as response:
            served = json.loads(response.read().decode("utf-8"))["static"]
        post_json(f"{base}/artifacts/slides/layout", {
            "revision": revision,
            "static": served,
            "errors": [],
            "space": space_snapshot(),
        })
        _, measured = asyncio.run(mcp.call_tool("measure_space", {
            "artifact": "slides",
            "page": 1,
            "revision": revision,
            "clearance": 12,
        }))
        assert measured["children"][0]["ref"] == "p1:0"
        assert measured["clearance"] == 12

        # A thread's status is the reviewer's, from the page: the server refuses a resolve
        # from an agent, and the tool that only reopened is gone with it.
        post_json(f"http://127.0.0.1:{binding._shared.port}/artifacts/slides/comments/update", {
            "comment_ids": [created["id"]], "status": "resolved", "author": "human",
        })
        _, closed_read = asyncio.run(mcp.call_tool("read_comments", {
            "artifact": "slides",
            "comment_ids": [created["id"]],
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


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_render_page_save_writes_a_png_and_returns_its_path(tmp_path: Path) -> None:
    # save exists so a page can be handed to the user without the image entering the
    # transcript; the tool returns a path, not pixels.
    project(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        content = asyncio.run(mcp.call_tool(
            "render_page", {"artifact": "slides", "page": 1, "save": True}))
        saved = json.loads(content[0].text)
        target = Path(saved["path"])
        assert target == tmp_path / ".html-mcp-web" / "renders" / "slides-p1.png"
        assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert saved["bytes"] == target.stat().st_size
        with pytest.raises(Exception, match="inside the project"):
            asyncio.run(mcp.call_tool(
                "render_page", {"artifact": "slides", "page": 1, "save": True, "out": "../escape.png"}))
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


def test_the_working_guide_rides_on_the_discovery_call_only(tmp_path: Path) -> None:
    """The rules a client's truncation used to swallow live here instead, on the call every
    agent starts with. A later inspect(artifact) is made many times and carries none of it."""
    project(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        _, discovered = asyncio.run(mcp.call_tool("inspect", {}))
        guide = discovered["guide"]
        assert set(guide) == {
            "layout_check", "measure_space", "render_page", "reader_unit", "review", "images",
            "watching", "editing",
        }
        assert guide["reader_unit"] == (
            "Before editing a reader-facing unit, fix what the reader knows, what they must learn, the "
            "visible structure, and what is excluded. Adjacent comparison and result units reuse the same "
            "keys, labels, and order. A preliminary unit contains only the prerequisite; preserve and "
            "annotate source examples when they are the subject. After two related comprehension failures, "
            "rebuild the unit instead of patching sentences."
        )
        assert "wait_review()" in guide["review"]
        # Told to wait, an agent answered that it was waiting and started nothing; the
        # words have to be named as the waiter.
        assert "tells you to wait" in guide["review"]
        assert "Pass page" in guide["layout_check"]
        assert "edit_file" in guide["editing"]
        assert "min_no_wrap_width" in guide["measure_space"]
        assert "inotify watch limit reached" in guide["watching"]
        assert "base64" in guide["images"]

        _, one = asyncio.run(mcp.call_tool("inspect", {"artifact": "slides"}))
        assert "guide" not in one
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


def test_inspect_adds_the_content_format_when_asked(tmp_path: Path) -> None:
    """A client without file tools could not follow a host path in the instructions, and
    the path leaked the contract out of the tools; the format rides on inspect now, when
    asked, rather than on a tool of its own."""
    (tmp_path / "content.html").write_text(
        '<section class="page"><h1>One</h1></section>', encoding="utf-8")
    (tmp_path / ".html-mcp-web.yaml").write_text(yaml.safe_dump({
        "artifacts": {"slides": {"label": "Slides", "layout": "slides", "main": "slides.html",
                                 "template": "neutral-slides", "content": "content.html"}},
        "port": available_port(),
    }, sort_keys=False), encoding="utf-8")
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        _, plain = asyncio.run(mcp.call_tool("inspect", {"artifact": "slides"}))
        assert "docs" not in plain                    # not on every inspect
        _, inspected = asyncio.run(mcp.call_tool("inspect", {"artifact": "slides", "docs": True}))
        docs = inspected["docs"]
        assert docs["template"] == "neutral-slides"
        assert "section" in docs["readme"]           # the shared content format
        assert docs["skin_readme"] is None or isinstance(docs["skin_readme"], str)
    finally:
        binding.stop()


def test_inspect_has_no_docs_for_a_plain_artifact(tmp_path: Path) -> None:
    project(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        _, inspected = asyncio.run(mcp.call_tool("inspect", {"artifact": "slides", "docs": True}))
        assert inspected["docs"] == {"template": None, "readme": None, "skin_readme": None}
    finally:
        binding.stop()


def test_inspect_returns_only_requested_page_layout_detail(tmp_path: Path) -> None:
    config = project(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        _, initial = asyncio.run(mcp.call_tool("inspect", {"artifact": "slides"}))
        revision = initial["artifacts"]["slides"]["revision"]
        with urllib.request.urlopen(f"http://127.0.0.1:{config.port}/state") as response:
            static = json.loads(response.read().decode("utf-8"))["static"]
        post_json(f"http://127.0.0.1:{config.port}/artifacts/slides/layout", {
            "revision": revision,
            "static": static,
            "errors": [
                "page 1 exceeds the slides height at p1:0",
                "page 2 exceeds the slides height at p2:0",
            ],
            "space": space_snapshot(),
        })

        _, compact = asyncio.run(mcp.call_tool("inspect", {"artifact": "slides"}))
        assert compact["artifacts"]["slides"] == {
            "revision": revision,
            "layout_error_count": 2,
            "comment_counts": {"open": 0, "resolved": 0},
        }
        _, detailed = asyncio.run(mcp.call_tool("inspect", {"artifact": "slides", "page": 1}))
        page = detailed["artifacts"]["slides"]["page"]
        assert page["number"] == 1
        assert page["errors"] == ["page 1 exceeds the slides height at p1:0"]
        assert page["room"]
        assert "page 2" not in json.dumps(detailed)
    finally:
        binding.stop()


def test_guideline_discovery_returns_a_reference_and_resource_not_inline_text(
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
        _, discovered = asyncio.run(mcp.call_tool("inspect", {}))
        assert discovered["guideline"] == {
            "name": "eda-domain-meeting",
            "path": str(guideline_path),
            "resource_uri": "html-mcp://guideline/configured",
        }
        assert "Never inline this marker" not in json.dumps(discovered)
        resources = asyncio.run(mcp.list_resources())
        assert [str(resource.uri) for resource in resources] == ["html-mcp://guideline/configured"]
        contents = list(asyncio.run(mcp.read_resource("html-mcp://guideline/configured")))
        assert contents[0].content == guideline_text
    finally:
        binding.stop()


@pytest.mark.parametrize("codex", [False, True])
def test_wait_review(tmp_path: Path, monkeypatch, codex) -> None:
    # The tool returns at once with a script for the harness to watch in the background;
    # blocking here would freeze the agent, which is what the button exists to avoid.
    project(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        context = SimpleNamespace(session=SimpleNamespace(client_params=SimpleNamespace(
            clientInfo=SimpleNamespace(name="claude-code"))))
        monkeypatch.setattr(mcp, "get_context", lambda: context)
        unstructured, told = asyncio.run(mcp.call_tool("wait_review", {}))
        assert json.loads(unstructured[0].text) == told
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
            _, selected = asyncio.run(mcp.call_tool("wait_review", {}))
            assert "Monitor" not in selected["how"]
            assert ("codex queue" in selected["how"]) == (name == "codex-mcp-client")
            assert ('sandbox_permissions="require_escalated"' in selected["how"]) == (name == "codex-mcp-client")
        tool = next(t for t in asyncio.run(mcp.list_tools()) if t.name == "wait_review")
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
