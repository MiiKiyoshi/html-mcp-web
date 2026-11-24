import json
from pathlib import Path

import pytest

from html_mcp_web.comments import (
    STORE_VERSION,
    Comment,
    CommentStore,
    DomPosition,
    AreaAnchor,
    PageAnchor,
    SourceAnchor,
    TextAnchor,
    anchor_from_dict,
    capture_source_anchor,
    source_offset,
    waiting,
)


def anchor() -> TextAnchor:
    return TextAnchor(
        quote="selected sentence",
        prefix="before ",
        suffix=" after",
        start=DomPosition([1, 0], 2),
        end=DomPosition([1, 0], 19),
        artifact_digest="abc",
    )


def test_thread_lifecycle_is_persisted(tmp_path: Path) -> None:
    store = CommentStore(tmp_path / "comments.json")
    created = store.add(anchor(), "Please verify this claim")
    replied = store.reply(created.id, "I checked the source data", "agent", ["artifact.html"])
    [resolved] = store.update_many([created.id], "human", "Updated the sentence", status="resolved",
                                   edits=["artifact.html"])

    loaded = CommentStore(tmp_path / "comments.json").get(created.id)
    assert replied.thread[-1].author == "agent"
    assert resolved.status == "resolved"
    assert loaded.status == "resolved"
    assert loaded.thread[-1].edits == ["artifact.html"]


def test_a_version_2_store_is_raised_once_and_its_records_are_marked(tmp_path: Path) -> None:
    """Version 2 named an archived thread "reference" and told the records of a suggestion
    applied or rejected from the reviewer's words only by their text. The upgrade renames
    the one and marks the others, once, so they ask the agent nothing. Words the reviewer
    writes after it are their own, whatever they say."""
    path = tmp_path / "comments.json"

    def entry(number: int, author: str, text: str, **more) -> dict:
        return {"id": f"e-0000000{number}", "author": author, "at": f"2026-01-01T00:0{number}:00+00:00",
                "text": text, **more}

    path.write_text(json.dumps({"version": 2, "comments": [{
        "id": "c-00000001", "anchor": {"kind": "artifact"}, "status": "open",
        "created": "2026-01-01T00:00:00+00:00", "updated": "2026-01-01T00:05:00+00:00", "resolved": None,
        "thread": [entry(0, "human", "Shorter?"), entry(1, "agent", "Like this."),
                   entry(2, "human", "Rejected suggestion.\n− Long line\n+ Line"), entry(3, "agent", "Then this."),
                   entry(4, "human", "Applied suggestion.", edits=["slides.html"])],
    }, {
        "id": "c-00000002", "anchor": {"kind": "artifact"}, "status": "reference",
        "created": "2026-01-01T00:00:00+00:00", "updated": "2026-01-01T00:00:00+00:00", "resolved": None,
        "thread": [entry(0, "human", "Applied suggestion.")],
    }]}, ensure_ascii=False), encoding="utf-8")
    store = CommentStore(path)
    raised = path.read_bytes()
    assert json.loads(raised)["version"] == STORE_VERSION == 3
    proposed, kept = store.list()
    assert [(item.applied, item.rejected) for item in proposed.thread] == [
        (False, False), (False, False), (False, True), (False, False), (True, False)]
    assert waiting(proposed.thread) == []
    # Without the files it changed, the same words were never a record.
    assert kept.status == "archived" and waiting(kept.thread) == kept.thread
    CommentStore(path)
    assert path.read_bytes() == raised

    for words, edits in (("Applied suggestion.", ["slides.html"]), ("Rejected suggestion.\n− Line\n+ Long line", None)):
        replied = store.reply(proposed.id, words, "human", edits)
        assert not replied.thread[-1].applied and not replied.thread[-1].rejected
        assert waiting(replied.thread)[-1].text == words


