"""Agent-facing projection of browser review state."""

import hashlib
import re
from datetime import datetime, timezone
from typing import Any


# How much of the text around a quote a read carries. The browser stores 120 characters
# each side, of rendered text: across the real stores that context made a quote findable
# in its source file in 4 of 192 cases where the quote alone was not, so it is there to be
# read, not searched for, and 40 characters say where in a sentence the quote sits.
CONTEXT = 40
# How much of a quote or a request a listing shows; a listing is for choosing a thread.
QUOTE_PREVIEW = 60
REQUEST_PREVIEW = 120
# How many threads a listing shows, newest first; the rest are counted.
LIST_LIMIT = 30


def revision_of(updated: str) -> str:
    """A short token standing for a thread's updated stamp. An agent hands it back to say
    which version of a thread it read; nothing reads its parts."""
    return hashlib.sha256(updated.encode("utf-8")).hexdigest()[:8]


def short_time(stamp: str) -> str:
    """A stored ISO stamp as the server's clock reads it, 'MM-DD HH:MM': nothing an agent
    does with a time needs the second, the microsecond or the offset."""
    return datetime.fromisoformat(stamp).astimezone().strftime("%m-%d %H:%M")


def parse_short_time(value: str) -> datetime:
    """Read back a 'MM-DD HH:MM' the server printed. The year is this one, or the last one
    when that would put the moment in the future."""
    try:
        month_day, clock = value.strip().split(" ", 1)
        month, day = (int(part) for part in month_day.split("-"))
        hour, minute = (int(part) for part in clock.split(":"))
    except ValueError:
        raise ValueError(f"a time reads as 'MM-DD HH:MM', like '09-19 00:52': {value!r}") from None
    now = datetime.now().astimezone()
    moment = datetime(now.year, month, day, hour, minute, tzinfo=now.tzinfo)
    return moment.replace(year=now.year - 1) if moment > now else moment


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def agent_anchor(anchor: dict[str, Any]) -> dict[str, Any]:
    if anchor["kind"] == "text":
        return {
            "kind": "text",
            "quote": anchor["quote"],
            # Rendered text keeps the source's line breaks and indentation as runs of
            # whitespace, which would spend the context on nothing.
            "prefix": re.sub(r"\s+", " ", anchor["prefix"])[-CONTEXT:],
            "suffix": re.sub(r"\s+", " ", anchor["suffix"])[:CONTEXT],
        }
    if anchor["kind"] == "source":
        return {
            key: anchor[key]
            for key in (
                "kind", "file", "quote", "line_start", "line_end",
                "column_start", "column_end", "stale",
            )
        }
    return dict(anchor)


def agent_comment(comment: dict[str, Any]) -> dict[str, Any]:
    thread = []
    for entry in comment["thread"]:
        shaped = {"author": entry["author"], "at": short_time(entry["at"]), "text": entry["text"]}
        # Only the agent's own entries can be rewritten, so only those carry the id to name them by.
        if entry["author"] == "agent":
            shaped = {"id": entry["id"], **shaped}
        if "edits" in entry:
            shaped["edited_files"] = entry["edits"]
        if "updated_at" in entry:
            shaped["updated_at"] = short_time(entry["updated_at"])
        thread.append(shaped)
    return {
        "id": comment["id"],
        "anchor": agent_anchor(comment["anchor"]),
        "thread": thread,
        "status": comment["status"],
        # What a rewrite of an entry must quote; it moves with every change to the thread.
        "rev": revision_of(comment["updated"]),
        # The proposal still waiting on the reviewer, as the pieces it changes.
        **({"suggestion": comment["suggestion"]["changes"]} if "suggestion" in comment else {}),
    }


def last_human_at(comment: dict[str, Any]) -> str:
    human_entries = [entry for entry in comment["thread"] if entry["author"] == "human"]
    return (human_entries[-1] if human_entries else comment["thread"][0])["at"]


def agent_comment_summary(comment: dict[str, Any], with_status: bool) -> dict[str, Any]:
    human_entries = [entry for entry in comment["thread"] if entry["author"] == "human"]
    request = human_entries[-1] if human_entries else comment["thread"][0]
    anchor = comment["anchor"]
    anchor_summary: dict[str, Any] = {"kind": anchor["kind"]}
    if anchor["kind"] == "page":
        anchor_summary["number"] = anchor["number"]
        anchor_summary["title"] = anchor["title"]
    elif anchor["kind"] == "text":
        # A request is mostly a few words about the text it is anchored to; without the
        # quote, choosing a thread took reading it.
        anchor_summary["quote"] = _cut(anchor["quote"], QUOTE_PREVIEW)
    elif anchor["kind"] == "source":
        anchor_summary.update(
            file=anchor["file"],
            line_start=anchor["line_start"],
            line_end=anchor["line_end"],
            stale=anchor["stale"],
        )
    return {
        "id": comment["id"],
        # Every row of a listing filtered by status carries the same one.
        **({"status": comment["status"]} if with_status else {}),
        "anchor": anchor_summary,
        "request": _cut(request["text"], REQUEST_PREVIEW),
        "thread_entries": len(comment["thread"]),
        "last_human_at": short_time(last_human_at(comment)),
    }


