"""MCP tools for reviewing project HTML artifacts."""

import asyncio
import functools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import quote, urlencode

from .mcp_contract import (
    LIST_LIMIT,
    agent_comment,
    agent_comment_summary,
    is_after,
    is_unanswered,
    last_human_at,
    new_requests,
    parse_entry_edits,
    parse_replies,
    parse_short_time,
    revision_of,
    short_time,
)


try:
    from mcp.server.fastmcp import Context, FastMCP, Image
    from pydantic import Field

    from .mcp_client import INIT_GUIDE, ProjectBinding, ProjectSetupError

    MISSING_MCP: ImportError | None = None
except ImportError as error:
    # The error is kept, not just the fact of it. An install that had mcp 2.x failed
    # this import with a message naming the rename and the pin that fixes it, and the
    # line printed in its place said the package was not installed; a reader who
    # believed that reinstalled the package and got the same line back.
    MISSING_MCP = error


def _check_dependencies() -> None:
    if MISSING_MCP is None:
        return
    print(f"html-mcp cannot import its MCP dependencies: {MISSING_MCP}\n"
          "Install html-mcp-web[mcp] into this interpreter.", file=sys.stderr)
    raise SystemExit(1)


def check(start_dir: Path) -> list[str]:
    """Build the server the way stdio would and return the names of its tools.

    The registered command is only ever judged by whether a client connects to it, and a
    server that dies at import is found out after it is registered. This is the same
    server, built the same way, without a transport: it fails where that would, and with
    the same message.
    """
    _check_dependencies()
    server = create_server(ProjectBinding(start_dir))
    return sorted(tool.name for tool in asyncio.run(server.list_tools()))


def _wait_method(ctx: "Context") -> str:
    name = ctx.session.client_params.clientInfo.name.casefold()
    if "claude" in name:
        return (
            "Run the script with Monitor(command=<script>, persistent=true, "
            "timeout_ms=3600000), then end the turn. Keep the monitor for subsequent events."
        )
    if "codex" in name:
        return (
            'Run sh <quoted-script-path> --codex "$CODEX_THREAD_ID" with '
            'exec_command(yield_time_ms=1000, sandbox_permissions="require_escalated", '
            'justification="Allow the HTML review waiter to deliver events to this Codex thread?"). '
            "Once running, end the turn; do not poll. "
            "The script uses codex queue to deliver events as labeled user messages, "
            "including while idle. Delivery may take about 10 seconds. "
            "Requires codex queue on PATH and CODEX_THREAD_ID in the agent shell. "
            "Keep one waiter; stop its process when no longer needed."
        )
    return (
        "Run the script with your shell tool and read its output. If the tool returns a "
        "running session, retain it and use the tool that reads subsequent output. Keep "
        "the turn active while waiting unless your client explicitly supports resuming "
        "a completed turn from background output. After handling an event, resume "
        "waiting on the same process."
    )


def _revisions(result: dict[str, Any]) -> list[dict[str, str]]:
    # A reply leaves the status as it was; what the agent can use next is the rev.
    return [{"id": entry["id"], "rev": revision_of(entry["updated"])} for entry in result["updated"]]


def _compact(tool):
    """A tool's mapping as one line of JSON, its text left as it is.

    Left to the framework, a mapping went out indented by two and a second time as
    structured content, with an output schema in every definition to describe it: the
    indentation alone was 28% of a read of seventeen real threads."""
    @functools.wraps(tool)
    async def answer(*args, **kwargs):
        result = await tool(*args, **kwargs)
        return result if isinstance(result, Image) else json.dumps(result, ensure_ascii=False)
    return answer


