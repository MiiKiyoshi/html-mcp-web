"""Anchored comment threads stored beside the reviewed HTML artifact."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Literal


Author = Literal["human", "agent"]
# A thread is open, resolved, or kept as reference: a thread worth reading again after
# the work it asked for is done, or instead of it, listed on its own. A dismissed state
# once closed a thread without acting on it; the reviewer never used it, and it was the
# one close an agent still had for its own work, so a comment not worth acting on is
# resolved or deleted like any other.
Status = Literal["open", "resolved", "reference"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    # Same notation as tex-mcp-web. The prefix makes the id usable verbatim in conversation.
    return f"c-{uuid.uuid4().hex[:8]}"


def _new_entry_id() -> str:
    return f"e-{uuid.uuid4().hex[:8]}"


@dataclass
class DomPosition:
    path: list[int]
    offset: int

    def to_dict(self) -> dict[str, Any]:
        return {"path": list(self.path), "offset": self.offset}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DomPosition":
        return cls(path=[int(value) for value in data["path"]], offset=int(data["offset"]))


@dataclass
class TextAnchor:
    quote: str
    prefix: str
    suffix: str
    start: DomPosition
    end: DomPosition
    artifact_digest: str
    kind: Literal["text"] = "text"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "quote": self.quote,
            "prefix": self.prefix,
            "suffix": self.suffix,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "artifact_digest": self.artifact_digest,
        }


@dataclass
class ArtifactAnchor:
    kind: Literal["artifact"] = "artifact"

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind}


@dataclass
class PageAnchor:
    """A comment attached to a whole page. It reattaches by page number even after the body is edited."""

    number: int
    title: str
    kind: Literal["page"] = "page"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "number": self.number, "title": self.title}


@dataclass
class SourceAnchor:
    """Exact selected source characters with enough context to reattach after edits."""

    file: str
    quote: str
    prefix: str
    suffix: str
    line_start: int
    line_end: int
    column_start: int
    column_end: int
    stale: bool = False
    kind: Literal["source"] = "source"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "file": self.file,
            "quote": self.quote,
            "prefix": self.prefix,
            "suffix": self.suffix,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "column_start": self.column_start,
            "column_end": self.column_end,
            "stale": self.stale,
        }


Anchor = TextAnchor | ArtifactAnchor | PageAnchor | SourceAnchor


def anchor_from_dict(data: dict[str, Any]) -> Anchor:
    kind = data["kind"]
    if kind == "text":
        quote = str(data["quote"])
        if not quote.strip():
            raise ValueError("text anchor quote must not be empty")
        return TextAnchor(
            quote=quote,
            prefix=str(data["prefix"]),
            suffix=str(data["suffix"]),
            start=DomPosition.from_dict(data["start"]),
            end=DomPosition.from_dict(data["end"]),
            artifact_digest=str(data["artifact_digest"]),
        )
    if kind == "artifact":
        return ArtifactAnchor()
    if kind == "page":
        number = int(data["number"])
        if number < 1:
            raise ValueError("page anchor number must be 1 or greater")
        return PageAnchor(number=number, title=str(data["title"]))
    if kind == "source":
        anchor = SourceAnchor(
            file=str(data["file"]),
            quote=str(data["quote"]),
            prefix=str(data["prefix"]),
            suffix=str(data["suffix"]),
            line_start=int(data["line_start"]),
            line_end=int(data["line_end"]),
            column_start=int(data["column_start"]),
            column_end=int(data["column_end"]),
            stale=bool(data.get("stale", False)),
        )
        if not anchor.file or not anchor.quote:
            raise ValueError("source anchor file and quote must not be empty")
        if anchor.line_start < 1 or anchor.line_end < anchor.line_start:
            raise ValueError("source anchor lines are out of bounds")
        if anchor.column_start < 0 or anchor.column_end < 0:
            raise ValueError("source anchor columns must be nonnegative")
        if (anchor.line_start, anchor.column_start) >= (anchor.line_end, anchor.column_end):
            raise ValueError("source selection must be nonempty and ordered")
        return anchor
    raise ValueError(f"unknown anchor kind: {kind!r}")


def source_offset(text: str, line: int, column: int) -> int:
    """Convert a 1-based line and 0-based UTF-16 editor column to a Python offset."""
    lines = text.split("\n")
    if line < 1 or line > len(lines) or column < 0:
        raise ValueError("source position is out of bounds")
    encoded = lines[line - 1].encode("utf-16-le")
    if column * 2 > len(encoded):
        raise ValueError("source column is out of bounds")
    try:
        prefix = encoded[:column * 2].decode("utf-16-le")
    except UnicodeDecodeError as error:
        raise ValueError("source column splits a character") from error
    return sum(len(value) + 1 for value in lines[:line - 1]) + len(prefix)


def _source_coordinate(text: str, offset: int) -> tuple[int, int]:
    before = text[:offset]
    return before.count("\n") + 1, len(before.rsplit("\n", 1)[-1].encode("utf-16-le")) // 2


def capture_source_anchor(
    path: Path,
    file_name: str,
    line_start: int,
    line_end: int,
    column_start: int,
    column_end: int,
) -> SourceAnchor:
    """Capture only the selected characters; surrounding text is relocation context."""
    text = path.read_text(encoding="utf-8")
    start = source_offset(text, line_start, column_start)
    end = source_offset(text, line_end, column_end)
    if end <= start:
        raise ValueError("source selection must be nonempty and ordered")
    return SourceAnchor(
        file=file_name,
        quote=text[start:end],
        prefix=text[max(0, start - 80):start],
        suffix=text[end:end + 80],
        line_start=line_start,
        line_end=line_end,
        column_start=column_start,
        column_end=column_end,
    )


def relocate_source_anchor(anchor: SourceAnchor, path: Path) -> SourceAnchor:
    """Relocate one exact selection. Changed or ambiguous selections become stale."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        anchor.stale = True
        return anchor
    positions: list[int] = []
    cursor = 0
    while anchor.quote:
        found = text.find(anchor.quote, cursor)
        if found < 0:
            break
        positions.append(found)
        cursor = found + 1
    if len(positions) > 1:
        positions = [
            start for start in positions
            if text[:start].endswith(anchor.prefix)
            and text[start + len(anchor.quote):].startswith(anchor.suffix)
        ]
    if len(positions) != 1:
        anchor.stale = True
        return anchor
    start = positions[0]
    end = start + len(anchor.quote)
    anchor.line_start, anchor.column_start = _source_coordinate(text, start)
    anchor.line_end, anchor.column_end = _source_coordinate(text, end)
    anchor.stale = False
    return anchor


