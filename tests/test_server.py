import asyncio
import json
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
    assert state["artifacts"]["slides"]["layout_check"] == {
        "checked_revision": None, "errors": [], "room": {}}


async def test_layout_result_is_accepted_when_the_deck_measures_past_a_megabyte(client) -> None:
    """The measurement grows with the deck. At aiohttp's default ceiling of 1MB a deck of
    a couple of dozen pages stopped being checked at all, and the page said only that it
    had not been checked yet."""
    test_client, review = client
    pages = []
    for number in range(1, 61):
        nodes = {
            f"p{number}:0.{index}": {
                "kind": "text", "element": "p", "bbox": [40, 40 + index, 900, 24],
                "padding": [0, 0, 0, 0], "children": [], "overflow": False,
                "lines": [[40, 40 + index, 880, 22]],
            }
            for index in range(120)
        }
        nodes[f"p{number}:0"] = {
            "kind": "group", "element": "div.body", "bbox": [0, 0, 1280, 720],
            "padding": [0, 0, 0, 0], "children": list(nodes), "lines": [], "overflow": False,
        }
        pages.append({"number": number, "bbox": [0, 0, 1280, 720],
                      "children": [f"p{number}:0"], "nodes": nodes})
    payload = {"revision": review.artifacts["slides"].revision, "errors": [], "space": pages}
    assert len(json.dumps(payload)) > 1024 * 1024
    response = await test_client.post("/artifacts/slides/layout", json=payload)
    assert response.status == 200
    state = await response.json()
    assert state["layout_check"]["checked_revision"] == review.artifacts["slides"].revision


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
    assert state["layout_check"]["checked_revision"] == review.artifacts["slides"].revision
    assert state["layout_check"]["errors"] == ["page 1 exceeds the slides height"]
    # The error is about fit, so the page's free rectangles come with it.
    assert [region["bbox"] for region in state["layout_check"]["room"]["1"]]
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

    # Left out, the revision means the current one; the reading is the same measurement.
    bare = await (await test_client.get("/artifacts/slides/space?page=1&clearance=0&target=p1%3A0")).json()
    assert bare["revision"] == revision
    assert bare["content_bbox"] == [120.0, 120.0, 200.0, 80.0]


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


async def test_an_edit_reported_on_an_untouched_anchor_is_noted(client) -> None:
    """An agent reports its edit in a reply with the files it touched. Where the quoted
    text is still in the artifact unchanged, the reply comes back with a note: normal when
    the fix landed elsewhere (a heading anchored over the body it asked about), and the
    one hint that the edit went to the wrong place when it was not. A reply that reports
    no edit claims nothing, and the reviewer's own close carries no check: they have just
    read the thread."""
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

    reported = await (await test_client.post("/artifacts/slides/comments/update", json={
        "comment_ids": [untouched["id"], whole["id"]],
        "message": "done",
        "edited_files": ["artifact.html"],
    })).json()
    assert untouched["id"] in reported["note"]
    assert whole["id"] not in reported["note"]

    plain = await (await test_client.post("/artifacts/slides/comments/update", json={
        "comment_ids": [untouched["id"]],
        "message": "will look",
    })).json()
    assert "note" not in plain

    # Once the quoted sentence is actually gone, the same report says nothing.
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
        "message": "done",
        "edited_files": ["artifact.html"],
    })).json()
    assert "note" not in quiet

    # A quote that survives inside a bigger phrase is not an untouched spot. The old text
    # rewritten as a superset still contains the quote, and the report noted a sentence
    # that had just been changed; the stored context around it is what tells the two apart.
    (review.project_dir / "artifact.html").write_text(
        "<!doctype html><html><head><title>Artifact</title></head><body><p>Plain sentence here.</p></body></html>",
        encoding="utf-8",
    )
    grown_anchor = {
        "kind": "text", "quote": "sentence", "prefix": "Plain ", "suffix": " here.",
        "start": {"path": [1, 0, 0], "offset": 6}, "end": {"path": [1, 0, 0], "offset": 14},
        "artifact_digest": review.artifacts["slides"].digest(),
    }
    grown = await (await test_client.post(
        "/artifacts/slides/comments",
        json={"anchor": grown_anchor, "text": "Wrap this in a sum"},
    )).json()
    (review.project_dir / "artifact.html").write_text(
        "<!doctype html><html><head><title>Artifact</title></head><body><p>Plain longer sentence here.</p></body></html>",
        encoding="utf-8",
    )
    reworded = await (await test_client.post("/artifacts/slides/comments/update", json={
        "comment_ids": [grown["id"]],
        "message": "wrapped",
        "edited_files": ["artifact.html"],
    })).json()
    assert "note" not in reworded

    # The reviewer's close carries no check of its own.
    closed = await (await test_client.post("/artifacts/slides/comments/update", json={
        "comment_ids": [untouched["id"]],
        "status": "resolved",
        "author": "human",
        "message": "read",
    })).json()
    assert "note" not in closed and "warning" not in closed

