"""MCP tools for reviewing project HTML artifacts."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlencode

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
        instructions=(
            "Call inspect() first, then read only the artifact, comments, and pages needed, reusing results while "
            "revision is unchanged. Find new comments with list_comments(unanswered=True) or since=<the largest "
            "last_human_at already handled>, not by re-reading the open list. inspect(artifact) reports the "
            "layout_check: completion requires checked_revision == revision and no errors, and those errors are the "
            "fit failures. Fit is settled by numbers, so measure_space(target=<block ref>) gives line_count, "
            "last_line_right_space, and a table's min_no_wrap_width, the pixels to trim or add. render_page carries "
            "what numbers do not (figure placement, a crop, colour); run it once per page when that changes and once "
            "before hand-off, not after each edit. When the page is for the user to look at rather than for you, "
            "render_page(save=True) writes the png and returns its path, which costs none of the tokens the image "
            "itself would. Resolve only alongside the edit the comment asked for; a comment "
            "answered with words alone stays open for its owner to close, and a resolve message is unnecessary when "
            "replies or edited_files already record the outcome. edit_file is the source; for a templated artifact "
            "main_file is build output and is not edited. Link images with a relative src into a project folder; do "
            "not embed them as base64, so content stays small and editable. The content format and component "
            "vocabulary are in templates/README.md beside the package (a skin's own README covers only what that skin "
            "changes); read it before writing content. The project is watched with inotify, one watch per "
            "directory under it, and the per-user watch limit is shared by every session on the host; a large tree "
            "that holds no artifact content (checkpoints, a baseline dump, a dataset) goes in the config's ignore "
            "list by its top-level directory name, or the project server fails to start with 'inotify watch limit "
            "reached' for this session and every other one."
        ),
    )

    @mcp.tool()
    async def inspect(
        artifact: str | None = None,
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
    ) -> "Image":
        """Render one page for visual inspection, or with save, to a png file to hand to the user."""
        client = binding.require_client()
        params = f"?page={page}&dpi={dpi}&gray={'1' if grayscale else '0'}"
        data = await client.get_bytes(
            f"/artifacts/{artifact}/render/page{params}",
            timeout=120.0,
        )
        if not save:
            return Image(data=data, format="png")
        project_dir = Path((await client.request_json("GET", "/state"))["project_dir"])
        target = ((project_dir / out) if out is not None
                  else project_dir / ".html-mcp-web" / "renders" / f"{artifact}-p{page}.png").resolve()
        if not target.is_relative_to(project_dir.resolve()):
            raise ValueError("out must stay inside the project directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return {"path": str(target), "bytes": len(data), "page": page, "dpi": dpi}

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
        revision: Annotated[int, Field(ge=1, description="Current revision from inspect(); space is ready when space_revision equals it.")],
        clearance: Annotated[float, Field(ge=0, description="Page pixels kept clear around existing content when free regions are computed; 0 to measure exactly.")],
        target: Annotated[str | None, Field(description="A block ref from a previous result's children (e.g. p1:0.2), including a table cell ref, to measure inside that block instead of the page.")] = None,
        min_width: Annotated[float | None, Field(ge=0, description="Keep only free regions at least this wide, in page pixels.")] = None,
        min_height: Annotated[float | None, Field(ge=0, description="Keep only free regions at least this tall, in page pixels.")] = None,
    ) -> dict[str, Any]:
        """Measure where the space is, in page pixels. Without target: page bounds, top-level block refs, and the largest free rectangles. With target: that block's content bounds, how far its content sits from each edge, its children, and its text lines; a table adds no-wrap width constraints, an SVG reports the area its shapes cover. Drill down by passing a child's ref as the next target."""
        client = binding.require_client()
        query: dict[str, Any] = {
            "page": page,
            "revision": revision,
            "clearance": clearance,
        }
        if target is not None:
            query["target"] = target
        if min_width is not None:
            query["min_width"] = min_width
        if min_height is not None:
            query["min_height"] = min_height
        return await client.request_json("GET", f"/artifacts/{artifact}/space?{urlencode(query)}")

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
