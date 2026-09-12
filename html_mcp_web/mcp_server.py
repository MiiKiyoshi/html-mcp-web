"""MCP tools for reviewing project HTML artifacts."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import quote, urlencode

from .mcp_contract import (
    agent_artifact,
    agent_artifact_summary,
    agent_comment,
    agent_comment_summary,
    is_after,
    is_unanswered,
    parse_replies,
)


try:
    from mcp.server.fastmcp import Context, FastMCP, Image
    from pydantic import Field

    from .mcp_client import ProjectBinding, ProjectSetupError

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


def create_server(binding: "ProjectBinding") -> "FastMCP":
    _check_dependencies()
    guideline_resource_uri = "html-mcp://guideline/configured"
    mcp = FastMCP(
        "html-mcp-web",
        # Keep static operating rules in initialization. inspect() is called repeatedly
        # for project state and must not carry the same guide in every discovery result.
        instructions=(
            "Call inspect() with no arguments once to discover stable artifact paths and any configured "
            "guideline; later use inspect(artifact=...) for dynamic state. If the user mentions the "
            "guideline or authoring requires it, read its path once; a client without filesystem access "
            "reads its resource_uri. For the first templated-artifact authoring call use docs=True, then "
            "omit docs. Pass page only for that page's layout errors and room. Within explicit permission, "
            "process comments by reading requests, editing, verifying the rendered result, and replying in "
            "their threads. On each new connection call wait_review() and follow how; do not poll or "
            "duplicate its waiter. Before editing a "
            "reader-facing unit, define the reader’s prior knowledge, intended understanding, visible "
            "structure, and exclusions; reuse exact keys and order across comparison and result units, "
            "keep preliminary units to prerequisites while preserving and annotating source examples, "
            "and rebuild after two related comprehension failures."
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

    @mcp.tool()
    async def inspect(
        artifact: str | None = None,
        docs: Annotated[bool, Field(description="With an artifact: add its content format and components (the templates' README and the skin's own), read once before writing content.")] = False,
        page: Annotated[int | None, Field(ge=1, description="With an artifact: add only this page's layout errors and available-room regions.")] = None,
    ) -> dict[str, Any]:
        """Discover compact project state, or inspect one artifact without comment threads."""
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
        if artifact is None and (docs or page is not None):
            raise ValueError("docs and page require artifact")
        project_dir = Path(state["project_dir"])
        if artifact is None:
            guideline = state.get("guideline")
            return {
                "config_path": state["config_path"],
                "project_dir": state["project_dir"],
                "review_url": f"http://127.0.0.1:{state['port']}",
                "guideline": ({**guideline, "resource_uri": guideline_resource_uri}
                              if guideline is not None else None),
                "artifacts": {
                    artifact_id: agent_artifact_summary(artifact_id, value, project_dir)
                    for artifact_id, value in artifacts.items()
                },
            }
        return {
            "artifacts": {artifact: agent_artifact(artifacts[artifact], page)},
            **({"docs": template_docs(artifacts[artifact])} if docs else {}),
        }

    @mcp.tool()
    async def list_comments(
        artifact: str,
        status: Literal["open", "resolved", "all"] = "open",
        unanswered: Annotated[bool, Field(description="Only comments whose latest thread entry is the human's: not yet answered, or written to again after the agent's reply.")] = False,
        since: Annotated[str | None, Field(description="ISO 8601 time; only comments whose latest human entry is after it. Pass the largest last_human_at seen so far.")] = None,
    ) -> dict[str, Any]:
        """List compact comment requests without anchors or thread history."""
        client = binding.require_client()
        query = "" if status == "all" else f"?status={status}"
        payload = await client.request_json("GET", f"/artifacts/{artifact}/comments{query}")
        comments = payload["comments"]
        if unanswered:
            comments = [comment for comment in comments if is_unanswered(comment)]
        if since is not None:
            cutoff = datetime.fromisoformat(since)
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=timezone.utc)
            comments = [comment for comment in comments if is_after(comment, cutoff)]
        return {
            "artifact": artifact,
            "comments": [agent_comment_summary(comment) for comment in comments],
        }

    @mcp.tool()
    async def read_comments(artifact: str, comment_ids: list[str]) -> dict[str, Any]:
        """Read full anchors and threads for explicitly selected comment IDs."""
        if not comment_ids:
            raise ValueError("comment_ids must not be empty")
        if len(set(comment_ids)) != len(comment_ids):
            raise ValueError("comment_ids must be unique")
        client = binding.require_client()
        comments = []
        for comment_id in comment_ids:
            comment = await client.request_json("GET", f"/artifacts/{artifact}/comments/{comment_id}")
            comments.append(agent_comment(comment))
        return {"artifact": artifact, "comments": comments}

    @mcp.tool()
    async def reply_comments(
        artifact: str,
        replies_text: Annotated[str, Field(min_length=1, description=(
            "The replies as one text. Each starts at a line head with its comment id and a colon "
            "('c-1a2b3c4d: ') and runs to the next such line head, blank lines and all; a colon "
            "elsewhere is just a colon. Written as prose, as it is."))],
        edited_files: Annotated[list[str] | None, Field(description="Project-relative paths edited for these comments; recorded on each thread entry.")] = None,
    ) -> dict[str, Any]:
        """Reply to comments without changing their status."""
        replies = parse_replies(replies_text)
        client = binding.require_client()
        updated: list[dict[str, Any]] = []
        notes: list[str] = []
        for comment_id, message in replies:
            result = await client.request_json("POST", f"/artifacts/{artifact}/comments/update", {
                "comment_ids": [comment_id],
                "message": message,
                **({"edited_files": edited_files} if edited_files is not None else {}),
            })
            updated.extend(result["updated"])
            # Where the quoted text is still in the artifact unchanged after an edit was
            # reported for it: normal for a fix that landed elsewhere, a place to look otherwise.
            if "note" in result:
                notes.append(result["note"])
        return {"updated": updated, **({"notes": notes} if notes else {})}

    @mcp.tool()
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

    @mcp.tool()
    async def export_pptx(
        artifact: str,
        out: Annotated[str | None, Field(description="Project-relative path of the pptx to write; default export/<artifact>.pptx.")] = None,
    ) -> dict[str, Any]:
        """Write the slides artifact as an editable pptx: text blocks become text boxes, tables become tables, images stay images, KaTeX becomes a screenshot, inline SVG stays vector, and a slide's speaker script becomes its notes. A skin's pptx block in skin.json can name TrueType files to embed the deck font."""
        client = binding.require_client()
        return await client.request_json(
            "POST", f"/artifacts/{artifact}/export/pptx", {"out": out} if out is not None else {}, timeout=300.0)

    @mcp.tool()
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

    @mcp.tool()
    async def wait_review(ctx: Context) -> dict[str, Any]:
        """Return a script and client-specific instructions for waiting on Call agent.

        Run the returned script using the how field, selected for the connected
        client. Reuse the process after handling each review event.
        """
        client = binding.require_client()
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
                "On [review], read list_comments(unanswered=True) for the reported artifact and handle the review. "
                "[gone] means the review server is unreachable; the script keeps retrying. "
                "[back] means it is reachable again."
            ),
        }

    return mcp


def template_docs(artifact: dict[str, Any]) -> dict[str, Any]:
    """The content format and the components of a templated artifact: the templates' README
    and the skin's own where it has one, as text, so a client without file tools has them
    too. An artifact with no template has nothing to read."""
    if "template" not in artifact:
        return {"template": None, "readme": None, "skin_readme": None}
    readme = Path(__file__).resolve().parent.parent / "templates" / "README.md"
    skin_readme = Path(artifact["template_dir"]) / "README.md"
    return {
        "template": artifact["template"],
        "readme": readme.read_text(encoding="utf-8") if readme.is_file() else None,
        "skin_readme": skin_readme.read_text(encoding="utf-8") if skin_readme.is_file() else None,
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