async def test_reopening_needs_no_words(client) -> None:
    """Reopening asked for a reason where resolving asks for nothing, and the reason was
    usually the status said twice. A reply is only its text, so that one still needs some."""
    test_client, review = client
    comment = await (await test_client.post(
        "/artifacts/slides/comments",
        json={"anchor": text_anchor(review.artifacts["slides"].digest()), "text": "Look again"},
    )).json()
    await test_client.post(f"/artifacts/slides/comments/{comment['id']}/resolve", json={"summary": ""})

    reopened = await (await test_client.post(
        f"/artifacts/slides/comments/{comment['id']}/reopen", json={"text": ""})).json()
    assert reopened["status"] == "open"
    assert len(reopened["thread"]) == 1          # nothing added: the status is the news

    empty_reply = await test_client.post(
        f"/artifacts/slides/comments/{comment['id']}/reply", json={"text": "   "})
    assert empty_reply.status == 400


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


def test_build_reports_what_it_wrote_and_leaves_no_staging_file(tmp_path: Path, capsys) -> None:
    """The watcher's rebuild and a by-hand one run concurrently, and a plain write let one
    build's report stat the other's just-truncated file: '0KB' over a file that was
    complete a moment later. The size reported is the size written."""
    from html_mcp_web.slides.build import build

    skin = Path(__file__).resolve().parent.parent / "templates" / "neutral-slides"
    content = tmp_path / "content.html"
    content.write_text(
        "<!doctype html><meta charset=\"utf-8\"><title>Deck</title>"
        "<body data-author=\"Author\" data-meta=\"Lab|Today\">"
        "<section data-title=\"One\"><p>Only page.</p></section></body>",
        encoding="utf-8",
    )
    out = tmp_path / "slides.html"
    build(content, out, skin)
    reported = capsys.readouterr().out
    kilobytes = int(re.search(r"(\d+)KB", reported).group(1))
    assert kilobytes == out.stat().st_size // 1024 > 0
    assert list(tmp_path.glob("*.building")) == []


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


def test_a_templated_artifact_names_its_missing_content(tmp_path: Path) -> None:
    """Right after init the content file may not exist yet; an error that named the built
    main file sent the reader looking for a build that had nothing to build from."""
    config = Config.from_dict({"artifacts": {
        "report": {
            "label": "Report", "layout": "report", "main": "report.html",
            "template": "neutral-report", "content": "report-content.html",
        },
    }}, config_path=tmp_path / ".html-mcp-web.yaml")
    review = HtmlReviewServer(config)
    error = review.project_state()["artifacts"]["report"]["error"]
    assert error.startswith("content file not found: ")
    assert "report-content.html" in error
    assert "builds" in error and "report.html" in error


def test_fit_errors_report_where_the_page_still_has_room():
    """The block that spills is not always the block to change: a column 10px over may sit
    beside 400px going spare, and an error that names only the spill hides that."""
    from html_mcp_web.server import room_for_errors

    def column(name: str, bbox: list[float]) -> dict:
        return {"kind": "group", "element": name, "bbox": bbox, "padding": [0, 0, 0, 0],
                "children": [], "lines": [], "overflow": False}

    pages = [{
        "number": 1,
        "bbox": [0, 0, 1200, 600],
        "children": ["p1:0", "p1:1"],
        "nodes": {
            "p1:0": column("div.left", [0, 0, 622, 600]),
            "p1:1": column("div.right", [658, 0, 542, 200]),
        },
    }]
    room = room_for_errors(["page 1 content overflows its content area (height by 10px)"], pages)
    assert list(room) == ["1"]
    first = room["1"][0]
    assert first["below"] == "p1:1"          # the short column, which is where the room is
    assert first["bbox"][0] >= 600           # to the right of the column that spilled
    assert first["bbox"][3] >= 300           # and tall enough to take what was going to be cut

    # A page nobody complained about is not measured, and neither is an error of another kind.
    assert room_for_errors(["page 1 two labels print over each other"], pages) == {}