def test_a_store_removed_while_in_use_starts_empty_again(tmp_path: Path) -> None:
    """A reader who empties the project folder and sets it up again removes the store under a
    running server. Every state it was asked for then failed until it was restarted."""
    import shutil

    store = CommentStore(tmp_path / "project" / ".html-mcp-web" / "comments" / "slides.json")
    store.add(anchor(), "before the folder was emptied")
    shutil.rmtree(tmp_path / "project")
    assert store.list() == []
    created = store.add(anchor(), "after it was set up again")
    assert [comment.id for comment in store.list()] == [created.id]


def test_comment_ids_are_distinct(tmp_path: Path) -> None:
    store = CommentStore(tmp_path / "comments.json")
    first = store.add(anchor(), "first")
    second = store.add(anchor(), "second")
    assert first.id != second.id


def test_empty_comment_is_rejected(tmp_path: Path) -> None:
    store = CommentStore(tmp_path / "comments.json")
    with pytest.raises(ValueError, match="empty"):
        store.add(anchor(), "  ")


def test_delete_missing_comment_raises(tmp_path: Path) -> None:
    store = CommentStore(tmp_path / "comments.json")
    with pytest.raises(KeyError):
        store.delete("missing")


def test_page_anchor_round_trips(tmp_path: Path) -> None:
    store = CommentStore(tmp_path / "comments.json")
    created = store.add(PageAnchor(number=3, title="Results"), "This slide is too dense")

    loaded = CommentStore(tmp_path / "comments.json").get(created.id)
    assert loaded.anchor.to_dict() == {"kind": "page", "number": 3, "title": "Results"}
    assert anchor_from_dict(loaded.anchor.to_dict()) == PageAnchor(number=3, title="Results")


def test_page_anchor_rejects_number_below_one() -> None:
    with pytest.raises(ValueError, match="1 or greater"):
        anchor_from_dict({"kind": "page", "number": 0, "title": "Results"})


def test_an_area_anchor_keeps_its_box_in_page_pixels(tmp_path: Path) -> None:
    from html_mcp_web.comment_drafts import _anchor_line
    from html_mcp_web.mcp_contract import agent_comment, agent_comment_summary

    store = CommentStore(tmp_path / "comments.json")
    created = store.add(anchor_from_dict(
        {"kind": "area", "number": 2, "title": "Results", "bbox": [30.04, 40, 430.36, 240]}), "this plot")
    loaded = store.get(created.id).to_dict()
    assert loaded["anchor"] == {"kind": "area", "number": 2, "title": "Results", "bbox": [30.0, 40.0, 430.4, 240.0]}
    assert isinstance(store.get(created.id).anchor, AreaAnchor)
    # What the agent reads is the page and the box image(bbox) takes, and no more.
    assert agent_comment(loaded)["anchor"] == loaded["anchor"]
    assert agent_comment_summary(loaded, False)["anchor"] == loaded["anchor"]
    assert _anchor_line(loaded["anchor"]) == "Anchor: page 2, Results, the box 30,40 to 430.4,240 in page pixels"
    for bbox in ([40, 40, 30, 240], [-1, 0, 10, 10], [0, 0, 10]):
        with pytest.raises(ValueError):
            anchor_from_dict({"kind": "area", "number": 2, "title": "Results", "bbox": bbox})


def test_source_anchor_keeps_exact_utf16_selection_and_reattaches(tmp_path: Path) -> None:
    source = tmp_path / "content.html"
    source.write_text("<p>😀 long selected words here</p>\n", encoding="utf-8")
    start = len("<p>😀 ".encode("utf-16-le")) // 2
    end = start + len("long selected".encode("utf-16-le")) // 2
    captured = capture_source_anchor(source, "content.html", 1, 1, start, end)
    assert captured.quote == "long selected"
    assert source_offset(source.read_text(encoding="utf-8"), 1, start) == len("<p>😀 ")

    store = CommentStore(tmp_path / "comments.json")
    created = store.add(captured, "Tighten this phrase")
    source.write_text("<main>\n<p>😀 long selected words here</p>\n</main>\n", encoding="utf-8")
    store.refresh_source_anchors(source, "content.html")
    moved = store.get(created.id).anchor
    assert isinstance(moved, SourceAnchor)
    assert (moved.line_start, moved.line_end, moved.column_start, moved.column_end) == (2, 2, start, end)
    assert moved.stale is False

    source.write_text("<main>\n<p>😀 changed words here</p>\n</main>\n", encoding="utf-8")
    store.refresh_source_anchors(source, "content.html")
    assert store.get(created.id).anchor.stale is True


