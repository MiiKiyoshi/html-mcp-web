import asyncio
import re
from pathlib import Path

import pytest
import yaml
from aiohttp.test_utils import TestClient, TestServer

from html_mcp_web.config import ArtifactConfig, Config
from html_mcp_web.server import HtmlReviewServer
from html_mcp_web.space import maximal_free_regions


@pytest.fixture
async def client(tmp_path: Path):
    (tmp_path / "artifact.html").write_text(
        "<!doctype html><html><head><title>Artifact</title></head><body><p>Selected sentence.</p></body></html>",
        encoding="utf-8",
    )
    config = Config(
        artifacts={"slides": ArtifactConfig(label="Slides", layout="slides", main="artifact.html")},
        watch=["*.html"],
        config_path=tmp_path / ".html-mcp-web.yaml",
    )
    review = HtmlReviewServer(config)
    app = review.create_app()
    app.on_startup.clear()
    app.on_cleanup.clear()
    test_client = TestClient(TestServer(app))
    await test_client.start_server()
    yield test_client, review
    await test_client.close()


def text_anchor(digest: str) -> dict:
    return {
        "kind": "text",
        "quote": "Selected sentence.",
        "prefix": "",
        "suffix": "",
        "start": {"path": [1, 0, 0], "offset": 0},
        "end": {"path": [1, 0, 0], "offset": 18},
        "artifact_digest": digest,
    }


def space_snapshot() -> list[dict]:
    return [{
        "number": 1,
        "bbox": [0, 0, 1280, 720],
        "children": ["p1:0"],
        "nodes": {
            "p1:0": {
                "kind": "group",
                "element": "div.panel",
                "bbox": [100, 100, 400, 300],
                "padding": [20, 20, 20, 20],
                "children": ["p1:0.0"],
                "lines": [],
                "overflow": False,
            },
            "p1:0.0": {
                "kind": "text",
                "element": "p",
                "bbox": [120, 120, 200, 80],
                "padding": [0, 0, 0, 0],
                "children": [],
                "lines": [[120, 120, 180, 20], [120, 150, 100, 20]],
                "overflow": False,
            },
        },
    }]


def test_maximal_free_regions_never_returns_zero_area() -> None:
    regions = maximal_free_regions(
        [0, 0, 100, 100],
        [[0, 0, 100, 50], [0, 50, 50, 50]],
        clearance=0,
        min_width=0,
        min_height=0,
    )
    assert regions == [[50, 50, 50, 50]]


async def test_artifact_injects_project_base(client) -> None:
    test_client, _ = client
    response = await test_client.get("/artifacts/slides/artifact")
    assert response.status == 200
    text = await response.text()
    assert '<html data-html-mcp-layout="slides">' in text
    assert '<base href="/project/">' in text
    # A hard reload does not revalidate the iframe document, so the link carries the mtime
    assert re.search(r'<link rel="stylesheet" href="/static/artifact\.css\?v=\d+">', text)
    assert '@page { size: 13.333in 7.5in; margin: 0; }' in text


async def test_viewer_shell_includes_pages_and_comments_tabs(client) -> None:
    test_client, _ = client
    response = await test_client.get("/")
    assert response.status == 200
    text = await response.text()
    assert 'data-tab="pages"' in text
    assert 'id="pages-list"' in text
    assert 'data-tab="comments"' in text
    assert 'id="fullscreen-btn"' in text
    assert 'id="presentation-controls"' in text
    assert 'id="artifact-status"' in text
    assert 'id="artifact-comment-btn"' in text
    assert 'id="reload-btn"' not in text


def test_report_artifact_uses_portrait_a4_print_page(tmp_path: Path) -> None:
    report = tmp_path / "report.html"
    report.write_text("<!doctype html><html><head></head><body><main class=\"pages\"><section class=\"page\"></section></main></body></html>", encoding="utf-8")
    review = HtmlReviewServer(Config(
        artifacts={"report": ArtifactConfig(label="Report", layout="report", main="report.html")},
        config_path=tmp_path / ".html-mcp-web.yaml",
    ))
    artifact = review._artifact_html(review.artifacts["report"])
    assert '<html data-html-mcp-layout="report">' in artifact
    assert '@page { size: A4 portrait; margin: 0; }' in artifact