@dataclass
class SuggestedEdit:
    """The rewrite a thread currently proposes: the pieces of one file it changes.

    Each ``old`` is a verbatim piece of *file* that occurs there exactly once, and
    ``new`` is what it becomes. Nothing that stays the same is carried, so a proposal
    that touches three words costs three words rather than the paragraph twice. A
    thread holds at most one: proposing again replaces it, applying it clears it.
    """

    file: str
    changes: list[tuple[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "changes": [{"old": old, "new": new} for old, new in self.changes]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SuggestedEdit":
        return cls(file=str(data["file"]), changes=[(str(c["old"]), str(c["new"])) for c in data["changes"]])


def _all_occurrences(text: str, needle: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while True:
        position = text.find(needle, start)
        if position < 0:
            return positions
        positions.append(position)
        start = position + 1


def locate_fragments(text: str, edits: list[tuple[str, str]]) -> list[tuple[int, int, str]]:
    """Find each ``(old, new)`` fragment in *text*, all or none, ordered by position.

    The agent names what to change by quoting it, the way an editing tool does, so it
    never has to count characters to reach a column. A fragment that is missing, that
    occurs more than once, or that overlaps another one is refused with what the caller
    needs to fix it in one retry: for an ambiguous one that is the lines it was found
    on, so the quote can be extended on purpose rather than by guessing.
    """
    if not edits:
        raise ValueError("a suggestion needs at least one edit")
    spans: list[tuple[int, int, str]] = []
    for old, new in edits:
        if not old:
            raise ValueError("an edit must say which text to replace")
        found = _all_occurrences(text, old)
        if not found:
            raise ValueError(f"not found in the source: {old!r}")
        if len(found) > 1:
            lines = ", ".join(str(text.count("\n", 0, at) + 1) for at in found)
            raise ValueError(
                f"{old!r} occurs {len(found)} times, on lines {lines}; "
                "quote more of the surrounding text"
            )
        spans.append((found[0], found[0] + len(old), new))
    spans.sort()
    for (_, end, _), (start, _, _) in zip(spans, spans[1:]):
        if start < end:
            raise ValueError("two edits cover the same text")
    return spans


def swap_fragments(text: str, edits: list[tuple[str, str]]) -> str:
    """Rewrite *text* by replacing each quoted fragment, all or none."""
    spans = locate_fragments(text, edits)
    updated = text
    # Back to front, so an earlier swap cannot move a later one's offsets.
    for start, end, new in reversed(spans):
        updated = updated[:start] + new + updated[end:]
    if updated == text:
        raise ValueError("the edits leave the text as it is")
    return updated


def _carry_text_anchor(anchor: TextAnchor, changes: list[tuple[str, str]]) -> None:
    """Keep a comment on the reviewer's words when an applied proposal rewrites them.

    The page reattaches a text comment by its quote and requires the words on at least one
    side of it to match. A piece inside the quote changes the quote the same way. A piece
    that takes in the whole quote becomes the quote, and the parts of it that lay beside
    the quote come off that side's context, so the context is again what surrounds it.
    Anything else leaves the comment to be shown as lost rather than placed by a guess.
    """
    quote = anchor.quote
    exact = [new for old, new in changes if old == quote]
    inside = [(old, new) for old, new in changes if old != quote and quote.count(old) == 1]
    around = [(old, new) for old, new in changes if old != quote and old.count(quote) == 1]
    if len(exact) == 1 and not inside and not around:
        anchor.quote = exact[0]
    elif len(inside) == 1 and not exact and not around:
        old, new = inside[0]
        anchor.quote = quote.replace(old, new, 1)
    elif len(around) == 1 and not exact and not inside:
        old, new = around[0]
        head, _, tail = old.partition(quote)
        if anchor.prefix.endswith(head) and anchor.suffix.startswith(tail):
            anchor.prefix = anchor.prefix[:len(anchor.prefix) - len(head)]
            anchor.suffix = anchor.suffix[len(tail):]
            anchor.quote = new


@dataclass
class ThreadEntry:
    author: Author
    at: str
    text: str
    edits: list[str] = field(default_factory=list)
    # A stable id, so an entry can be named after the thread grows; updated_at is set when
    # its text was rewritten after it was written.
    id: str = field(default_factory=_new_entry_id)
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.id, "author": self.author, "at": self.at, "text": self.text}
        if self.edits:
            data["edits"] = list(self.edits)
        if self.updated_at is not None:
            data["updated_at"] = self.updated_at
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThreadEntry":
        edits = [str(value) for value in data["edits"]] if "edits" in data else []
        return cls(author=data["author"], at=str(data["at"]), text=str(data["text"]), edits=edits,
                   id=str(data["id"]) if "id" in data else _new_entry_id(),
                   updated_at=str(data["updated_at"]) if "updated_at" in data else None)


@dataclass
class Comment:
    id: str
    anchor: Anchor
    thread: list[ThreadEntry]
    status: Status
    created: str
    updated: str
    # When the comment was last closed; none while it is open. The resolved view leads
    # with the comment closed last, and "updated" cannot say which that was: a reply
    # after the close moves it too.
    resolved: str | None
    suggestion: SuggestedEdit | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "anchor": self.anchor.to_dict(),
            "thread": [entry.to_dict() for entry in self.thread],
            "status": self.status,
            "created": self.created,
            "updated": self.updated,
            "resolved": self.resolved,
            **({"suggestion": self.suggestion.to_dict()} if self.suggestion is not None else {}),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Comment":
        return cls(
            id=str(data["id"]),
            anchor=anchor_from_dict(data["anchor"]),
            thread=[ThreadEntry.from_dict(entry) for entry in data["thread"]],
            status=data["status"],
            created=str(data["created"]),
            updated=str(data["updated"]),
            # A store written before the field carries none: its closed comments keep
            # the order they were written in.
            resolved=str(data["resolved"]) if "resolved" in data and data["resolved"] is not None else None,
            # A thread written before proposals existed carries none.
            suggestion=SuggestedEdit.from_dict(data["suggestion"]) if "suggestion" in data else None,
        )


STORE_VERSION = 2


class CommentStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_name(f"{self.path.name}.lock")
        if not self.path.exists():
            self._write({"version": STORE_VERSION, "comments": []})
        else:
            self._assign_entry_ids()

    def _assign_entry_ids(self) -> None:
        """Give entries written before they carried ids their ids, once, under the lock:
        an id made on every load would name nothing across loads."""
        with self._locked():
            try:
                data = self._read()
            except (OSError, ValueError, KeyError, TypeError):
                return  # an unreadable store fails on its first operation, as before
            if all("id" in entry for comment in data["comments"] for entry in comment["thread"]):
                return
            self._save(Comment.from_dict(value) for value in data["comments"])

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        try:
            import fcntl
        except ImportError:
            yield
            return
        with self.lock_path.open("a") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read(self) -> dict[str, Any]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if int(data["version"]) != STORE_VERSION:
            raise ValueError(f"unsupported comment store version: {data['version']}")
        if not isinstance(data["comments"], list):
            raise ValueError("comments must be a list")
        return data

    def _write(self, data: dict[str, Any]) -> None:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.path.parent,
            prefix=".comments-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            temporary = Path(handle.name)
        os.replace(temporary, self.path)

    def _all(self) -> list[Comment]:
        return [Comment.from_dict(value) for value in self._read()["comments"]]

    def _save(self, comments: Iterable[Comment]) -> None:
        self._write({"version": STORE_VERSION, "comments": [comment.to_dict() for comment in comments]})

    def list(self, status: Status | None = None) -> list[Comment]:
        comments = self._all()
        return comments if status is None else [comment for comment in comments if comment.status == status]

    def refresh_source_anchors(self, path: Path, file_name: str) -> None:
        """Reattach exact source selections after their editable file changes."""
        with self._locked():
            comments = self._all()
            before = [comment.to_dict() for comment in comments]
            for comment in comments:
                if isinstance(comment.anchor, SourceAnchor) and comment.anchor.file == file_name:
                    relocate_source_anchor(comment.anchor, path)
            if before != [comment.to_dict() for comment in comments]:
                self._save(comments)

    def get(self, comment_id: str) -> Comment:
        for comment in self._all():
            if comment.id == comment_id:
                return comment
        raise KeyError(f"comment {comment_id!r} not found")

    def add(self, anchor: Anchor, text: str, author: Author = "human") -> Comment:
        if not text.strip():
            raise ValueError("comment text must not be empty")
        now = _now()
        comment = Comment(
            id=_new_id(),
            anchor=anchor,
            thread=[ThreadEntry(author=author, at=now, text=text.strip())],
            status="open",
            created=now,
            updated=now,
            resolved=None,
        )
        with self._locked():
            comments = self._all()
            comments.append(comment)
            self._save(comments)
        return comment

    def _append(
        self,
        comment_id: str,
        author: Author,
        text: str,
        status: Status | None = None,
        edits: list[str] | None = None,
    ) -> Comment:
        return self.update_many([comment_id], author, text, status=status, edits=edits)[0]

    def export_comments(self, comment_ids: list[str]) -> dict:
        from .comment_drafts import export

        with self._locked():
            by_id = {comment.id: comment for comment in self._all()}
            return export(self.path.parent.parent / "drafts" / self.path.stem,
                          [by_id[key].to_dict() for key in comment_ids])

    def reply_file(self, path: str, edits: list[str] | None = None) -> list[Comment]:
        from .comment_drafts import load

        replies, entry_edits, expected = load(self.path.parent.parent / "drafts" / self.path.stem, path)
        return self.apply_batch(replies, entry_edits, expected, edits)

    def edit_agent_entries(self, entry_edits: list[tuple[str, str, str]],
                           expected_updated: dict[str, str]) -> list[Comment]:
        """Rewrite agent entries named by (comment id, entry id), all or none.
        expected_updated maps each touched comment to the updated stamp the caller read;
        a thread that moved on since refuses the whole batch."""
        return self.apply_batch({}, entry_edits, expected_updated, None)

    def apply_batch(
        self,
        replies: dict[str, str],
        entry_edits: list[tuple[str, str, str]],
        expected_updated: dict[str, str],
        edits: list[str] | None,
    ) -> list[Comment]:
        """Append agent replies and rewrite agent entries under one lock and one save.

        Every comment in expected_updated is checked against the store first; nothing is
        written unless all of it can be. An entry is named by its comment and its own id,
        (comment_id, entry_id, text); an entry that is not in that thread, or a human's,
        is refused."""
        if not replies and not entry_edits:
            raise ValueError("nothing to apply")
        if any(not text.strip() for text in replies.values()) or any(not text.strip() for _, _, text in entry_edits):
            raise ValueError("thread text must not be empty")
        if len({entry_id for _, entry_id, _ in entry_edits}) != len(entry_edits):
            raise ValueError("each entry appears at most once")
        with self._locked():
            comments = self._all()
            by_id = {comment.id: comment for comment in comments}
            entries = {(comment.id, entry.id): entry for comment in comments for entry in comment.thread}
            touched: dict[str, Comment] = {}
            for comment_id, entry_id, _ in entry_edits:
                if (comment_id, entry_id) not in entries:
                    raise KeyError(f"thread entry {entry_id!r} not found in {comment_id!r}")
                entry = entries[(comment_id, entry_id)]
                if entry.author != "agent":
                    raise ValueError(f"thread entry {entry_id} was written by {entry.author}")
                touched[comment_id] = by_id[comment_id]
            for comment_id in replies:
                if comment_id not in by_id:
                    raise KeyError(f"comments not found: {comment_id}")
                touched[comment_id] = by_id[comment_id]
            for comment_id, comment in touched.items():
                if comment_id not in expected_updated:
                    raise ValueError(f"no updated stamp given for {comment_id}")
                if comment.updated != expected_updated[comment_id]:
                    raise ValueError(f"stale: {comment_id} changed since it was read")
            now = _now()
            for comment_id, entry_id, text in entry_edits:
                entry = entries[(comment_id, entry_id)]
                entry.text = text.strip()
                entry.updated_at = now
            for comment_id, text in replies.items():
                by_id[comment_id].thread.append(
                    ThreadEntry(author="agent", at=now, text=text.strip(), edits=list(edits or [])))
            for comment in touched.values():
                comment.updated = now
            self._save(comments)
            return list(touched.values())

    def update_many(
        self,
        comment_ids: list[str],
        author: Author,
        text: str | dict[str, str],
        status: Status | None = None,
        edits: list[str] | None = None,
        expected_updated: dict[str, str] | None = None,
    ) -> list[Comment]:
        # Changing a comment's status may be silent: replies already carry the content, a
        # forced summary duplicates them, and reopening usually says no more than the
        # status itself does. A reply is only its text, so that one still needs some.
        texts = text if isinstance(text, dict) else dict.fromkeys(comment_ids, text)
        if any(not value.strip() for value in texts.values()) and status is None:
            raise ValueError("thread text must not be empty")
        if not comment_ids:
            raise ValueError("comment_ids must not be empty")
        if len(set(comment_ids)) != len(comment_ids):
            raise ValueError("comment_ids must be unique")
        with self._locked():
            comments = self._all()
            by_id = {comment.id: (index, comment) for index, comment in enumerate(comments)}
            missing = [comment_id for comment_id in comment_ids if comment_id not in by_id]
            if missing:
                raise KeyError(f"comments not found: {', '.join(missing)}")
            if expected_updated is not None and any(
                by_id[key][1].updated != expected_updated[key] for key in comment_ids
            ):
                raise ValueError("stale draft: export comments again")
            changed = []
            now = _now()
            for comment_id in comment_ids:
                index, comment = by_id[comment_id]
                text = texts[comment_id]
                if text.strip() or edits:
                    comment.thread.append(
                        ThreadEntry(author=author, at=now, text=text.strip(), edits=list(edits) if edits is not None else [])
                    )
                if status is not None:
                    if status != comment.status:
                        comment.resolved = now if status == "resolved" else None
                    comment.status = status
                comment.updated = now
                comments[index] = comment
                changed.append(comment)
            self._save(comments)
            return changed

    def reply(self, comment_id: str, text: str, author: Author, edits: list[str] | None = None) -> Comment:
        return self._append(comment_id, author, text, edits=edits)

    def resolve(self, comment_id: str, summary: str, author: Author, edits: list[str] | None = None) -> Comment:
        return self._append(comment_id, author, summary, status="resolved", edits=edits)


    def reopen(self, comment_id: str, text: str, author: Author) -> Comment:
        return self._append(comment_id, author, text, status="open")

    def keep_as_reference(self, comment_id: str, author: Author) -> Comment:
        """Set the thread aside to be read again; its entries stay as they are."""
        return self._append(comment_id, author, "", status="reference")

    def edit_entry(self, comment_id: str, index: int, text: str, author: Author) -> Comment:
        """Rewrite one thread entry in place, keeping its author and time."""
        if not text.strip():
            raise ValueError("thread text must not be empty")
        with self._locked():
            comments = self._all()
            for position, comment in enumerate(comments):
                if comment.id != comment_id:
                    continue
                if not 0 <= index < len(comment.thread):
                    raise IndexError(f"comment {comment_id!r} has no thread entry {index}")
                entry = comment.thread[index]
                if entry.author != author:
                    raise ValueError(f"thread entry {index} was written by {entry.author}")
                entry.text = text.strip()
                comment.updated = _now()
                comments[position] = comment
                self._save(comments)
                return comment
        raise KeyError(f"comment {comment_id!r} not found")

    @staticmethod
    def _open_thread(comments: list[Comment], comment_id: str, expected_updated: str) -> Comment:
        for comment in comments:
            if comment.id == comment_id:
                if comment.updated != expected_updated:
                    raise ValueError("stale thread: comment changed since it was read")
                if comment.status != "open":
                    raise ValueError("a suggestion belongs to a comment that is open")
                return comment
        raise KeyError(f"comment {comment_id!r} not found")

    def suggest(self, comment_id: str, expected_updated: str, text: str, suggestion: SuggestedEdit) -> Comment:
        """Put a proposal on an open thread and say why, in one entry.

        Proposing again replaces the proposal and adds another entry, so a thread carries
        one live proposal and its whole conversation."""
        if not text.strip():
            raise ValueError("a suggestion must say why")
        with self._locked():
            comments = self._all()
            comment = self._open_thread(comments, comment_id, expected_updated)
            now = _now()
            comment.thread.append(ThreadEntry(author="agent", at=now, text=text.strip()))
            comment.suggestion = suggestion
            comment.updated = now
            self._save(comments)
            return comment

    def withdraw_suggestion(self, comment_id: str, expected_updated: str, text: str) -> Comment:
        """Take the proposal off a thread and say why, keeping every entry."""
        if not text.strip():
            raise ValueError("a withdrawal must say why")
        with self._locked():
            comments = self._all()
            comment = self._open_thread(comments, comment_id, expected_updated)
            if comment.suggestion is None:
                raise ValueError("the comment carries no suggestion")
            now = _now()
            comment.thread.append(ThreadEntry(author="agent", at=now, text=text.strip()))
            comment.suggestion = None
            comment.updated = now
            self._save(comments)
            return comment

    def apply_suggestion(
        self,
        comment_id: str,
        expected_updated: str,
        write: Callable[[SuggestedEdit], list[str]],
    ) -> Comment:
        """Write a thread's proposal into its file and take it off the thread.

        *write* replaces the file and names the ranges it changed, under this store's lock,
        so a thread that moved on meanwhile refuses rather than writing what the reviewer
        did not see. It must not take the lock itself: the caller reattaches source
        anchors once this returns."""
        with self._locked():
            comments = self._all()
            comment = self._open_thread(comments, comment_id, expected_updated)
            suggestion = comment.suggestion
            if suggestion is None:
                raise ValueError("the comment carries no suggestion")
            edits = write(suggestion)
            if isinstance(comment.anchor, TextAnchor):
                _carry_text_anchor(comment.anchor, suggestion.changes)
            now = _now()
            comment.thread.append(ThreadEntry(author="human", at=now, text="Applied suggestion.", edits=edits))
            comment.suggestion = None
            comment.updated = now
            self._save(comments)
            return comment

    def delete(self, comment_id: str) -> None:
        with self._locked():
            comments = self._all()
            remaining = [comment for comment in comments if comment.id != comment_id]
            if len(remaining) == len(comments):
                raise KeyError(f"comment {comment_id!r} not found")
            self._save(remaining)
