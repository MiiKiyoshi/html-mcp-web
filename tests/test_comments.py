from pathlib import Path

import pytest

from html_mcp_web.comments import CommentStore, DomPosition, PageAnchor, TextAnchor, anchor_from_dict


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
    resolved = store.resolve(created.id, "Updated the sentence", "agent", ["artifact.html"])

    loaded = CommentStore(tmp_path / "comments.json").get(created.id)
    assert replied.thread[-1].author == "agent"
    assert resolved.status == "resolved"
    assert loaded.status == "resolved"
    assert loaded.thread[-1].edits == ["artifact.html"]


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

    resolved = store.resolve(created.id, "", "agent")
    assert resolved.status == "resolved"
    assert len(resolved.thread) == 1

    reopened = store.reopen(created.id, "needs another pass", "human")
    assert reopened.status == "open"

    resolved_with_edits = store.resolve(created.id, "", "agent", ["artifact.html"])
    assert resolved_with_edits.thread[-1].text == ""
    assert resolved_with_edits.thread[-1].edits == ["artifact.html"]

    dismissed = store.dismiss(created.id, "", "human")
    assert dismissed.status == "dismissed"
    assert len(dismissed.thread) == len(resolved_with_edits.thread)

    with pytest.raises(ValueError, match="empty"):
        store.reply(created.id, "   ", "agent")
    with pytest.raises(ValueError, match="empty"):
        store.reopen(created.id, "", "human")
