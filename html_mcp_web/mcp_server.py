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
    agent_artifact,
    agent_artifact_summary,
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
    guideline_resource_uri = "html-mcp://guideline/configured"
    mcp = FastMCP(
        "html-mcp-web",
        instructions=(
            "Call inspect() once for paths and document references; reuse until configuration changes. "
            "Read authoring, template notes and any configured guideline only when needed, by path or "
            "resource_uri. Use inspect(artifact=..., page=...) for current state. "
            "Work from read_comments(new=True); pass comment_ids only to reread a whole thread. Within the user's editing scope, edit, render affected pages, and reply in the "
            "threads; the reviewer resolves them. Call listen() when the user asks to listen and follow "
            "how; reuse its process, do not poll or duplicate it. "
            f"Setup: read {INIT_GUIDE}. "
            "Treat overflow, clipping, and text-tail warnings as geometric unless the user or a "
            "visual audit finds a content problem. First preserve content and structure with the "
            "smallest size or spacing change. Do not rewrite, remove, or reorganize content just "
            "to clear a warning. Use structural edits only if the geometric fix cannot work or "
            "the user requests them. Then rerun inspect and render only the affected page."
        ),
    )

    @mcp.resource(
        guideline_resource_uri,
        name="configured-guideline",
        description="The guideline configured for this HTML project, read only when needed.",
        mime_type="text/markdown",
    )
    async def configured_guideline() -> str:
        state = await binding.require_client().request_json("GET", "/state")
        guideline = state.get("guideline")
        if guideline is None:
            raise RuntimeError("this project has no configured guideline")
        return Path(guideline["path"]).read_text(encoding="utf-8")

    @mcp.resource("html-mcp://docs/{document}", mime_type="text/markdown")
    async def authoring_document(document: str) -> str:
        """Read the authoring guide or component reference when needed."""
        names = {"authoring": "README.md", "components": "COMPONENTS.md"}
        return (Path(__file__).resolve().parent.parent / "templates" / names[document]).read_text(encoding="utf-8")

    @mcp.resource("html-mcp://templates/{artifact}", mime_type="text/markdown")
    async def template_document(artifact: str) -> str:
        """Read the configured artifact's template-specific notes."""
        state = await binding.require_client().request_json("GET", "/state")
        return (Path(state["artifacts"][artifact]["template_dir"]) / "README.md").read_text(encoding="utf-8")

    @mcp.tool(structured_output=False)
    @_compact
    async def inspect(
        artifact: str | None = None,
        page: Annotated[int | None, Field(ge=1, description="With an artifact: add only this page's layout errors and available-room regions.")] = None,
    ) -> dict[str, Any]:
        """Discover paths and document references, or inspect current artifact state.

        layout_error_count is null until the current revision is checked; zero means
        that revision has no layout errors. Pass page for local errors and room.
        """
        try:
            client = binding.connect()
        except ProjectSetupError as error:
            return binding.setup_error_state(error)
        if client is None:
            return binding.setup_state()
        state = await client.request_json("GET", "/state")
        artifacts = state["artifacts"]
        if artifact is not None and artifact not in artifacts:
            raise RuntimeError(f"unknown artifact: {artifact}; available artifacts: {', '.join(artifacts)}")
        if artifact is None and page is not None:
            raise ValueError("page requires artifact")
        project_dir = Path(state["project_dir"])
        if artifact is None:
            guideline = state.get("guideline")
            return {
                "config_path": state["config_path"],
                "project_dir": state["project_dir"],
                "guideline": ({**guideline, "resource_uri": guideline_resource_uri}
                              if guideline is not None else None),
                "documents": document_references(artifacts),
                "artifacts": {
                    artifact_id: agent_artifact_summary(artifact_id, value, project_dir)
                    for artifact_id, value in artifacts.items()
                },
            }
        return {
            "artifacts": {artifact: agent_artifact(artifacts[artifact], page)},
        }

    @mcp.tool(structured_output=False)
    @_compact
    async def list_comments(
        artifact: str,
        status: Literal["open", "resolved", "reference", "all"] = "open",
        unanswered: Annotated[bool, Field(description="Only comments whose latest thread entry is the human's: not yet answered, or written to again after the agent's reply.")] = False,
        since: Annotated[str | None, Field(description="'MM-DD HH:MM'; only comments whose latest human entry is in or after that minute. Pass the largest last_human_at seen so far.")] = None,
    ) -> dict[str, Any]:
        """List comment requests, newest first, without thread history."""
        client = binding.require_client()
        query = "" if status == "all" else f"?status={status}"
        payload = await client.request_json("GET", f"/artifacts/{artifact}/comments{query}")
        comments = payload["comments"]
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
    async def read_comments(
        artifact: str,
        comment_ids: list[str] | None = None,
        new: Annotated[bool, Field(description=(
            "Instead of comment_ids: on open threads, what the reviewer wrote that this has "
            "neither handed over before nor seen you answer. Reports from and cursor; a turn "
            "that went wrong is taken again with since=<from>."))] = False,
        since: Annotated[str | None, Field(description="With new: 'MM-DD HH:MM'; read from that minute instead of the cursor.")] = None,
        save: bool = False,
    ) -> dict[str, Any]:
        """Read what is new, or selected threads whole; save writes the selected threads as a
        Markdown draft and returns its path. Edit only its Reply and Edit blocks."""
        client = binding.require_client()
        if new:
            if comment_ids is not None or save:
                raise ValueError("new answers on its own; it takes no comment_ids and writes no draft")
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
        if since is not None:
            raise ValueError("since goes with new")
        if not comment_ids:
            raise ValueError("give comment_ids, or new=True")
        if len(set(comment_ids)) != len(comment_ids):
            raise ValueError("comment_ids must be unique")
        if save:
            return await client.request_json("POST", f"/artifacts/{artifact}/comments/export", {"comment_ids": comment_ids})
        comments = []
        for comment_id in comment_ids:
            comment = await client.request_json("GET", f"/artifacts/{artifact}/comments/{comment_id}")
            comments.append(agent_comment(comment))
        return {"artifact": artifact, "comments": comments}

    @mcp.tool(structured_output=False)
    @_compact
    async def reply_comments(
        artifact: str,
        replies_text: Annotated[str | None, Field(min_length=1, description=(
            "The replies as one text. Each starts at a line head with its comment id and a colon "
            "('c-1a2b3c4d: ') and runs to the next such line head, blank lines and all; a colon "
            "elsewhere is just a colon. Written as prose, as it is."))] = None,
        edited_files: Annotated[list[str] | None, Field(description="Project-relative paths edited for these comments; recorded on each thread entry.")] = None,
        replies_file: str | None = None,
        edits_text: Annotated[str | None, Field(description=(
            "Rewrites of your own earlier entries, as one text: each starts at a line head with "
            "the comment id, /, the entry id, @, the comment's rev as read, and a colon "
            "('c-1a2b3c4d/e-5e6f7a8b@9f8e7d6c: ') and runs to the next such head. "
            "Refused if the thread changed since."))] = None,
    ) -> dict[str, Any]:
        """Reply without changing status, or rewrite your own entries. Use replies_text and/or
        edits_text, or a saved draft's replies_file (which carries both) on its own."""
        if replies_file is not None and (replies_text is not None or edits_text is not None):
            raise ValueError("replies_file carries replies and edits itself; give it alone")
        if replies_file is None and replies_text is None and edits_text is None:
            raise ValueError("provide replies_text, edits_text or replies_file")
        if replies_file is not None:
            client = binding.require_client()
            result = await client.request_json("POST", f"/artifacts/{artifact}/comments/update", {
                "replies_file": replies_file,
                **({"edited_files": edited_files} if edited_files is not None else {}),
            })
            return {"updated": _revisions(result), **({"notes": [result["note"]]} if "note" in result else {})}
        client = binding.require_client()
        updated: list[dict[str, Any]] = []
        notes: list[str] = []
        if edits_text is not None:
            rewrites = parse_entry_edits(edits_text)
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
            updated.extend(_revisions(result))
        replies = parse_replies(replies_text) if replies_text is not None else []
        for comment_id, message in replies:
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
    async def render_page(
        artifact: str,
        page: Annotated[int, Field(ge=1)],
        dpi: Annotated[int, Field(ge=36, le=300, description="Render resolution; 96 reads text, 150 or more shows fine detail at a higher token cost.")] = 96,
        grayscale: Annotated[bool, Field(description="Grayscale is smaller and enough for layout; set false when colour itself is being checked.")] = True,
        save: Annotated[bool, Field(description="Write the png and return its path instead of the image, for showing a page to the user without spending the tokens an image costs.")] = False,
        out: Annotated[str | None, Field(description="Project-relative png path used when save is set; default .html-mcp-web/renders/<artifact>-p<page>.png.")] = None,
        target: Annotated[str | None, Field(description="A block ref on this page (e.g. p8:1.1.0.2, as layout errors and measure_space report them) to render just that block with a small margin, at a fraction of a full page's tokens. Needs the layout check to have run for the current revision.")] = None,
    ) -> "Image":
        """Render one page (or with target, one block of it) for visual inspection, or with save, to a png file to hand to the user."""
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
    async def export_pptx(
        artifact: str,
        out: Annotated[str | None, Field(description="Project-relative path of the pptx to write; default export/<artifact>.pptx.")] = None,
    ) -> dict[str, Any]:
        """Write the slides artifact as an editable pptx: text blocks become text boxes, tables become tables, images stay images, KaTeX becomes a screenshot, inline SVG stays vector, and a slide's speaker script becomes its notes. A skin's pptx block in skin.json can name TrueType files to embed the deck font."""
        client = binding.require_client()
        return await client.request_json(
            "POST", f"/artifacts/{artifact}/export/pptx", {"out": out} if out is not None else {}, timeout=300.0)

    @mcp.tool(structured_output=False)
    @_compact
    async def measure_space(
        artifact: str,
        page: Annotated[int, Field(ge=1)],
        clearance: Annotated[float, Field(ge=0, description="Page pixels kept clear around existing content when free regions are computed; 0 to measure exactly.")],
        revision: Annotated[int | None, Field(ge=1, description="Revision the measurement must belong to, from inspect(); omitted, the current one is measured without an inspect round to learn its number.")] = None,
        target: Annotated[str | None, Field(description="A block ref from a previous result's children (e.g. p1:0.2), including a table cell ref, to measure inside that block instead of the page.")] = None,
        min_width: Annotated[float | None, Field(ge=0, description="Keep only free regions at least this wide, in page pixels.")] = None,
        min_height: Annotated[float | None, Field(ge=0, description="Keep only free regions at least this tall, in page pixels.")] = None,
    ) -> dict[str, Any]:
        """Measure where the space is, in page pixels. Without target: page bounds, top-level block refs, and the largest free rectangles. With target: that block's content bounds, how far its content sits from each edge, its children, and its text lines; a table adds no-wrap width constraints, an SVG reports the area its shapes cover. Drill down by passing a child's ref as the next target."""
        client = binding.require_client()
        query: dict[str, Any] = {
            "page": page,
            "clearance": clearance,
        }
        if revision is not None:
            query["revision"] = revision
        if target is not None:
            query["target"] = target
        if min_width is not None:
            query["min_width"] = min_width
        if min_height is not None:
            query["min_height"] = min_height
        # Long enough for the server to run the layout check itself when no review UI is
        # open: it starts a headless browser on its own page and answers once that posts.
        return await client.request_json("GET", f"/artifacts/{artifact}/space?{urlencode(query)}", timeout=75.0)

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


def document_references(artifacts: dict[str, Any]) -> dict[str, Any]:
    """Discover each shared document once, without loading its text."""
    directory = Path(__file__).resolve().parent.parent / "templates"
    templates = {}
    for artifact_id, artifact in artifacts.items():
        if "template" not in artifact:
            continue
        path = Path(artifact["template_dir"]) / "README.md"
        if path.is_file():
            templates[artifact["template"]] = {
                "path": str(path), "resource_uri": f"html-mcp://templates/{artifact_id}",
            }
    return {
        "authoring": {"path": str(directory / "README.md"), "resource_uri": "html-mcp://docs/authoring"},
        "components": {"path": str(directory / "COMPONENTS.md"), "resource_uri": "html-mcp://docs/components"},
        "templates": templates,
    }


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