def test_repeated_source_quote_needs_unique_context(tmp_path: Path) -> None:
    source = tmp_path / "content.html"
    source.write_text("<p>first word</p>\n<p>second word</p>\n", encoding="utf-8")
    anchor = capture_source_anchor(source, "content.html", 2, 2, 10, 14)
    store = CommentStore(tmp_path / "comments.json")
    created = store.add(anchor, "This one")
    store.refresh_source_anchors(source, "content.html")
    moved = store.get(created.id).anchor
    assert isinstance(moved, SourceAnchor)
    assert moved.line_start == 2
    assert moved.stale is False


def test_update_many_is_atomic(tmp_path: Path) -> None:
    store = CommentStore(tmp_path / "comments.json")
    first = store.add(anchor(), "first")
    second = store.add(anchor(), "second")

    with pytest.raises(KeyError, match="missing"):
        store.update_many([first.id, "missing"], "agent", "reply")

    assert len(store.get(first.id).thread) == 1
    changed = store.update_many([first.id, second.id], "agent", "done", status="resolved")
    assert [comment.id for comment in changed] == [first.id, second.id]
    assert all(comment.status == "resolved" for comment in changed)


def test_silent_close_flips_status_without_thread_entry(tmp_path: Path) -> None:
    store = CommentStore(tmp_path / "comments.json")
    created = store.add(anchor(), "fix wording")

    [resolved] = store.update_many([created.id], "human", "", status="resolved")
    assert resolved.status == "resolved"
    assert len(resolved.thread) == 1

    [reopened] = store.update_many([created.id], "human", "needs another pass", status="open")
    assert reopened.status == "open"

    [resolved_with_edits] = store.update_many([created.id], "human", "", status="resolved", edits=["artifact.html"])
    assert resolved_with_edits.thread[-1].text == ""
    assert resolved_with_edits.thread[-1].edits == ["artifact.html"]

    # Reopening is a status change like the close above, and the reason asked for was
    # usually the status said twice; a reply is only its text, so that one still needs some.
    [silently_reopened] = store.update_many([created.id], "human", "", status="open")
    assert silently_reopened.status == "open"
    assert len(silently_reopened.thread) == len(resolved_with_edits.thread)

    with pytest.raises(ValueError, match="empty"):
        store.reply(created.id, "   ", "agent")


def test_a_close_leaves_its_time_and_a_reopen_takes_it_back(tmp_path: Path) -> None:
    """The resolved view leads with the comment closed last, and the time it was last
    touched cannot say which that was: a reply after the close moves that too."""
    store = CommentStore(tmp_path / "comments.json")
    created = store.add(anchor(), "Please verify this claim")
    assert created.resolved is None
    [closed] = store.update_many([created.id], "human", "", status="resolved")
    assert closed.resolved == closed.updated
    replied = store.reply(created.id, "A word after the close", "agent")
    assert replied.resolved == closed.resolved
    assert CommentStore(tmp_path / "comments.json").get(created.id).resolved == closed.resolved
    assert store.update_many([created.id], "human", "", status="open")[0].resolved is None

    # A record stored before the field carries none.
    stored = closed.to_dict()
    del stored["resolved"]
    assert Comment.from_dict(stored).resolved is None