async def test_state_includes_layout_and_pending_check(client) -> None:
    test_client, review = client
    state = await (await test_client.get("/state")).json()
    assert state["config_path"] == str(review.config.config_path)
    assert state["artifacts"]["slides"]["layout"] == "slides"
    assert state["artifacts"]["slides"]["layout_check"] == {"checked_revision": None, "errors": []}


async def test_layout_result_tracks_current_revision(client) -> None:
    test_client, review = client
    response = await test_client.post(
        "/artifacts/slides/layout",
        json={
            "revision": review.artifacts["slides"].revision,
            "errors": ["page 1 exceeds the slides height"],
            "space": space_snapshot(),
        },
    )
    assert response.status == 200
    state = await response.json()
    assert state["layout_check"] == {
        "checked_revision": review.artifacts["slides"].revision,
        "errors": ["page 1 exceeds the slides height"],
    }
    assert state["space_revision"] == review.artifacts["slides"].revision
    stale = await test_client.post("/artifacts/slides/layout", json={
        "revision": review.artifacts["slides"].revision - 1,
        "errors": [],
        "space": space_snapshot(),
    })
    assert stale.status == 409


async def test_space_measurement_is_revision_scoped_and_drills_into_one_block(client) -> None:
    test_client, review = client
    revision = review.artifacts["slides"].revision
    posted = await test_client.post(
        "/artifacts/slides/layout",
        json={"revision": revision, "errors": [], "space": space_snapshot()},
    )
    assert posted.status == 200

    page = await (await test_client.get(
        f"/artifacts/slides/space?revision={revision}&page=1&clearance=10&min_width=80&min_height=80"
    )).json()
    assert page["target"] is None
    assert page["children"] == [{
        "ref": "p1:0",
        "kind": "group",
        "element": "div.panel",
        "bbox": [100.0, 100.0, 400.0, 300.0],
    }]
    assert [0.0, 0.0, 90.0, 720.0] in page["free_regions"]
    assert [510.0, 0.0, 770.0, 720.0] in page["free_regions"]

    block = await (await test_client.get(
        f"/artifacts/slides/space?revision={revision}&page=1&clearance=0&target=p1%3A0"
    )).json()
    assert block["content_bbox"] == [120.0, 120.0, 200.0, 80.0]
    assert block["edge_space"] == {"top": 20.0, "right": 180.0, "bottom": 200.0, "left": 20.0}
    assert block["children"][0]["ref"] == "p1:0.0"

    stale = await test_client.get(
        f"/artifacts/slides/space?revision={revision + 1}&page=1&clearance=0"
    )
    assert stale.status == 409


async def test_comment_and_agent_reply_round_trip(client) -> None:
    test_client, review = client
    socket = await test_client.ws_connect("/ws")
    state_message = await socket.receive_json()
    assert state_message["type"] == "state"

    response = await test_client.post(
        "/artifacts/slides/comments",
        json={"anchor": text_anchor(review.artifacts["slides"].digest()), "text": "Check this"},
    )
    assert response.status == 201
    comment = await response.json()
    event = await socket.receive_json()
    assert event["type"] == "comment_added"
    fetched = await (await test_client.get(f"/artifacts/slides/comments/{comment['id']}")).json()
    assert fetched["id"] == comment["id"]
    state = await (await test_client.get("/state")).json()
    assert state["artifacts"]["slides"]["comment_counts"] == {
        "open": 1,
        "resolved": 0,
        "dismissed": 0,
    }

    reply = await test_client.post(
        f"/artifacts/slides/comments/{comment['id']}/reply",
        json={"author": "agent", "text": "Checked", "edits": ["artifact.html"]},
    )
    assert reply.status == 200
    saved = await reply.json()
    assert saved["thread"][-1]["author"] == "agent"
    assert saved["thread"][-1]["edits"] == ["artifact.html"]
    await socket.close()


