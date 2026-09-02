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
from typing import Any, Iterable, Iterator, Literal


Author = Literal["human", "agent"]
# A thread is open or resolved. A third state, dismissed, closed a thread without acting
# on it; the reviewer never used it, and it was the one close an agent still had for its
# own work, so a comment not worth acting on is resolved or deleted like any other.
Status = Literal["open", "resolved"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    # Same notation as tex-mcp-web. The prefix makes the id usable verbatim in conversation.
    return f"c-{uuid.uuid4().hex[:8]}"


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


Anchor = TextAnchor | ArtifactAnchor | PageAnchor


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
    raise ValueError(f"unknown anchor kind: {kind!r}")


@dataclass
class ThreadEntry:
    author: Author
    at: str
    text: str
    edits: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"author": self.author, "at": self.at, "text": self.text}
        if self.edits:
            data["edits"] = list(self.edits)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThreadEntry":
        edits = [str(value) for value in data["edits"]] if "edits" in data else []
        return cls(author=data["author"], at=str(data["at"]), text=str(data["text"]), edits=edits)


@dataclass
class Comment:
    id: str
    anchor: Anchor
    thread: list[ThreadEntry]
    status: Status
    created: str
    updated: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "anchor": self.anchor.to_dict(),
            "thread": [entry.to_dict() for entry in self.thread],
            "status": self.status,
            "created": self.created,
            "updated": self.updated,
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
        )


STORE_VERSION = 2


class CommentStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_name(f"{self.path.name}.lock")
        if not self.path.exists():
            self._write({"version": STORE_VERSION, "comments": []})

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

    def update_many(
        self,
        comment_ids: list[str],
        author: Author,
        text: str,
        status: Status | None = None,
        edits: list[str] | None = None,
    ) -> list[Comment]:
        # Changing a comment's status may be silent: replies already carry the content, a
        # forced summary duplicates them, and reopening usually says no more than the
        # status itself does. A reply is only its text, so that one still needs some.
        if not text.strip() and status is None:
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
            changed = []
            now = _now()
            for comment_id in comment_ids:
                index, comment = by_id[comment_id]
                if text.strip() or edits:
                    comment.thread.append(
                        ThreadEntry(author=author, at=now, text=text.strip(), edits=list(edits) if edits is not None else [])
                    )
                if status is not None:
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

    def delete(self, comment_id: str) -> None:
        with self._locked():
            comments = self._all()
            remaining = [comment for comment in comments if comment.id != comment_id]
            if len(remaining) == len(comments):
                raise KeyError(f"comment {comment_id!r} not found")
            self._save(remaining)