def test_an_archived_thread_stays_readable_and_comes_back(tmp_path: Path) -> None:
    """Archived is a third status beside open and resolved, for a thread worth reading
    again: it takes replies without changing, and goes back to either with one flip."""
    store = CommentStore(tmp_path / "comments.json")
    created = store.add(anchor(), "Keep this reasoning")

    def flip(status: str):
        return store.update_many([created.id], "human", "", status=status)[0]

    kept = flip("archived")
    assert kept.status == "archived" and kept.resolved is None
    assert len(kept.thread) == 1                      # a status flip adds no entry
    assert [comment.id for comment in store.list(status="archived")] == [created.id]
    assert store.list(status="open") == [] and store.list(status="resolved") == []

    replied = store.reply(created.id, "One more thought", "agent")
    assert replied.status == "archived" and len(replied.thread) == 2
    assert flip("resolved").status == "resolved"
    assert flip("archived").resolved is None  # resolved -> archived
    assert flip("open").status == "open"
    assert len(store.get(created.id).thread) == 2      # the flips left the thread alone

    # A store written before the status existed holds only open and resolved, and loads.
    older = CommentStore(tmp_path / "older.json")
    older.add(anchor(), "old")
    assert {comment.status for comment in CommentStore(tmp_path / "older.json").list()} == {"open"}


def test_an_applied_proposal_carries_the_reviewers_text_anchor() -> None:
    """The page reattaches a text comment by its quote and one side of context. A proposal
    that rewrites the reviewer's words keeps the comment on what now stands there."""
    from html_mcp_web.comments import DomPosition, TextAnchor, _carry_text_anchor

    def anchor(prefix: str, quote: str, suffix: str) -> TextAnchor:
        at = DomPosition(path=[0], offset=0)
        return TextAnchor(quote=quote, prefix=prefix, suffix=suffix, start=at, end=at, artifact_digest="d")

    inside = anchor("Title ", "old words here", ". Next")
    _carry_text_anchor(inside, [("old words", "new words")])
    assert (inside.prefix, inside.quote, inside.suffix) == ("Title ", "new words here", ". Next")

    exact = anchor("Title ", "old words", ". Next")
    _carry_text_anchor(exact, [("old words", "plain words")])
    assert exact.quote == "plain words"

    # A piece that takes in the whole quote becomes it, and its own ends leave the context.
    around = anchor("Title Each runner gets ", "last week's runs", ". Next")
    _carry_text_anchor(around, [("Each runner gets last week's runs.", "Each runner gets seven nights.")])
    assert (around.prefix, around.quote, around.suffix) == ("Title ", "Each runner gets seven nights.", " Next")

    # A piece that only overlaps it is not guessed at: the comment shows as lost instead.
    overlap = anchor("Title ", "old words here", ". Next")
    _carry_text_anchor(overlap, [("here. Next", "there. Next")])
    assert overlap.quote == "old words here"


def test_a_thread_carries_one_proposal_below_its_conversation(tmp_path: Path) -> None:
    """The rules tex-mcp keeps: one live proposal per thread, replaced rather than added
    to, kept through replies and a close, proposed and applied only while open, and taken
    back at any time with a reason."""
    from html_mcp_web.comments import ArtifactAnchor, SuggestedEdit

    store = CommentStore(tmp_path / "comments.json")
    comment = store.add(ArtifactAnchor(), "Tighten the title.")
    first = store.suggest(comment.id, comment.updated, "Shorter.", SuggestedEdit("a.html", [("Long title", "Title")]))
    second = store.suggest(comment.id, first.updated, "Shorter still.", SuggestedEdit("a.html", [("Long title", "T")]))
    assert second.suggestion == SuggestedEdit("a.html", [("Long title", "T")])
    assert [entry.text for entry in second.thread] == ["Tighten the title.", "Shorter.", "Shorter still."]

    replied = store.reply(comment.id, "Why that short?", author="human")
    assert replied.suggestion == second.suggestion
    [closed] = store.update_many([comment.id], "human", "", status="resolved")
    assert closed.suggestion == second.suggestion
    with pytest.raises(ValueError, match="open"):
        store.suggest(comment.id, closed.updated, "Again.", SuggestedEdit("a.html", [("Long title", "X")]))
    with pytest.raises(ValueError, match="open"):
        store.apply_suggestion(comment.id, closed.updated, lambda suggestion: ["a.html"])

    withdrawn = store.withdraw_suggestion(comment.id, closed.updated, "Keeping the title.")
    assert withdrawn.suggestion is None
    assert withdrawn.thread[-1].text == "Keeping the title."
    with pytest.raises(ValueError, match="carries no suggestion"):
        store.withdraw_suggestion(comment.id, withdrawn.updated, "Again.")