def test_a_formula_counts_as_one_obstacle_when_room_is_measured():
    """The free-region search costs more the more boxes it is given, and a rendered formula
    is hundreds of little spans. Counting each of them put 719 boxes on one page and the
    search held the server for minutes with every other request waiting behind it."""
    from html_mcp_web.server import content_area, leaf_boxes, room_for_errors

    spans = {
        f"p1:0.1.{index}": {"kind": "text", "element": "span.mord.mathnormal",
                            "bbox": [60 + index, 200, 8, 18], "padding": [0, 0, 0, 0],
                            "children": [], "lines": [], "overflow": False}
        for index in range(300)
    }
    nodes = dict(spans)
    nodes["p1:0.1"] = {"kind": "group", "element": "span.katex", "bbox": [60, 200, 400, 24],
                       "padding": [0, 0, 0, 0], "children": list(spans), "lines": [], "overflow": False}
    nodes["p1:0.0"] = {"kind": "text", "element": "p", "bbox": [40, 60, 1200, 30],
                       "padding": [0, 0, 0, 0], "children": [], "lines": [], "overflow": False}
    nodes["p1:0"] = {"kind": "group", "element": "div.body", "bbox": [40, 40, 1200, 600],
                     "padding": [0, 0, 0, 0], "children": ["p1:0.0", "p1:0.1"],
                     "lines": [], "overflow": False}
    page = {"number": 1, "bbox": [0, 0, 1280, 720], "children": ["p1:0"], "nodes": nodes}

    scope_ref, _ = content_area(page)
    boxes = leaf_boxes(page, scope_ref)
    assert [ref for ref, _ in boxes] == ["p1:0.1", "p1:0.0"]  # the formula whole, not its spans

    room = room_for_errors(["page 1 content overflows its content area (height by 4px)"], [page])
    assert room["1"]  # and the room under them is still reported


def started_watcher(root: Path, ignore: list[str]):
    """A watcher started against a stand-in observer, with the paths it asked to watch."""
    import html_mcp_web.watcher as module
    from html_mcp_web.watcher import Watcher

    scheduled: list[tuple[str, bool]] = []

    class FakeObserver:
        def schedule(self, handler, path, recursive):
            scheduled.append((Path(path).name, recursive))

        def start(self):
            pass

    async def on_change(path):
        pass

    watcher = Watcher(root, ["*.html"], ignore, on_change)
    original = module.Observer
    module.Observer = FakeObserver
    try:
        watcher.start(asyncio.new_event_loop())
    finally:
        module.Observer = original
    return watcher, scheduled


def test_watcher_skips_ignored_top_level_directories(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "baselines" / "run1").mkdir(parents=True)
    (tmp_path / ".html-mcp-web").mkdir()
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    # Not in the ignore list: an event under a link resolves outside the project and the
    # handler drops it, so watching through one spends the limit for nothing.
    (tmp_path / "engine").symlink_to(outside)
    watcher, scheduled = started_watcher(tmp_path, ["baselines"])
    assert scheduled == [(tmp_path.name, False), ("docs", True)]


def test_watcher_names_the_costly_directories_when_the_limit_is_used_up(tmp_path):
    """errno ENOSPC on an inotify watch reads as no space left on device, which sends the
    reader to look at the disk. The message says what is actually spent and by what."""
    import errno
    import html_mcp_web.watcher as module
    from html_mcp_web.watcher import Watcher

    for index in range(4):
        (tmp_path / "baselines" / f"run{index}").mkdir(parents=True)
    (tmp_path / "docs").mkdir()

    class FullObserver:
        def schedule(self, handler, path, recursive):
            if recursive:
                raise OSError(errno.ENOSPC, "No space left on device")

        def start(self):
            pass

        def stop(self):
            pass

    async def on_change(path):
        pass

    watcher = Watcher(tmp_path, ["*.html"], [], on_change)
    original = module.Observer
    module.Observer = FullObserver
    try:
        with pytest.raises(RuntimeError) as failure:
            watcher.start(asyncio.new_event_loop())
    finally:
        module.Observer = original
    message = str(failure.value)
    assert "inotify watch limit is used up" in message
    assert "baselines 5" in message  # the tree that costs the most, counted
    assert "ignore" in message and "max_user_watches" in message
    assert watcher.observer is None  # the partly scheduled observer was dropped