REPLY_HEAD = re.compile(r"^(c-[0-9a-f]{8}): ", re.MULTILINE)


def parse_replies(text: str) -> list[tuple[str, str]]:
    """Replies written as one text: each starts at a line head with its comment id and a
    colon, and runs to the next such head, blank lines and all.

    An agent writing a list of objects serialized the prose inside them by hand, and by
    habit as \\uXXXX escapes: five or six tokens a character and, twice, a miscounted code
    point that changed the word. A top-level string it writes as it is. Only a line head
    starts a reply, so a colon in the prose is just a colon.
    """
    heads = list(REPLY_HEAD.finditer(text))
    if not heads:
        raise ValueError("replies_text holds no reply: each starts at a line head with '<comment_id>: '")
    if text[:heads[0].start()].strip():
        raise ValueError("replies_text has text before the first '<comment_id>: ' line head")
    replies: list[tuple[str, str]] = []
    for index, head in enumerate(heads):
        end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
        message = text[head.end():end].strip()
        if not message:
            raise ValueError(f"the reply to {head.group(1)} is empty")
        replies.append((head.group(1), message))
    ids = [comment_id for comment_id, _ in replies]
    if len(set(ids)) != len(ids):
        raise ValueError("each comment appears at most once in replies_text")
    return replies


EDIT_HEAD = re.compile(r"^(c-[0-9a-f]{8})/(e-[0-9a-f]{8})@([0-9a-f]{8}): ", re.MULTILINE)


def parse_entry_edits(text: str) -> list[tuple[str, str, str, str]]:
    """Rewrites of the agent's own entries, written as one text: each starts at a line
    head with the comment id, a slash, the entry id, an @, the comment's rev as read, and a
    colon ('c-1a2b3c4d/e-5e6f7a8b@9f8e7d6c: '), and runs to the next such head. The rev is
    the check that the thread has not moved on since it was read."""
    heads = list(EDIT_HEAD.finditer(text))
    if not heads:
        raise ValueError("edits_text holds no edit: each starts at a line head with '<comment_id>/<entry_id>@<rev>: '")
    if text[:heads[0].start()].strip():
        raise ValueError("edits_text has text before the first '<comment_id>/<entry_id>@<rev>: ' line head")
    found: list[tuple[str, str, str, str]] = []
    for index, head in enumerate(heads):
        end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
        body = text[head.end():end].strip()
        if not body:
            raise ValueError(f"the new text for {head.group(2)} is empty")
        found.append((head.group(1), head.group(2), head.group(3), body))
    if len({entry_id for _, entry_id, _, _ in found}) != len(found):
        raise ValueError("each entry appears at most once in edits_text")
    return found


def is_unanswered(comment: dict[str, Any]) -> bool:
    return comment["thread"][-1]["author"] == "human"


def is_after(comment: dict[str, Any], since: datetime) -> bool:
    """Whether the latest human entry falls in or after the minute since names: a time is
    printed to the minute, so the minute it names comes back rather than being missed."""
    at = datetime.fromisoformat(last_human_at(comment))
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return at >= since



def _moment(stamp: str) -> datetime:
    at = datetime.fromisoformat(stamp)
    return at if at.tzinfo is not None else at.replace(tzinfo=timezone.utc)


def new_requests(comments: list[dict[str, Any]], edge: datetime | None) -> tuple[list[dict[str, Any]], str | None]:
    """What the reviewer has written on open threads that the agent has neither been
    handed before nor already taken up, and the stamp of the newest such entry.

    Unread and unanswered, both: edge says what was handed before, and the agent's last
    entry in a thread says what it has taken up. With no edge the second half alone keeps
    a first call off the whole history. The edge is exact and compared strictly, or the
    entry it names would be handed over on every call.
    """
    fresh: list[dict[str, Any]] = []
    newest: str | None = None
    for comment in comments:
        if comment["status"] != "open":
            continue
        thread = comment["thread"]
        answered = max((index for index, entry in enumerate(thread) if entry["author"] == "agent"), default=-1)
        said = [entry for entry in thread[answered + 1:]
                if entry["author"] == "human" and (edge is None or _moment(entry["at"]) > edge)]
        if not said:
            continue
        fresh.append({
            "id": comment["id"],
            "rev": revision_of(comment["updated"]),
            "anchor": agent_anchor(comment["anchor"]),
            # Every entry here is the reviewer's, on an open thread.
            "entries": [{"at": short_time(entry["at"]), "text": entry["text"]} for entry in said],
        })
        latest = max((entry["at"] for entry in said), key=_moment)
        if newest is None or _moment(latest) > _moment(newest):
            newest = latest
    return fresh, newest