async def test_editing_a_thread_entry_rewrites_it_in_place(client) -> None:
    test_client, review = client
    response = await test_client.post(
        "/artifacts/slides/comments",
        json={"anchor": text_anchor(review.artifacts["slides"].digest()), "text": "Chek this"},
    )
    comment = await response.json()
    await test_client.post(
        f"/artifacts/slides/comments/{comment['id']}/reply",
        json={"author": "agent", "text": "Checked"},
    )

    edited = await test_client.post(
        f"/artifacts/slides/comments/{comment['id']}/edit",
        json={"index": 0, "text": "Check this"},
    )
    assert edited.status == 200
    saved = await edited.json()
    assert [entry["text"] for entry in saved["thread"]] == ["Check this", "Checked"]
    assert saved["thread"][0]["at"] == comment["thread"][0]["at"]

    foreign = await test_client.post(
        f"/artifacts/slides/comments/{comment['id']}/edit",
        json={"index": 1, "text": "not mine"},
    )
    assert foreign.status == 400
    missing = await test_client.post(
        f"/artifacts/slides/comments/{comment['id']}/edit",
        json={"index": 7, "text": "nowhere"},
    )
    assert missing.status == 400
    empty = await test_client.post(
        f"/artifacts/slides/comments/{comment['id']}/edit",
        json={"index": 0, "text": "   "},
    )
    assert empty.status == 400


async def test_resolving_reports_an_anchor_the_artifact_still_carries(client) -> None:
    test_client, review = client
    digest = review.artifacts["slides"].digest()
    untouched = await (await test_client.post(
        "/artifacts/slides/comments",
        json={"anchor": text_anchor(digest), "text": "Reword this"},
    )).json()
    whole = await (await test_client.post(
        "/artifacts/slides/comments",
        json={"anchor": {"kind": "artifact"}, "text": "General note"},
    )).json()

    response = await test_client.post("/artifacts/slides/comments/update", json={
        "comment_ids": [untouched["id"], whole["id"]],
        "status": "resolved",
        "message": "done",
    })
    payload = await response.json()
    assert untouched["id"] in payload["warning"]
    assert whole["id"] not in payload["warning"]

    # Once the quoted sentence is actually gone, the same close says nothing.
    (review.project_dir / "artifact.html").write_text(
        "<!doctype html><html><head><title>Artifact</title></head><body><p>Rewritten line.</p></body></html>",
        encoding="utf-8",
    )
    edited = await (await test_client.post(
        "/artifacts/slides/comments",
        json={"anchor": text_anchor(digest), "text": "Reword this too"},
    )).json()
    quiet = await (await test_client.post("/artifacts/slides/comments/update", json={
        "comment_ids": [edited["id"]],
        "status": "resolved",
        "message": "done",
    })).json()
    assert "warning" not in quiet


async def test_replying_never_reports_the_anchor(client) -> None:
    test_client, review = client
    comment = await (await test_client.post(
        "/artifacts/slides/comments",
        json={"anchor": text_anchor(review.artifacts["slides"].digest()), "text": "Question"},
    )).json()

    payload = await (await test_client.post("/artifacts/slides/comments/update", json={
        "comment_ids": [comment["id"]],
        "message": "Answering without touching the text",
    })).json()

    assert "warning" not in payload


def test_template_build_uses_common_build_entrypoint(tmp_path: Path) -> None:
    template = tmp_path / "template"
    template.mkdir()
    builder = template / "build.py"
    builder.write_text(
        "from pathlib import Path\nimport sys\nPath(sys.argv[2]).write_text(Path(sys.argv[1]).read_text())\n",
        encoding="utf-8",
    )
    content = tmp_path / "content.html"
    content.write_text("<p>artifact</p>", encoding="utf-8")
    (tmp_path / "artifact.html").write_text("<p>old</p>", encoding="utf-8")
    config = Config(
        artifacts={"report": ArtifactConfig(
            label="Report", layout="report", main="artifact.html", template="test", content="content.html")},
        config_path=tmp_path / ".html-mcp-web.yaml",
    )
    review = HtmlReviewServer(config)
    review.artifacts["report"].template_dir = template

    review.artifacts["report"].build()

    assert review.artifacts["report"].build_error is None
    assert (tmp_path / "artifact.html").read_text(encoding="utf-8") == "<p>artifact</p>"


async def test_control_data_is_not_served(client) -> None:
    test_client, _ = client
    response = await test_client.get("/project/.html-mcp-web/comments.json")
    assert response.status == 404