def test_watcher_reports_deletions_and_both_ends_of_a_rename(tmp_path):
    """A deleted or renamed-away artifact is a change to it: unreported, the layout
    measured from the old file stayed on offer as current."""
    from watchdog.events import FileDeletedEvent, FileMovedEvent

    watcher, _ = started_watcher(tmp_path, [])
    seen: list[str] = []
    watcher.handler._schedule = lambda path: seen.append(Path(path).name)

    watcher.handler.on_deleted(FileDeletedEvent(str(tmp_path / "slides.html")))
    assert seen == ["slides.html"]

    watcher.handler.on_moved(FileMovedEvent(str(tmp_path / "old.html"), str(tmp_path / "new.html")))
    assert seen == ["slides.html", "old.html", "new.html"]


def test_watcher_follows_a_directory_created_after_it_started(tmp_path):
    """The root is watched flat so that ignoring a top-level directory frees its tree, and
    that leaves a directory made later without a watch of its own."""
    from watchdog.events import DirCreatedEvent

    (tmp_path / "docs").mkdir()
    watcher, scheduled = started_watcher(tmp_path, ["baselines"])
    assert scheduled == [(tmp_path.name, False), ("docs", True)]

    (tmp_path / "figs").mkdir()
    watcher.handler.on_created(DirCreatedEvent(str(tmp_path / "figs")))
    assert scheduled[-1] == ("figs", True)

    # A directory the config leaves out stays out, however it arrives.
    (tmp_path / "baselines").mkdir()
    watcher.handler.on_created(DirCreatedEvent(str(tmp_path / "baselines")))
    # A directory deeper in the tree is already covered by its parent's recursive watch.
    (tmp_path / "docs" / "figures").mkdir()
    watcher.handler.on_created(DirCreatedEvent(str(tmp_path / "docs" / "figures")))
    assert scheduled[-1] == ("figs", True)


async def test_render_page_crops_to_a_target_block(client, monkeypatch) -> None:
    """A one-line fix in one block is confirmed with that block's picture, not the whole
    page's: the target ref crops the render to the block plus a small margin."""
    import io

    import fitz
    from PIL import Image

    test_client, review = client
    revision = review.artifacts["slides"].revision
    posted = await test_client.post(
        "/artifacts/slides/layout",
        json={"revision": revision, "errors": [], "space": space_snapshot()},
    )
    assert posted.status == 200

    # A real one-page PDF at the slide deck's print size, standing in for firefox.
    with fitz.open() as made:
        made.new_page(width=960, height=540)
        pdf = made.tobytes()

    async def printed(runtime):
        return pdf

    monkeypatch.setattr(review, "_pdf", printed)

    # p1:0 is [100, 100, 400, 300] page pixels; with the 8px margin and at 96 dpi the
    # rendered pixels come back one to one with page pixels.
    part = await test_client.get("/artifacts/slides/render/page?page=1&dpi=96&target=p1%3A0")
    assert part.status == 200
    width, height = Image.open(io.BytesIO(await part.read())).size
    assert abs(width - 416) <= 1 and abs(height - 316) <= 1

    whole = await test_client.get("/artifacts/slides/render/page?page=1&dpi=96")
    assert Image.open(io.BytesIO(await whole.read())).size[0] >= 1279

    # The ref names the page it lives on; asking for it on another page is a mistake,
    # an unknown ref is not found, and without a fresh measurement the place is unknown.
    assert (await test_client.get("/artifacts/slides/render/page?page=2&dpi=96&target=p1%3A0")).status == 400
    assert (await test_client.get("/artifacts/slides/render/page?page=1&dpi=96&target=p1%3A9")).status == 404
    # With a review UI connected the server leaves the checking to it, so a target whose
    # measurement has gone stale is refused rather than measured behind the reviewer's back.
    review.websockets.add(object())
    review.artifacts["slides"].revision += 1
    stale = await test_client.get("/artifacts/slides/render/page?page=1&dpi=96&target=p1%3A0")
    assert stale.status == 409


