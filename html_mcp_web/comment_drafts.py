"""Server-owned, file-backed comment replies and rewrites. Only the Reply and Edit
blocks are editable."""

import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

from .mcp_contract import agent_anchor, short_time


@contextlib.contextmanager
def _directory(root: Path, create: bool = False):
    # Walk directory descriptors, never following a symlink, including ancestors.
    root = root.absolute()
    if ".." in root.parts:
        raise ValueError("invalid draft directory")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in root.parts[1:]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def _read(fd: int, name: str) -> str:
    source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(source, "r", encoding="utf-8", newline="") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("draft must be a regular, unlinked file")
        return stream.read()


def _anchor_line(anchor: dict) -> str:
    anchor = agent_anchor(anchor)
    if anchor["kind"] == "text":
        return f"Anchor: …{anchor['prefix']}«{anchor['quote']}»{anchor['suffix']}…"
    if anchor["kind"] == "source":
        return (f"Anchor: {anchor['file']}:{anchor['line_start']}-{anchor['line_end']}"
                f"{' (stale)' if anchor['stale'] else ''} «{anchor['quote']}»")
    if anchor["kind"] == "page":
        return f"Anchor: page {anchor['number']}, {anchor['title']}"
    return "Anchor: the whole artifact"


def _entry_head(entry: dict) -> str:
    head = f"**{entry['author']}** {short_time(entry['at'])}"
    if "updated_at" in entry:
        head += f", rewritten {short_time(entry['updated_at'])}"
    if "edits" in entry:
        head += f", edited {', '.join(entry['edits'])}"
    return f"\n{head}\n"


def export(root: Path, comments: list[dict]) -> dict:
    """Write the draft. Each entry the agent wrote is an Edit block where it stands in the
    thread, holding its current text, and each comment ends in one empty Reply block;
    everything else is fixed."""
    ids = [comment["id"] for comment in comments]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("comment_ids must be nonempty and unique")
    key = uuid.uuid4().hex
    segments = ["# Comment replies\n\nEdit only Reply and Edit blocks; keep their markers. "
                "A Reply block left empty adds nothing; an Edit block left as it is changes nothing.\n"]
    slots: list[list] = []  # ["reply", comment_id] or ["edit", comment_id, entry_id, original]
    for comment in comments:
        # The thread as it reads, not as it is stored: the stored record was three
        # quarters of a draft, and nothing in it past this is for the reader.
        segments[-1] += f"\n## {comment['id']} ({comment['status']})\n{_anchor_line(comment['anchor'])}\n"
        for entry in comment["thread"]:
            segments[-1] += _entry_head(entry)
            if entry["author"] != "agent":
                segments[-1] += f"\n{entry['text']}\n"
                continue
            segments[-1] += f"<!-- edit:{key}:{entry['id']} -->\n"
            segments.append(f"\n<!-- /edit:{key}:{entry['id']} -->\n")
            slots.append(["edit", comment["id"], entry["id"], entry["text"]])
        segments[-1] += f"\n### Reply\n<!-- reply:{key}:{comment['id']} -->\n"
        segments.append(f"\n<!-- /reply:{key}:{comment['id']} -->\n")
        slots.append(["reply", comment["id"]])
    # Between an opening marker line and its closing marker sits the block's content:
    # the entry's current text for an Edit block, nothing yet for a Reply block.
    body = ""
    for index, segment in enumerate(segments):
        body += segment
        if index < len(slots) and slots[index][0] == "edit":
            body += slots[index][3]
    snapshot = {"ids": ids, "updated": [c["updated"] for c in comments], "segments": segments, "slots": slots}
    root = root.absolute()
    with _directory(root, create=True) as fd:
        for suffix, text in ((".snapshot", json.dumps(snapshot, ensure_ascii=False)), (".md", body)):
            target = os.open(key + suffix, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            with os.fdopen(target, "w", encoding="utf-8", newline="") as stream:
                stream.write(text)
    return {"path": str(root / (key + ".md")), "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(), "comment_ids": ids}


def load(root: Path, path: str) -> tuple[dict[str, str], list[tuple[str, str, str]], dict[str, str]]:
    """Read a filled draft back: (replies by comment id, entry rewrites as (comment id,
    entry id, text), expected updated stamps by comment id). Only changed blocks count."""
    candidate = Path(path)
    if ".." in candidate.parts or candidate.parent != root.absolute() or not re.fullmatch(r"[0-9a-f]{32}\.md", candidate.name):
        raise ValueError("draft must be a server-created draft path")
    try:
        with _directory(root) as fd:
            snapshot = json.loads(_read(fd, candidate.stem + ".snapshot"))
            body = _read(fd, candidate.name)
        # Exact immutable segments protect IDs, snapshot timestamps and thread text.
        match = re.fullmatch("(.*?)".join(re.escape(s) for s in snapshot["segments"]), body, re.DOTALL)
        if match is None or len(match.groups()) != len(snapshot["slots"]):
            raise ValueError("malformed draft: edit only Reply and Edit blocks")
        replies: dict[str, str] = {}
        entry_edits: list[tuple[str, str, str]] = []
        for slot, value in zip(snapshot["slots"], match.groups()):
            if slot[0] == "reply":
                if value.strip():
                    replies[slot[1]] = value.strip()
            elif value.strip() != slot[3].strip():
                if not value.strip():
                    raise ValueError(f"the Edit block for {slot[2]} must not be emptied")
                entry_edits.append((slot[1], slot[2], value.strip()))
        if not replies and not entry_edits:
            raise ValueError("the draft holds no reply and no changed Edit block")
        expected = dict(zip(snapshot["ids"], snapshot["updated"]))
        return replies, entry_edits, expected
    except (OSError, UnicodeError, KeyError, TypeError, IndexError, json.JSONDecodeError) as error:
        raise ValueError("invalid or unregistered draft") from error
