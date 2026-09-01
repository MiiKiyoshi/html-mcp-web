"""MCP tools for reviewing project HTML artifacts."""

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
)


try:
    from mcp.server.fastmcp import FastMCP, Image
    from pydantic import BaseModel, ConfigDict, Field

    from .mcp_client import ProjectBinding, ProjectSetupError

    HAS_MCP = True
except ImportError:
    HAS_MCP = False


if HAS_MCP:
    class Reply(BaseModel):
        """A message written for one thread."""

        model_config = ConfigDict(extra="forbid")

        comment_id: Annotated[str, Field(min_length=1)]
        message: Annotated[str, Field(min_length=1)]


def _check_dependencies() -> None:
    if HAS_MCP:
        return
    print("html-mcp requires the mcp and httpx packages. Install html-mcp-web[mcp].", file=sys.stderr)
    raise SystemExit(1)


def create_server(binding: "ProjectBinding") -> "FastMCP":
    _check_dependencies()
    mcp = FastMCP(
        "html-mcp-web",
        # A client may cut this text off: Claude Code delivers about 2,300 characters, and
        # the rest reached no agent at all. What stays here is what is needed before the
        # first call; the rest is one field of the inspect() an agent starts with anyway.
        instructions=(
            "Call inspect() with no arguments first: it returns a guide field with the rules for reading "
            "a layout check, measuring space, rendering, and writing content, which inspect(artifact) "
            "leaves out. Read only the artifact, comments and pages needed, reusing results while revision "
            "is unchanged, and find new comments with list_comments(unanswered=True) or "
            "list_comments(since=<the largest last_human_at already handled>). "
            "edit_file is the source; for a templated artifact main_file is build output and is not "
            "edited. Saving edit_file triggers the rebuild and bumps the revision, so build.py is never "
            "run by hand, and inspect(artifact) after it reports the new revision and how far the check "
            "has caught up. The content format and components are in templates/README.md beside the "
            "package; a skin's own README, in the template_dir inspect(artifact) reports, covers only what "
            "that skin changes. "
            "Completion is layout_check.checked_revision == revision with no errors, and each error ends "
            "with the ref of the block it is about, which measure_space(target=<ref>) and "
            "render_page(target=<ref>) both take. Make the edit, reply with what changed and why, record "
            "edited_files, and leave the comment open: closing it hides the reasoning the reviewer reads "
            "to judge the fix, and the reviewer closes the batch with Resolve all. set_comment_status is "
            "for a comment that asks for no edit, not for signing off your own work. Then call "
            "wait_review() and start the script it returns in the background (Claude Code: Monitor) and "
            "end the turn: it exits when the reviewer presses Call agent, the harness's completion "
            "notification wakes you, and list_comments(unanswered=True) picks up from there. Waiting that "
            "way costs no tokens, so prefer it to polling for comments."
        ),
    )

    # The working rules, kept here rather than in the server instructions because a client
    # may cut those off before the end. They ride on the discovery call, which is made once,
    # and stay off every later inspect(artifact).
    GUIDE = {
        "layout_check": (
            "checked_revision == revision and no errors is the fit bar. An error names the block that "
            "spills and ends with its ref; where the page still has room comes back beside the errors as "
            "layout_check.room, and a block not tied to its column (a footnote, a shared definition, a "
            "result line) moves there before anything is trimmed."
        ),
        "measure_space": (
            "No errors is not the same as a page that reads well. measure_space(target=<ref>) on the block "
            "that fills most of the page settles the rest: line_count and last_line_right_space are the "
            "pixels to trim or add, edge_space is the gap to each side of the block, a table adds "
            "min_no_wrap_width, and unused_ratio is the share of the block's box nothing is drawn in."
        ),
        "render_page": (
            "The check does not judge whether a drawing is right: that a wire reaches the part it is drawn "
            "to, that a curve matches the formula beside it. render_page carries what numbers do not "
            "(figure placement, a crop, colour). render_page(target=<ref>) crops to one block for a fraction "
            "of a page's tokens, dpi=150 shows fine detail, and save=True writes a png for the user to look "
            "at without the image entering the transcript. Run it when what it carries changed and once "
            "before hand-off, not after each edit."
        ),
        "images": (
            "Link images with a relative src into a project folder; do not embed them as base64, so content "
            "stays small and editable."
        ),
        "watching": (
            "The project is watched with inotify, one watch per directory under it, and the per-user watch "
            "limit is shared by every session on the host. A large tree that holds no artifact content "
            "(checkpoints, a baseline dump, a dataset) goes in the config's ignore list by its top-level "
            "directory name, or the project server fails to start with 'inotify watch limit reached' for "
            "this session and every other one."
        ),
    }

    @mcp.tool()
    async def inspect(
        artifact: str | None = None,
    ) -> dict[str, Any]:
        """Discover compact project state with the working guide, or inspect one artifact without comment threads."""
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
        project_dir = Path(state["project_dir"])
        result = (
            {artifact: agent_artifact(artifact, artifacts[artifact], project_dir)}
            if artifact is not None
            else {artifact_id: agent_artifact_summary(artifact_id, value) for artifact_id, value in artifacts.items()}
        )
        return {
            "config_path": state["config_path"],
            "project_dir": state["project_dir"],
            "review_url": f"http://127.0.0.1:{state['port']}",
            **({} if artifact is not None else {"guide": GUIDE}),
            "artifacts": result,
        }

    @mcp.tool()
    async def list_comments(
        artifact: str,
        status: Literal["open", "resolved", "dismissed", "all"] = "open",
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
        replies: Annotated[list[Reply], Field(min_length=1, description="One entry per thread: the comment and the message written for it.")],
        edited_files: Annotated[list[str] | None, Field(description="Project-relative paths edited for these comments; recorded on each thread entry.")] = None,
    ) -> dict[str, Any]:
        """Reply to comments without changing their status."""
        ids = [reply.comment_id for reply in replies]
        if len(set(ids)) != len(ids):
            raise ValueError("each comment appears at most once in replies")
        client = binding.require_client()
        updated: list[dict[str, Any]] = []
        for reply in replies:
            result = await client.request_json("POST", f"/artifacts/{artifact}/comments/update", {
                "comment_ids": [reply.comment_id],
                "message": reply.message,
                **({"edited_files": edited_files} if edited_files is not None else {}),
            })
            updated.extend(result["updated"])
        return {"updated": updated}

    @mcp.tool()
    async def set_comment_status(
        artifact: str,
        comment_ids: list[str],
        status: Literal["open", "resolved", "dismissed"],
        message: str = "",
        edited_files: Annotated[list[str] | None, Field(description="Project-relative paths edited for these comments; recorded on the thread entry.")] = None,
    ) -> dict[str, Any]:
        """Change status after verification. A message posts to every id, so batch with one only when it fits each thread."""
        if not comment_ids:
            raise ValueError("comment_ids must not be empty")
        client = binding.require_client()
        return await client.request_json("POST", f"/artifacts/{artifact}/comments/update", {
            "comment_ids": comment_ids,
            "status": status,
            "message": message,
            **({"edited_files": edited_files} if edited_files is not None else {}),
        })

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
        """Write the slides artifact as an editable pptx: text blocks become text boxes, tables become tables, images stay images, KaTeX becomes a screenshot, and inline SVG stays vector. A skin's pptx block in skin.json can name TrueType files to embed the deck font."""
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
    async def wait_review() -> dict[str, Any]:
        """Arm the reviewer's Call agent button and return at once with a waiter script. Start that script with the harness's background facility (Claude Code: Monitor) and end the turn; the script exits the moment the reviewer presses the button, and the harness's completion notification is the wake-up. Costs nothing while waiting."""
        client = binding.require_client()
        state = await client.request_json("GET", "/state")
        port = state["port"]
        calls = state["review"]["calls"]
        script = (
            "#!/bin/sh\n"
            f"# Exits when the reviewer presses 'Call agent' on http://127.0.0.1:{port}\n"
            f"since={calls}\n"
            "tries=0\n"
            "while [ $tries -lt 60 ]; do\n"
            f"  out=$(curl -sf --max-time 60 \"http://127.0.0.1:{port}/wait-review?since=$since\"); rc=$?\n"
            "  if [ $rc -eq 0 ] && [ -n \"$out\" ]; then printf '%s\\n' \"$out\"; exit 0; fi\n"
            "  if [ $rc -ne 0 ] && [ $rc -ne 28 ]; then printf '[gone] review server unreachable (curl exit %s)\\n' $rc; exit 1; fi\n"
            "  tries=$((tries + 1))\n"
            "done\n"
            "printf '[timeout] no review call within an hour; call wait_review again to keep waiting\\n'\n"
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
                "Run the script with the harness's background completion facility and end the turn: on "
                "Claude Code, Monitor(command=<script>, description='waiting for the reviewer', "
                "timeout_ms=3900000). It prints one line and exits: [review] means comments are ready, "
                "so continue with list_comments(unanswered=True); [timeout] after an hour means call "
                "wait_review again if still waiting; [gone] means the review server stopped. Without a "
                "background facility, running it with a shell tool blocks until the button is pressed."
            ),
        }

    return mcp


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