async def test_one_broken_artifact_does_not_take_the_server_down(tmp_path: Path) -> None:
    """A main file can be missing mid-session (the reviewer renaming it, a build not run
    yet). That is the artifact's own problem: it is reported on the artifact, and the
    server comes up serving every healthy one instead of refusing to start."""
    (tmp_path / "good.html").write_text(
        "<!doctype html><html><head><title>Good</title></head><body><p>Fine.</p></body></html>",
        encoding="utf-8",
    )
    config = Config(
        artifacts={
            "good": ArtifactConfig(label="Good", layout="slides", main="good.html"),
            "gone": ArtifactConfig(label="Gone", layout="slides", main="renamed-away.html"),
        },
        watch=["*.html"],
        config_path=tmp_path / ".html-mcp-web.yaml",
    )
    review = HtmlReviewServer(config)
    state = review.project_state()
    assert state["artifacts"]["gone"]["error"] == (
        f"HTML artifact not found: {tmp_path / 'renamed-away.html'}")
    assert state["artifacts"]["gone"]["artifact_digest"] is None
    assert state["artifacts"]["good"]["artifact_digest"]
    assert "error" not in state["artifacts"]["good"]

    # The error reaches the agent, not only the raw state: dropped in the contract, a
    # missing artifact looked exactly like a healthy unchecked one.
    from html_mcp_web.mcp_contract import agent_artifact, agent_artifact_summary
    summary = agent_artifact_summary("gone", state["artifacts"]["gone"])
    assert "not found" in summary["error"]
    detailed = agent_artifact("gone", state["artifacts"]["gone"], tmp_path)
    assert "not found" in detailed["error"]
    assert "error" not in agent_artifact_summary("good", state["artifacts"]["good"])

    app = review.create_app()
    app.on_startup.clear()
    app.on_cleanup.clear()
    test_client = TestClient(TestServer(app))
    await test_client.start_server()
    try:
        assert (await test_client.get("/artifacts/good/artifact")).status == 200
        missing = await test_client.get("/artifacts/gone/artifact")
        assert missing.status == 404
        assert "renamed-away.html" in await missing.text()

        # Deleting a main is a change to its artifact: without the watcher reporting it,
        # the layout measured from the deleted file stayed on offer as current.
        posted = await test_client.post(
            "/artifacts/good/layout",
            json={"revision": review.artifacts["good"].revision, "errors": [],
                  "space": space_snapshot()},
        )
        assert posted.status == 200
        (tmp_path / "good.html").unlink()
        await review.on_project_change(str(tmp_path / "good.html"))
        gone_now = review.project_state()["artifacts"]["good"]
        assert "not found" in gone_now["error"]
        assert gone_now["layout_check"]["checked_revision"] is None
        assert gone_now["space_revision"] is None
    finally:
        await test_client.close()


async def test_the_reviewer_closes_a_batch_under_their_own_name(client) -> None:
    """The agent answers and leaves the thread open so its reasoning stays readable; the
    reviewer closes what they have read. A batch closed from the page is the reviewer's
    act, so the thread records them, and the agent's did-my-edit-land check stays out."""
    test_client, review = client
    digest = review.artifacts["slides"].digest()
    ids = []
    for number in range(2):
        made = await (await test_client.post(
            "/artifacts/slides/comments",
            json={"anchor": text_anchor(digest), "text": f"Look at {number}"},
        )).json()
        ids.append(made["id"])

    closed = await (await test_client.post("/artifacts/slides/comments/update", json={
        "comment_ids": ids, "status": "resolved", "author": "human", "message": "read, all fine",
    })).json()
    assert [entry["status"] for entry in closed["updated"]] == ["resolved", "resolved"]
    # The anchors all survive here, and that is not news to the reviewer who just read them.
    assert "warning" not in closed
    thread = await (await test_client.get(f"/artifacts/slides/comments/{ids[0]}")).json()
    assert thread["thread"][-1] == {**thread["thread"][-1], "author": "human", "text": "read, all fine"}

    # Closing is the reviewer's act: an agent that closed its own work hid the reasoning
    # it is judged by, and a rule that only the instructions carried was read by some
    # sessions and not others. The server refuses it, on the batch and on one thread.
    reopened = await (await test_client.post("/artifacts/slides/comments/update", json={
        "comment_ids": ids, "status": "open", "author": "human", "message": "not yet",
    })).json()
    assert [entry["status"] for entry in reopened["updated"]] == ["open", "open"]
    agent_closed = await test_client.post("/artifacts/slides/comments/update", json={
        "comment_ids": ids, "status": "resolved",
    })
    assert agent_closed.status == 400
    assert "an agent does not resolve" in await agent_closed.text()
    one_closed = await test_client.post(f"/artifacts/slides/comments/{ids[0]}/resolve", json={
        "summary": "", "author": "agent",
    })
    assert one_closed.status == 400
    assert (await (await test_client.get(f"/artifacts/slides/comments/{ids[0]}")).json())["status"] == "open"

    bad = await test_client.post("/artifacts/slides/comments/update", json={
        "comment_ids": ids, "status": "resolved", "author": "someone",
    })
    assert bad.status == 400


