"""Agent-facing projection of browser review state."""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def agent_anchor(anchor: dict[str, Any]) -> dict[str, Any]:
    if anchor["kind"] == "text":
        return {
            "kind": "text",
            "quote": anchor["quote"],
            "prefix": anchor["prefix"],
            "suffix": anchor["suffix"],
        }
    return dict(anchor)


def agent_comment(comment: dict[str, Any]) -> dict[str, Any]:
    thread = []
    for entry in comment["thread"]:
        shaped = {"author": entry["author"], "at": entry["at"], "text": entry["text"]}
        if "edits" in entry:
            shaped["edited_files"] = entry["edits"]
        thread.append(shaped)
    return {
        "id": comment["id"],
        "anchor": agent_anchor(comment["anchor"]),
        "thread": thread,
        "status": comment["status"],
    }


def last_human_at(comment: dict[str, Any]) -> str:
    human_entries = [entry for entry in comment["thread"] if entry["author"] == "human"]
    return (human_entries[-1] if human_entries else comment["thread"][0])["at"]


def agent_comment_summary(comment: dict[str, Any]) -> dict[str, Any]:
    human_entries = [entry for entry in comment["thread"] if entry["author"] == "human"]
    request = human_entries[-1] if human_entries else comment["thread"][0]
    anchor = comment["anchor"]
    anchor_summary: dict[str, Any] = {"kind": anchor["kind"]}
    if anchor["kind"] == "page":
        anchor_summary["number"] = anchor["number"]
        anchor_summary["title"] = anchor["title"]
    return {
        "id": comment["id"],
        "status": comment["status"],
        "anchor": anchor_summary,
        "request": request["text"],
        "thread_entries": len(comment["thread"]),
        "last_human_at": last_human_at(comment),
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


def is_unanswered(comment: dict[str, Any]) -> bool:
    return comment["thread"][-1]["author"] == "human"


def is_after(comment: dict[str, Any], since: datetime) -> bool:
    at = datetime.fromisoformat(last_human_at(comment))
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return at > since


def agent_artifact_summary(artifact_id: str, artifact: dict[str, Any]) -> dict[str, Any]:
    layout_check = artifact["layout_check"]
    return {
        "id": artifact_id,
        "label": artifact["label"],
        "layout": artifact["layout"],
        "revision": artifact["revision"],
        "checked_revision": layout_check["checked_revision"],
        "layout_error_count": len(layout_check["errors"]),
        "open_comment_count": artifact["comment_counts"]["open"],
        # A missing main file, among others. Dropping it here showed the agent a healthy
        # unchecked artifact where there was none to check.
        **({"error": artifact["error"]} if "error" in artifact else {}),
    }


def agent_artifact(
    artifact_id: str,
    artifact: dict[str, Any],
    project_dir: Path,
) -> dict[str, Any]:
    edit_name = artifact["content_file"] if "content_file" in artifact else artifact["main_file"]
    result = {
        "id": artifact_id,
        "label": artifact["label"],
        "layout": artifact["layout"],
        "edit_file": str((project_dir / edit_name).resolve()),
        "main_file": str((project_dir / artifact["main_file"]).resolve()),
        "revision": artifact["revision"],
        "layout_check": artifact["layout_check"],
        "space_revision": artifact["space_revision"],
        "comment_counts": artifact["comment_counts"],
        **({"error": artifact["error"]} if "error" in artifact else {}),
    }
    if "template" in artifact:
        result["template"] = artifact["template"]
        result["template_dir"] = artifact["template_dir"]
        result["build_error"] = artifact["build_error"]
    return result
