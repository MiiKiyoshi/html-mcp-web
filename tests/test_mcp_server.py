import asyncio
import json
import shutil
import socket
import sys
import urllib.request
from pathlib import Path

import pytest
import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

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
                "set_comment_status",
                "render_page",
                "export_pptx",
                "measure_space",
                "wait_review",
            ]
            inspected = await session.call_tool("inspect", {})
            assert inspected.isError is False
            assert inspected.structuredContent["setup_required"]["project_dir"] == str(tmp_path)
            config = project(tmp_path)
            connected = await session.call_tool("inspect", {"artifact": "slides"})
            assert connected.isError is False
            assert connected.structuredContent["config_path"] == str(config.config_path)
            assert connected.structuredContent["review_url"] == f"http://127.0.0.1:{config.port}"


@pytest.mark.asyncio
async def test_stdio_mcp_serves_existing_project_at_startup(tmp_path: Path) -> None:
    config = project(tmp_path)
    server = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from html_mcp_web.cli import main_mcp; raise SystemExit(main_mcp())"],
        cwd=tmp_path,
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
        assert "reusing results while revision is unchanged" in mcp.instructions
        assert "do not embed them as base64" in mcp.instructions
        tools = asyncio.run(mcp.list_tools())
        schemas = {tool.name: tool.inputSchema for tool in tools}
        assert list(schemas) == [
            "inspect",
            "list_comments",
            "read_comments",
            "reply_comments",
            "set_comment_status",
            "render_page",
            "export_pptx",
            "measure_space",
            "wait_review",
        ]
        assert set(schemas["inspect"]["properties"]) == {"artifact"}
        assert schemas["read_comments"]["required"] == ["artifact", "comment_ids"]
        assert schemas["reply_comments"]["required"] == ["artifact", "replies"]
        assert schemas["set_comment_status"]["required"] == ["artifact", "comment_ids", "status"]
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
        _, inspected = asyncio.run(mcp.call_tool("inspect", {"artifact": "slides"}))
        assert inspected["config_path"] == str(config.config_path)
        assert inspected["project_dir"] == str(tmp_path)
        assert inspected["review_url"] == f"http://127.0.0.1:{config.port}"
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
        assert "a comment answered with words alone stays open" in mcp.instructions

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
        assert artifact["edit_file"] == str(tmp_path / "slides.html")
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
            "replies": [{"comment_id": created["id"], "message": "Changed the wording"}],
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
        post_json(f"{base}/artifacts/slides/layout", {
            "revision": revision,
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

        _, resolved = asyncio.run(mcp.call_tool("set_comment_status", {
            "artifact": "slides",
            "comment_ids": [created["id"]],
            "status": "resolved",
        }))
        assert resolved["updated"][0]["status"] == "resolved"
        _, resolved_read = asyncio.run(mcp.call_tool("read_comments", {
            "artifact": "slides",
            "comment_ids": [created["id"]],
        }))
        resolved_comment = resolved_read["comments"][0]
        assert resolved_comment["status"] == "resolved"
        assert all(entry["text"] for entry in resolved_comment["thread"])

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
    # main file is absent, so the first start fails; the lock must be freed so that fixing the
    # cause and retrying serves the project instead of blocking forever on this process's lock.
    port = available_port()
    (tmp_path / ".html-mcp-web.yaml").write_text(yaml.safe_dump({
        "artifacts": {"slides": {"label": "Slides", "layout": "slides", "main": "slides.html"}},
        "port": port,
    }, sort_keys=False), encoding="utf-8")
    shared = SharedProjectServer(load_config(tmp_path / ".html-mcp-web.yaml"))
    try:
        with pytest.raises(RuntimeError, match="failed to start"):
            shared.ensure()
        assert shared.lock_handle is None  # the lock was released, not leaked
        (tmp_path / "slides.html").write_text(
            '<!doctype html><html><body><main class="pages"><section class="page"></section></main></body></html>',
            encoding="utf-8")
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


def test_wait_review_writes_a_waiter_script_carrying_port_and_press_count(tmp_path: Path) -> None:
    # The tool returns at once with a script for the harness to watch in the background;
    # blocking here would freeze the agent, which is what the button exists to avoid.
    project(tmp_path)
    binding = ProjectBinding(tmp_path)
    try:
        mcp = create_server(binding)
        unstructured, told = asyncio.run(mcp.call_tool("wait_review", {}))
        assert json.loads(unstructured[0].text) == told
        script = Path(told["script"])
        assert script == tmp_path / ".html-mcp-web" / "wait-review.sh"
        assert script.stat().st_mode & 0o111
        body = script.read_text(encoding="utf-8")
        assert "since=0" in body                      # no press yet, so any press wakes it
        assert f":{binding._shared.port}/wait-review" in body
        assert "[gone]" in body and "[timeout]" in body
        assert "Monitor" in told["how"]
    finally:
        binding.stop()