async def test_call_button_wakes_a_parked_waiter_and_keeps_an_early_press(client) -> None:
    """The reviewer's press is an interrupt, not a message the agent must be listening for.
    The server keeps the press count and the consumption watermark, so a press made while
    nobody waits answers the next wait at once (the first design froze the watermark into
    each waiter's script, and a press made before the arming was frozen out with it). The
    watermark moves only on the waiter's ack: consuming on the way out lost the wake-up
    whenever the response died on the wire, so until the ack lands the press is offered
    again, and only after it does a restarted waiter park."""
    test_client, review = client

    # Presses with nobody parked are kept, and coalesce into the next wait.
    reply = await (await test_client.post("/review-request")).json()
    assert reply == {"calls": 1, "delivered": False}
    reply = await (await test_client.post("/review-request")).json()
    assert reply == {"calls": 2, "delivered": False}
    early = await test_client.get("/wait-review")
    assert early.status == 200
    assert early.headers["X-Press"] == "2"
    line = await early.text()
    assert line.startswith("[review] reviewer called (press #2)")
    assert "list_comments" in line
    # The line counts threads whose last word is the reviewer's: a count of open threads
    # sent an agent to read one it had already answered.
    assert "no unanswered comments" in line
    asked = await (await test_client.post(
        "/artifacts/slides/comments",
        json={"anchor": {"kind": "artifact"}, "text": "Is this right?"},
    )).json()
    assert "unanswered comments: 1 on 'slides'" in review._review_line()
    await test_client.post("/artifacts/slides/comments/update", json={
        "comment_ids": [asked["id"]], "message": "Yes, checked.",
    })
    assert "no unanswered comments" in review._review_line()

    # Not acked yet (the line may never have reached the harness), so it is offered again.
    again = await test_client.get("/wait-review")
    assert again.status == 200
    assert again.headers["X-Press"] == "2"

    # Acked means consumed: the same waiter restarted parks rather than replaying, so
    # running the script in a loop is safe.
    acked = await (await test_client.post("/wait-review/ack?upto=2")).json()
    assert acked == {"calls": 2, "consumed": 2}
    review.REVIEW_POLL_TIMEOUT = 0.05
    assert (await test_client.get("/wait-review")).status == 204
    review.REVIEW_POLL_TIMEOUT = HtmlReviewServer.REVIEW_POLL_TIMEOUT

    # A parked waiter is released by the press.
    parked = asyncio.ensure_future(test_client.get("/wait-review"))
    for _ in range(50):
        if review.review_waiters == 1:
            break
        await asyncio.sleep(0.02)
    assert review.review_waiters == 1
    reply = await (await test_client.post("/review-request")).json()
    assert reply == {"calls": 3, "delivered": True}
    released = await parked
    assert released.status == 200
    assert (await released.text()).startswith("[review] reviewer called (press #3)")
    assert review.review_waiters == 0

    # An ack from a script that outlived a server restart clamps to what exists and a
    # stale repeat never moves the watermark back.
    over = await (await test_client.post("/wait-review/ack?upto=9")).json()
    assert over == {"calls": 3, "consumed": 3}
    stale = await (await test_client.post("/wait-review/ack?upto=1")).json()
    assert stale == {"calls": 3, "consumed": 3}
    review.REVIEW_POLL_TIMEOUT = 0.05
    assert (await test_client.get("/wait-review")).status == 204


async def test_presses_survive_a_server_restart(client, tmp_path: Path) -> None:
    """The reviewer pressed, the listener restarted, and a stateless waiter that reattached
    quickly parked against fresh zeroes forever: the counters persist, so the press is
    still on offer to the next server."""
    test_client, review = client
    await test_client.post("/review-request")
    reborn = HtmlReviewServer(review.config)
    assert (reborn.review_calls, reborn.review_consumed) == (1, 0)
    reborn.REVIEW_POLL_TIMEOUT = 0.05
    app = reborn.create_app()
    app.on_startup.clear()
    app.on_cleanup.clear()
    second_client = TestClient(TestServer(app))
    await second_client.start_server()
    try:
        offered = await second_client.get("/wait-review")
        assert offered.status == 200
        assert offered.headers["X-Press"] == "1"
        await second_client.post("/wait-review/ack?upto=1")
        third = HtmlReviewServer(review.config)
        assert (third.review_calls, third.review_consumed) == (1, 1)
    finally:
        await second_client.close()