def create_server(binding: "ProjectBinding") -> "FastMCP":
    _check_dependencies()
    mcp = FastMCP(
        "html-mcp-web",
        instructions=(
            "Work from read_comments(new=True), and pass ids to reread a whole thread. "
            "Before writing an artifact, read what guide() lists. Within the user's editing "
            "scope, edit, check the affected pages with layout() and image(), and reply with "
            "write_comments. When the wording is the reviewer's to decide, suggest instead of "
            "editing. The reviewer resolves threads. Call listen() when the user asks "
            "to listen and follow how. Reuse its process, and do not poll or duplicate it. "
            f"Setup: read {INIT_GUIDE}."
        ),
    )

    @mcp.tool(structured_output=False)
    @_compact
    async def guide(artifact: str) -> dict[str, Any]:
        """The file to edit for this artifact, and what to read before writing it."""
        client = binding.require_client()
        state = await client.request_json("GET", "/state")
        artifacts = state["artifacts"]
        if artifact not in artifacts:
            raise RuntimeError(f"unknown artifact: {artifact}; available artifacts: {', '.join(artifacts)}")
        entry = artifacts[artifact]
        docs = Path(__file__).resolve().parent.parent / "templates"
        read = [str(docs / "README.md"), str(docs / "COMPONENTS.md")]
        if "template_dir" in entry and entry["template_dir"] is not None:
            notes = Path(entry["template_dir"]) / "README.md"
            if notes.is_file():
                read.append(str(notes))
        if state.get("guideline") is not None:
            read.append(state["guideline"]["path"])
        return {"edit_file": str((Path(state["project_dir"]) / entry["edit_file"]).resolve()), "read": read}

    @mcp.tool(structured_output=False)
    @_compact
    async def read_comments(
        artifact: str,
        ids: list[str] | None = None,
        new: Annotated[bool, Field(description=(
            "What the reviewer wrote on open threads that you have neither been handed nor "
            "answered. Reports from and cursor, and since=<from> takes a turn again."))] = False,
        since: Annotated[str | None, Field(description=(
            "'MM-DD HH:MM'. With new: read from that minute. In a listing: only threads the "
            "reviewer wrote to in or after it."))] = None,
        status: Literal["open", "resolved", "reference", "all"] = "open",
        unanswered: Annotated[bool, Field(description="In a listing: only threads whose latest entry is the reviewer's.")] = False,
        save: Annotated[bool, Field(description=(
            "With ids: write them as a Markdown draft and return its path. Edit only its "
            "Reply and Edit blocks."))] = False,
    ) -> dict[str, Any]:
        """Read what is new (new), threads whole (ids), or else a listing of requests, newest first."""
        client = binding.require_client()
        if new:
            if ids is not None or save or status != "open" or unanswered:
                raise ValueError("new answers on its own; it takes no ids, status, unanswered or save")
            payload = await client.request_json("GET", f"/artifacts/{artifact}/comments?status=open")
            project_dir = Path((await client.request_json("GET", "/state"))["project_dir"])
            previous = read_cursor(project_dir, artifact)
            edge = parse_short_time(since) if since is not None else (
                datetime.fromisoformat(previous) if previous is not None else None)
            fresh, newest = new_requests(payload["comments"], edge)
            # Moved forward only: since= re-reads what was handed over without rewinding.
            latest = previous
            if newest is not None and (previous is None or datetime.fromisoformat(newest) > datetime.fromisoformat(previous)):
                latest = newest
            if latest is None:
                # A quiet first call still fixes where the next one starts.
                latest = datetime.now(timezone.utc).isoformat()
            if latest != previous:
                write_cursor(project_dir, artifact, latest)
            return {
                "comments": fresh,
                **({"from": short_time(previous)} if previous is not None else {}),
                "cursor": short_time(latest),
            }
        if ids is not None:
            if since is not None or status != "open" or unanswered:
                raise ValueError("ids reads those threads whole; it takes no since, status or unanswered")
            if not ids or len(set(ids)) != len(ids):
                raise ValueError("ids must be nonempty and unique")
            if save:
                return await client.request_json("POST", f"/artifacts/{artifact}/comments/export", {"comment_ids": ids})
            comments = []
            for comment_id in ids:
                comment = await client.request_json("GET", f"/artifacts/{artifact}/comments/{comment_id}")
                comments.append(agent_comment(comment))
            return {"artifact": artifact, "comments": comments}
        if save:
            raise ValueError("save needs ids")
        query = "" if status == "all" else f"?status={status}"
        comments = (await client.request_json("GET", f"/artifacts/{artifact}/comments{query}"))["comments"]
        if unanswered:
            comments = [comment for comment in comments if is_unanswered(comment)]
        if since is not None:
            cutoff = parse_short_time(since)
            comments = [comment for comment in comments if is_after(comment, cutoff)]
        # The newest are what was just written; a cap that kept the oldest would hide them.
        comments.sort(key=last_human_at, reverse=True)
        return {
            "artifact": artifact,
            "comments": [agent_comment_summary(comment, status == "all") for comment in comments[:LIST_LIMIT]],
            **({"more": len(comments) - LIST_LIMIT} if len(comments) > LIST_LIMIT else {}),
        }

    @mcp.tool(structured_output=False)
    @_compact
    async def write_comments(
        artifact: str,
        action: Literal["reply", "edit", "suggest", "withdraw"],
        text: Annotated[str | None, Field(min_length=1, description=(
            "reply: the replies as one text, each starting at a line head with its comment id "
            "and a colon ('c-1a2b3c4d: ') and running to the next such head. edit: rewrites of "
            "your own entries, each headed 'c-1a2b3c4d/e-5e6f7a8b@<rev>: '. suggest, withdraw: "
            "why."))] = None,
        edited_files: Annotated[list[str] | None, Field(description="reply: project-relative paths you edited for these comments.")] = None,
        draft: Annotated[str | None, Field(description="reply: a draft from read_comments(save=True), given without text. It carries replies and edits.")] = None,
        id: Annotated[str | None, Field(description="suggest, withdraw: the comment.")] = None,
        rev: Annotated[str | None, Field(description="suggest, withdraw: the comment's rev as read.")] = None,
        changes: Annotated[list[dict[str, str]] | None, Field(description=(
            "suggest: [{old, new}], each old found once in guide()'s edit_file, as the file spells it."))] = None,
    ) -> dict[str, Any]:
        """Reply, rewrite your own entries, or propose a source change for the reviewer to
        apply, replacing that thread's proposal. A stale rev is refused."""
        client = binding.require_client()
        if action in ("suggest", "withdraw"):
            if id is None or rev is None or text is None:
                raise ValueError(f"{action} needs id, rev and text")
            if (action == "suggest") != (changes is not None):
                raise ValueError("changes go with suggest, and only with it")
            comment = await client.request_json("GET", f"/artifacts/{artifact}/comments/{id}")
            if revision_of(comment["updated"]) != rev:
                raise ValueError(f"stale: {id} changed since it was read; read it again")
            body: dict[str, Any] = {"updated": comment["updated"], "text": text}
            if changes is not None:
                body["changes"] = changes
            result = await client.request_json("POST", f"/artifacts/{artifact}/comments/{id}/{action}", body)
            return {"id": id, "rev": revision_of(result["updated"])}
        if draft is not None:
            if action != "reply" or text is not None:
                raise ValueError("a draft goes with action reply and no text")
            result = await client.request_json("POST", f"/artifacts/{artifact}/comments/update", {
                "replies_file": draft,
                **({"edited_files": edited_files} if edited_files is not None else {}),
            })
            return {"updated": _revisions(result), **({"notes": [result["note"]]} if "note" in result else {})}
        if text is None:
            raise ValueError("give text, or a draft")
        if action == "edit":
            rewrites = parse_entry_edits(text)
            # The agent quotes a rev; the store checks a stamp. The stamp read here is the
            # one the rev stood for, or the thread has moved on, and the store checks it
            # again under its lock, so a change in between is refused there.
            stamps: dict[str, str] = {}
            for comment_id, _, rev, _ in rewrites:
                if comment_id not in stamps:
                    comment = await client.request_json("GET", f"/artifacts/{artifact}/comments/{comment_id}")
                    if revision_of(comment["updated"]) != rev:
                        raise ValueError(f"stale: {comment_id} changed since it was read; read it again")
                    stamps[comment_id] = comment["updated"]
            result = await client.request_json("POST", f"/artifacts/{artifact}/comments/update", {
                "entry_edits": [{"comment": comment_id, "entry": entry_id, "updated": stamps[comment_id], "text": body}
                                for comment_id, entry_id, _, body in rewrites],
            })
            return {"updated": _revisions(result)}
        updated: list[dict[str, Any]] = []
        notes: list[str] = []
        for comment_id, message in parse_replies(text):
            result = await client.request_json("POST", f"/artifacts/{artifact}/comments/update", {
                "comment_ids": [comment_id],
                "message": message,
                **({"edited_files": edited_files} if edited_files is not None else {}),
            })
            updated.extend(_revisions(result))
            # Where the quoted text is still in the artifact unchanged after an edit was
            # reported for it: normal for a fix that landed elsewhere, a place to look otherwise.
            if "note" in result:
                notes.append(result["note"])
        return {"updated": updated, **({"notes": notes} if notes else {})}

    @mcp.tool(structured_output=False)
    @_compact
    async def image(
        artifact: str,
        page: Annotated[int, Field(ge=1)],
        target: Annotated[str | None, Field(description="A block ref from layout() (e.g. p8:1.1.0.2): render just that block, for fewer tokens.")] = None,
        dpi: Annotated[int, Field(ge=36, le=300, description="96 reads text. 150 or more shows fine detail at more tokens.")] = 96,
        grayscale: Annotated[bool, Field(description="Set false when colour itself is being checked.")] = True,
        save: Annotated[bool, Field(description="Write a png and return its path, to show the user without spending image tokens.")] = False,
        out: Annotated[str | None, Field(description="With save: the project-relative png path.")] = None,
    ) -> "Image":
        """Render one page, or one block of it, as an image."""
        client = binding.require_client()
        params = f"?page={page}&dpi={dpi}&gray={'1' if grayscale else '0'}"
        if target is not None:
            params += f"&target={quote(target)}"
        data = await client.get_bytes(
            f"/artifacts/{artifact}/render/page{params}",
            timeout=120.0,
        )
        if not save:
            return Image(data=data, format="png")
        project_dir = Path((await client.request_json("GET", "/state"))["project_dir"])
        name = f"{artifact}-{target.replace(':', '-')}.png" if target is not None else f"{artifact}-p{page}.png"
        out_path = ((project_dir / out) if out is not None
                    else project_dir / ".html-mcp-web" / "renders" / name).resolve()
        if not out_path.is_relative_to(project_dir.resolve()):
            raise ValueError("out must stay inside the project directory")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        return {"path": str(out_path), "bytes": len(data), "page": page, "dpi": dpi}

    @mcp.tool(structured_output=False)
    @_compact
    async def layout(
        artifact: str,
        page: Annotated[int | None, Field(ge=1, description="Add this page's blocks and free space, in page pixels.")] = None,
        target: Annotated[str | None, Field(description=(
            "With page: a block ref from children, to measure inside it: its lines and "
            "children, a table's no-wrap widths, an SVG's drawn area."))] = None,
        clearance: Annotated[float, Field(ge=0, description="With page: pixels kept clear around content when free space is found.")] = 0,
        min_width: Annotated[float | None, Field(ge=0, description="With page: only free regions at least this wide.")] = None,
        min_height: Annotated[float | None, Field(ge=0, description="With page: only free regions at least this tall.")] = None,
    ) -> dict[str, Any]:
        """Layout errors of the current revision: content off the page, clipped drawings,
        overlapping labels. With page, that page's errors, blocks and free space."""
        client = binding.require_client()
        # Long enough for the server to run the check itself when no review page is open:
        # it starts a headless browser on its own page and answers once that posts.
        result = await client.request_json("GET", f"/artifacts/{artifact}/layout", timeout=75.0)
        if page is not None:
            if result["errors"] is not None:
                result["errors"] = [error for error in result["errors"] if error.startswith(f"page {page} ")]
                query: dict[str, Any] = {"page": page, "clearance": clearance}
                for key, value in (("target", target), ("min_width", min_width), ("min_height", min_height)):
                    if value is not None:
                        query[key] = value
                space = await client.request_json("GET", f"/artifacts/{artifact}/space?{urlencode(query)}", timeout=75.0)
                # What the agent asked for is not news: only the measurement comes back.
                result.update({key: value for key, value in space.items()
                               if key not in ("artifact", "revision", "page") and value is not None})
        elif target is not None:
            raise ValueError("target needs page")
        if result["errors"]:
            result["note"] = (
                "Treat these as geometric unless the user or a visual check finds a content "
                "problem. Keep content and structure, and make the smallest size or spacing "
                "change first. Do not rewrite, remove, or reorganize content just to clear an "
                "error. Restructure only if that cannot work or the user asks. Then check "
                "layout() and image() for the page again.")
        return result

    @mcp.tool(structured_output=False)
    @_compact
    async def listen(ctx: Context) -> dict[str, Any]:
        """Return a script and client-specific instructions for listening for Call agent.

        Run the returned script using the how field, selected for the connected
        client. Reuse the process after handling each review event.
        """
        try:
            client = binding.require_client()
        except ProjectSetupError as error:
            raise RuntimeError(
                f"{error}. If another project holds the port, propose a free port to the user, "
                "edit port in that config after they agree, and call listen() again."
            ) from error
        state = await client.request_json("GET", "/state")
        port = state["port"]
        # The server keeps the press count and the consumption watermark, so the script
        # carries no state of its own: a press made before this call answers it at once,
        # and after a line is delivered the loop parks again rather than replaying the
        # press it acked, so one monitor serves every press of the session. The ack comes
        # after the line is printed: consuming before delivery lost the wake-up whenever
        # the response died on the wire, so a press is offered until a waiter confirms it
        # landed, and delivery is at-least-once.
        script = (
            "#!/bin/sh\n"
            "thread=\n"
            "if [ \"${1-}\" = \"--codex\" ]; then\n"
            "  thread=${2:?Pass the Codex thread ID}\n"
            "  command -v codex >/dev/null || exit 1\n"
            "fi\n"
            "deliver() {\n"
            "  if [ -n \"$thread\" ]; then\n"
            "    until codex queue --thread \"$thread\" --message \"[HTML review event]\n"
            "$1\"; do\n"
            "      printf '%s\\n' 'Queue delivery failed; retrying in 5 seconds' >&2\n"
            "      sleep 5\n"
            "    done\n"
            "  else\n"
            "    printf '%s\\n' \"$1\"\n"
            "  fi\n"
            "}\n"
            f"# Prints one line each time the reviewer presses 'Call agent' on http://127.0.0.1:{port},\n"
            "# at once if an unacknowledged press is waiting, and keeps waiting for the next. A server\n"
            "# that goes away is waited for too: one [gone] line, then [back] when it answers again.\n"
            "headers=$(mktemp) || exit 1\n"
            "trap 'rm -f \"$headers\"' EXIT\n"
            "gone=0\n"
            "delay=2\n"
            "while :; do\n"
            f"  out=$(curl -sf -D \"$headers\" --max-time 60 \"http://127.0.0.1:{port}/wait-review\"); rc=$?\n"
            "  if [ $gone -eq 1 ] && { [ $rc -eq 0 ] || [ $rc -eq 28 ]; }; then\n"
            "    deliver '[back] review server reachable again'; gone=0; delay=2\n"
            "  fi\n"
            "  if [ $rc -eq 0 ] && [ -n \"$out\" ]; then\n"
            "    deliver \"$out\"\n"
            "    press=$(tr -d '\\r' < \"$headers\" | sed -n 's/^[Xx]-[Pp]ress: *//p' | head -1)\n"
            f"    [ -n \"$press\" ] && curl -sf -X POST \"http://127.0.0.1:{port}/wait-review/ack?upto=$press\" >/dev/null\n"
            "  fi\n"
            "  if [ $rc -ne 0 ] && [ $rc -ne 28 ]; then\n"
            "    if [ $gone -eq 0 ]; then deliver \"[gone] review server unreachable (curl exit $rc); waiting for it\"; gone=1; fi\n"
            "    sleep $delay\n"
            "    [ $delay -lt 30 ] && delay=$((delay * 2))\n"
            "  fi\n"
            "done\n"
        )
        # Replaced atomically so a waiter started from the previous script keeps reading
        # the file it opened.
        directory = Path(state["project_dir"]) / ".html-mcp-web"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "wait-review.sh"
        staging = directory / "wait-review.sh.new"
        staging.write_text(script, encoding="utf-8")
        staging.chmod(0o755)
        staging.replace(target)
        return {
            "script": str(target),
            "how": (
                _wait_method(ctx)
                + " Start another copy only after the previous process has ended. "
                "On [review], call read_comments(new=True) for the reported artifact and handle the review. "
                "[gone] means the review server is unreachable; the script keeps retrying. "
                "[back] means it is reachable again."
            ),
        }

    return mcp


def _cursor_path(project_dir: Path) -> Path:
    return project_dir / ".html-mcp-web" / "agent-cursor.json"


def read_cursor(project_dir: Path, artifact: str) -> str | None:
    """The exact stamp of the newest entry read_comments(new=True) handed over, or None."""
    path = _cursor_path(project_dir)
    if not path.exists():
        return None
    cursors = json.loads(path.read_text(encoding="utf-8"))
    return cursors[artifact] if artifact in cursors else None


def write_cursor(project_dir: Path, artifact: str, at: str) -> None:
    path = _cursor_path(project_dir)
    cursors = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    cursors[artifact] = at
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".new")
    staging.write_text(json.dumps(cursors), encoding="utf-8")
    staging.replace(path)


def main(start_dir: Path) -> None:
    _check_dependencies()
    binding = ProjectBinding(start_dir)
    try:
        binding.connect()
    except ProjectSetupError as error:
        print(f"html-mcp project is not ready: {error}", file=sys.stderr)
    server = create_server(binding)
    try:
        server.run(transport="stdio")
    finally:
        binding.stop()