async def test_config_change_adds_artifact_and_invalid_config_keeps_current_state(tmp_path: Path) -> None:
    for name in ("slides.html", "slides-v2.html", "report.html"):
        (tmp_path / name).write_text(
            '<!doctype html><html><body><main class="pages"><section class="page"></section></main></body></html>',
            encoding="utf-8",
        )
    config_path = tmp_path / ".html-mcp-web.yaml"
    initial = {
        "artifacts": {"slides": {"label": "Slides", "layout": "slides", "main": "slides.html"}},
        "port": 8765,
    }
    config_path.write_text(yaml.safe_dump(initial, sort_keys=False), encoding="utf-8")
    review = HtmlReviewServer(Config.from_dict(initial, config_path=config_path))
    app = review.create_app()
    app.on_startup.clear()
    app.on_cleanup.clear()
    test_client = TestClient(TestServer(app))
    await test_client.start_server()
    try:
        updated = {
            "artifacts": {
                **initial["artifacts"],
                "report": {"label": "Report", "layout": "report", "main": "report.html"},
            },
            "port": 8765,
        }
        config_path.write_text(yaml.safe_dump(updated, sort_keys=False), encoding="utf-8")
        await review.on_project_change(str(config_path))
        state = review.project_state()
        assert list(state["artifacts"]) == ["slides", "report"]
        assert state["artifacts"]["slides"]["revision"] == 1

        updated["artifacts"]["slides"]["main"] = "slides-v2.html"
        config_path.write_text(yaml.safe_dump(updated, sort_keys=False), encoding="utf-8")
        await review.on_project_change(str(config_path))
        changed = review.project_state()
        assert changed["artifacts"]["slides"]["main_file"] == "slides-v2.html"
        assert changed["artifacts"]["slides"]["revision"] == 2

        config_path.write_text("artifacts: {}\nport: 8765\n", encoding="utf-8")
        await review.on_project_change(str(config_path))
        current = await (await test_client.get("/state")).json()
        assert list(current["artifacts"]) == ["slides", "report"]

        config_path.write_text("artifacts: [\n", encoding="utf-8")
        await review.on_project_change(str(config_path))
        malformed = await (await test_client.get("/state")).json()
        assert list(malformed["artifacts"]) == ["slides", "report"]
    finally:
        await test_client.close()


async def test_artifact_content_change_does_not_invalidate_sibling(tmp_path: Path) -> None:
    for name in ("slides.html", "report.html", "report-content.html"):
        (tmp_path / name).write_text("<p>artifact</p>", encoding="utf-8")
    config = Config.from_dict({"artifacts": {
        "slides": {"label": "Slides", "layout": "slides", "main": "slides.html"},
        "report": {
            "label": "Report", "layout": "report", "main": "report.html",
            "template": "neutral-report", "content": "report-content.html",
        },
    }}, config_path=tmp_path / ".html-mcp-web.yaml")
    review = HtmlReviewServer(config)
    review.artifacts["report"].build = lambda: None

    await review.on_project_change(str(tmp_path / "report-content.html"))

    assert review.artifacts["slides"].revision == 1
    assert review.artifacts["report"].revision == 2

    review.generated_paths.add((tmp_path / "report.html").resolve())
    await review.on_project_change(str(tmp_path / "report.html"))
    assert review.artifacts["report"].revision == 2


def test_watcher_skips_ignored_top_level_directories(tmp_path):
    from html_mcp_web.watcher import Watcher

    (tmp_path / "docs").mkdir()
    (tmp_path / "baselines" / "run1").mkdir(parents=True)
    (tmp_path / ".html-mcp-web").mkdir()
    scheduled = []

    class FakeObserver:
        def schedule(self, handler, path, recursive):
            scheduled.append((Path(path).name, recursive))

        def start(self):
            pass

    async def on_change(path):
        pass

    watcher = Watcher(tmp_path, ["*.html"], ["baselines"], on_change)
    import html_mcp_web.watcher as module
    original = module.Observer
    module.Observer = FakeObserver
    try:
        watcher.start(asyncio.new_event_loop())
    finally:
        module.Observer = original
    assert scheduled == [(tmp_path.name, False), ("docs", True)]
