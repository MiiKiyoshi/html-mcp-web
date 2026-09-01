"""aiohttp server for reviewing project HTML artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from aiohttp import WSMsgType, web

from .comments import Comment, CommentStore, anchor_from_dict
from .config import (
    ArtifactConfig,
    Config,
    get_content_file,
    get_main_file,
    get_project_dir,
    get_template_dir,
    load_config,
)
from .pdf_export import print_artifact_pdf
from .pptx_export import export_pptx
from .space import (
    intersection,
    maximal_free_regions,
    union_area,
    union_bbox,
    validated_space_pages,
)
from .watcher import Watcher


PRINT_PAGE_SIZES = {"slides": "13.333in 7.5in", "report": "A4 portrait"}
NO_CACHE = {"Cache-Control": "no-cache"}


def strip_script_blocks(source: str) -> str:
    """Remove the speaker-script blocks a slides template emits after its pages."""
    return re.sub(r'\s*<div class="script-block">.*?</div>\s*</div>', "", source, flags=re.S)


# A fit error names the block that spills; these are the ones a reader answers either by
# trimming that block or by moving something to where the page still has room.
FIT_ERROR = re.compile(r"^page (\d+) .*?(?:overflows its content area|wastes its last line|exceeds the)")
# Room worth naming: tall enough to take a line of text and wide enough to hold one.
ROOM_CLEARANCE = 8.0
ROOM_MIN_WIDTH = 80.0
ROOM_MIN_HEIGHT = 20.0
ROOM_MAX_BOXES = 120


def room_for_errors(errors: list[str], space_pages: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """The free rectangles on each page a fit error names, largest first.

    Reported beside the errors because the block that spills is not always the block to
    change: a page whose left column is 10px over may have 100px going spare under the
    right one.
    """
    pages = {page["number"]: page for page in space_pages}
    room: dict[str, list[dict[str, Any]]] = {}
    for error in errors:
        match = FIT_ERROR.match(error)
        if match is None:
            continue
        number = int(match.group(1))
        if str(number) in room or number not in pages:
            continue
        page = pages[number]
        scope_ref, scope = content_area(page)
        drawn = leaf_boxes(page, scope_ref)
        # The search over free rectangles grows steeply with the number of boxes, and this
        # runs inside the request that carries the whole measurement: a page that somehow
        # still arrives with hundreds of them is answered with the blocks one level down
        # rather than left to hold the server.
        if len(drawn) > ROOM_MAX_BOXES:
            children = page["children"] if scope_ref is None else page["nodes"][scope_ref]["children"]
            drawn = [(ref, page["nodes"][ref]["bbox"]) for ref in children]
        regions = maximal_free_regions(
            scope, [box for _, box in drawn], ROOM_CLEARANCE, ROOM_MIN_WIDTH, ROOM_MIN_HEIGHT)
        regions.sort(key=lambda box: box[2] * box[3], reverse=True)
        room[str(number)] = [
            {"bbox": [round(value, 2) for value in box],
             **({"below": ref} if (ref := block_above(box, drawn)) else {})}
            for box in regions[:3]
        ]
    return room


def content_area(page: dict[str, Any]) -> tuple[str | None, list[float]]:
    """The box on the page that content is written into.

    Measured against the whole page, the title bar and the body box fill it between them
    and nothing reads as free, while the room the writer can use is inside the body. The
    body is the largest top-level block that holds other blocks.
    """
    best: tuple[float, str] | None = None
    for ref in page["children"]:
        node = page["nodes"][ref]
        if not node["children"]:
            continue
        area = node["bbox"][2] * node["bbox"][3]
        if best is None or area > best[0]:
            best = (area, ref)
    if best is None:
        return None, page["bbox"]
    return best[1], page["nodes"][best[1]]["bbox"]


def leaf_boxes(page: dict[str, Any], scope_ref: str | None) -> list[tuple[str, list[float]]]:
    """What actually occupies the content area. A container is not an obstacle: its own box
    would cover the space its children leave between them.

    A figure, a table and a rendered formula are where the descent stops. Their insides are
    not places a block could be moved to, and a formula is built from hundreds of little
    spans: one page came to 719 boxes, and the free-region search, whose cost climbs steeply
    with them, held the server for minutes while no other request was served.
    """
    start = page["children"] if scope_ref is None else page["nodes"][scope_ref]["children"]
    found: list[tuple[str, list[float]]] = []
    stack = list(start)
    while stack:
        ref = stack.pop()
        node = page["nodes"][ref]
        whole = node["kind"] in ("object", "table") or "katex" in node["element"]
        if node["children"] and not whole:
            stack.extend(node["children"])
        else:
            found.append((ref, node["bbox"]))
    return found


def block_above(box: list[float], drawn: list[tuple[str, list[float]]]) -> str | None:
    """The block sitting directly over a free rectangle, which is what makes the rectangle
    findable on the page: "under the right column" rather than a pair of numbers."""
    left, top, width, _ = box
    best: tuple[float, str] | None = None
    for ref, (cx, cy, cw, ch) in drawn:
        overlap = min(left + width, cx + cw) - max(left, cx)
        gap = top - (cy + ch)
        if overlap < width / 2 or gap < 0 or gap > 40:
            continue
        if best is None or gap < best[0]:
            best = (gap, ref)
    return None if best is None else best[1]


def artifact_text(path: Path) -> str:
    """The artifact's readable text on one line, for comparing against anchor quotes."""
    source = path.read_text(encoding="utf-8")
    source = re.sub(r"<(script|style)\b.*?</\1>", " ", source, flags=re.S | re.I)
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", source)).split())


@dataclass
class ArtifactRuntime:
    artifact_id: str
    config: ArtifactConfig
    main_file: Path
    content_file: Path | None
    template_dir: Path | None
    store: CommentStore
    build_error: str | None = None
    revision: int = 1
    layout_revision: int | None = None
    layout_errors: list[str] = field(default_factory=list)
    layout_room: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    space_revision: int | None = None
    space_pages: list[dict[str, Any]] = field(default_factory=list)

    def digest(self) -> str:
        return hashlib.sha256(self.main_file.read_bytes()).hexdigest()

    def state(self) -> dict[str, Any]:
        comments = self.store.list()
        comment_counts = {
            status: sum(comment.status == status for comment in comments)
            for status in ("open", "resolved", "dismissed")
        }
        data: dict[str, Any] = {
            "id": self.artifact_id,
            "label": self.config.label,
            "layout": self.config.layout,
            "main_file": self.config.main,
            "artifact_digest": self.digest(),
            "revision": self.revision,
            "layout_check": {
                "checked_revision": self.layout_revision,
                "errors": list(self.layout_errors),
                # Where the page still has room, for the pages the errors name. A fit error
                # says which block spills, and a reader who only has that trims it; the
                # room may be in the other column.
                "room": {page: list(regions) for page, regions in self.layout_room.items()},
            },
            "space_revision": self.space_revision,
            "comment_counts": comment_counts,
        }
        if self.config.template is not None:
            data["template"] = self.config.template
            data["content_file"] = self.config.content
            data["template_dir"] = str(self.template_dir) if self.template_dir else None
            data["build_error"] = self.build_error
        return data

    def reset_layout(self) -> None:
        self.layout_revision = None
        self.layout_errors = []
        self.layout_room = {}
        self.space_revision = None
        self.space_pages = []

    def build(self) -> None:
        builder = self.template_dir / "build.py" if self.template_dir else None
        if builder is None or not builder.is_file():
            self.build_error = f"template builder not found: {builder}"
            return
        result = subprocess.run(
            [sys.executable, str(builder), str(self.content_file), str(self.main_file)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.build_error = None if result.returncode == 0 else (result.stderr or result.stdout).strip()[-2000:]


class HtmlReviewServer:
    # How long one long-poll request is held before it returns empty and the caller asks
    # again. Under the MCP client's own timeouts, and short enough that a stopped server
    # is noticed within a minute.
    REVIEW_POLL_TIMEOUT = 55.0

    def __init__(self, config: Config):
        self.config = config
        self.project_dir = get_project_dir(config).resolve()
        self.static_dir = Path(__file__).parent / "static"
        self.websockets: set[web.WebSocketResponse] = set()
        self.pdf_lock = asyncio.Lock()
        self.generated_paths: set[Path] = set()
        # The reviewer's call button. Presses are a monotonic count, so a press made
        # before anyone was waiting is not lost: the next wait sees count > since and
        # returns at once.
        self.review_calls = 0
        self.review_called = asyncio.Event()
        self.review_waiters = 0
        self.headless_check = asyncio.Lock()
        self.artifacts = self._create_artifacts(config)
        self.watcher = self._create_watcher(config)

    def _create_artifacts(self, config: Config) -> dict[str, ArtifactRuntime]:
        runtimes: dict[str, ArtifactRuntime] = {}
        for artifact_id, artifact in config.artifacts.items():
            comment_path = self.project_dir / ".html-mcp-web" / "comments" / f"{artifact_id}.json"
            runtime = ArtifactRuntime(
                artifact_id=artifact_id,
                config=artifact,
                main_file=get_main_file(config, artifact_id).resolve(),
                content_file=(get_content_file(config, artifact_id).resolve()
                              if get_content_file(config, artifact_id) is not None else None),
                template_dir=get_template_dir(config, artifact_id),
                store=CommentStore(comment_path),
            )
            if runtime.content_file is not None and runtime.content_file.is_file():
                if not runtime.main_file.is_file() or runtime.content_file.stat().st_mtime > runtime.main_file.stat().st_mtime:
                    runtime.build()
            if not runtime.main_file.is_file():
                raise FileNotFoundError(f"HTML artifact not found: {runtime.main_file}")
            runtimes[artifact_id] = runtime
        return runtimes

    def _create_watcher(self, config: Config) -> Watcher:
        return Watcher(self.project_dir, config.watch, config.ignore, self.on_project_change)

    def project_state(self) -> dict[str, Any]:
        return {
            "config_path": str(self.config.config_path),
            "project_dir": str(self.project_dir),
            "port": self.config.port,
            "review": {"calls": self.review_calls, "waiters": self.review_waiters},
            "artifacts": {artifact_id: runtime.state() for artifact_id, runtime in self.artifacts.items()},
        }

    def runtime(self, request: web.Request) -> ArtifactRuntime:
        artifact_id = request.match_info["artifact_id"]
        try:
            return self.artifacts[artifact_id]
        except KeyError as error:
            raise web.HTTPNotFound(text=f"unknown artifact: {artifact_id}") from error

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead: list[web.WebSocketResponse] = []
        encoded = json.dumps(message, ensure_ascii=False)
        for socket in self.websockets:
            try:
                await socket.send_str(encoded)
            except ConnectionError:
                dead.append(socket)
        for socket in dead:
            self.websockets.discard(socket)

    async def on_project_change(self, path: str) -> None:
        changed = Path(path).resolve()
        if changed == self.config.config_path:
            try:
                await self.apply_config()
            except (FileNotFoundError, TypeError, ValueError, yaml.YAMLError) as error:
                await self.broadcast({"type": "config_error", "error": str(error), **self.project_state()})
            return
        if changed in self.generated_paths:
            self.generated_paths.remove(changed)
            return
        affected: list[ArtifactRuntime] = []
        for runtime in self.artifacts.values():
            if runtime.content_file is not None and changed == runtime.content_file:
                previous_mtime = runtime.main_file.stat().st_mtime_ns if runtime.main_file.is_file() else None
                runtime.build()
                current_mtime = runtime.main_file.stat().st_mtime_ns if runtime.main_file.is_file() else None
                if runtime.build_error is None and current_mtime != previous_mtime:
                    self.generated_paths.add(runtime.main_file)
                affected.append(runtime)
            elif changed == runtime.main_file:
                affected.append(runtime)
        if not affected:
            affected = list(self.artifacts.values())
        for runtime in affected:
            runtime.revision += 1
            runtime.reset_layout()
        await self.broadcast({"type": "artifacts_changed", "path": str(changed.relative_to(self.project_dir)), **self.project_state()})

    async def index(self, request: web.Request) -> web.FileResponse:
        return web.FileResponse(self.static_dir / "index.html", headers=NO_CACHE)

    async def static(self, request: web.Request) -> web.FileResponse:
        target = (self.static_dir / request.match_info["name"]).resolve()
        if not target.is_relative_to(self.static_dir.resolve()) or not target.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(target, headers=NO_CACHE)

    def _artifact_html(self, runtime: ArtifactRuntime, for_print: bool = False) -> str:
        source = runtime.main_file.read_text(encoding="utf-8")
        if for_print:
            # Speaker scripts are screen-only. Hiding them with CSS is not enough for the
            # printer: a hidden block between pages made Firefox drop the background layer
            # of the page before it, so the print copy carries no script blocks at all.
            source = strip_script_blocks(source)
        page_size = PRINT_PAGE_SIZES[runtime.config.layout]
        css = self.static_dir / "artifact.css"
        css_version = int(css.stat().st_mtime) if css.is_file() else 0
        head_content = (
            '<base href="/project/">'
            f'<link rel="stylesheet" href="/static/artifact.css?v={css_version}">'
            f'<style id="html-mcp-page-style">@page {{ size: {page_size}; margin: 0; }}</style>'
        )
        source = re.sub(
            r"(<html\b)([^>]*>)",
            rf'\1 data-html-mcp-layout="{runtime.config.layout}"\2',
            source,
            count=1,
            flags=re.IGNORECASE,
        )
        if re.search(r"<head\b", source, flags=re.IGNORECASE):
            return re.sub(r"(<head\b[^>]*>)", rf"\1{head_content}", source, count=1, flags=re.IGNORECASE)
        return f"{head_content}{source}"

    async def artifact(self, request: web.Request) -> web.Response:
        for_print = request.query.get("print") == "1"
        return web.Response(text=self._artifact_html(self.runtime(request), for_print), content_type="text/html",
                            charset="utf-8", headers={"Cache-Control": "no-store"})

    async def _pdf(self, runtime: ArtifactRuntime) -> bytes:
        url = f"http://127.0.0.1:{self.config.port}/artifacts/{runtime.artifact_id}/artifact?print=1"
        async with self.pdf_lock:
            return await asyncio.get_running_loop().run_in_executor(None, print_artifact_pdf, url, runtime.config.layout)

    async def download_pdf(self, request: web.Request) -> web.Response:
        runtime = self.runtime(request)
        try:
            pdf = await self._pdf(runtime)
        except Exception as error:
            raise web.HTTPServiceUnavailable(text=f"PDF export failed: {error}") from error
        return web.Response(body=pdf, content_type="application/pdf",
                            headers={"Content-Disposition": f'attachment; filename="{runtime.main_file.stem}.pdf"'})

    async def _export_pptx(self, runtime: ArtifactRuntime, out: Path) -> dict[str, Any]:
        if runtime.config.layout != "slides":
            raise web.HTTPBadRequest(text="pptx export applies to slides artifacts")
        if not out.is_relative_to(self.project_dir):
            raise web.HTTPBadRequest(text="out must stay inside the project directory")
        # The print URL strips script blocks; the export drives the same firefox port as PDF.
        url = f"http://127.0.0.1:{self.config.port}/artifacts/{runtime.artifact_id}/artifact?print=1"
        try:
            async with self.pdf_lock:
                return await asyncio.get_running_loop().run_in_executor(
                    None, export_pptx, url, out, self.project_dir, runtime.template_dir)
        except Exception as error:
            raise web.HTTPServiceUnavailable(text=f"pptx export failed: {error}") from error

    def default_pptx_path(self, runtime: ArtifactRuntime) -> Path:
        return self.project_dir / "export" / f"{runtime.artifact_id}.pptx"

    async def export_pptx(self, request: web.Request) -> web.Response:
        runtime = self.runtime(request)
        data = await request.json()
        out = (self.project_dir / data["out"]).resolve() if "out" in data else self.default_pptx_path(runtime)
        return web.json_response(await self._export_pptx(runtime, out))

    async def download_pptx(self, request: web.Request) -> web.StreamResponse:
        runtime = self.runtime(request)
        out = self.default_pptx_path(runtime)
        await self._export_pptx(runtime, out)
        return web.FileResponse(out, headers={
            "Content-Disposition": f'attachment; filename="{out.name}"', "Cache-Control": "no-store"})

    async def render_page(self, request: web.Request) -> web.Response:
        runtime = self.runtime(request)
        try:
            page = int(request.query["page"]) if "page" in request.query else 1
            dpi = int(request.query["dpi"]) if "dpi" in request.query else 96
            gray_value = request.query["gray"] if "gray" in request.query else "1"
        except ValueError as error:
            raise web.HTTPBadRequest(text="page and dpi must be integers") from error
        if not 36 <= dpi <= 300:
            raise web.HTTPBadRequest(text="dpi must be in 36..300")
        if gray_value not in {"0", "1"}:
            raise web.HTTPBadRequest(text="gray must be 0 or 1")
        gray = gray_value == "1"
        # A one-line fix in one block does not need the whole page back: a target ref crops
        # the render to that block, at a fraction of the tokens the full page costs.
        target_ref = request.query.get("target")
        target_box = None
        if target_ref is not None:
            if runtime.space_revision != runtime.revision:
                await self._ensure_layout_checked(runtime, request.host)
            if runtime.space_revision != runtime.revision:
                raise web.HTTPConflict(
                    text="space measurement is not ready for the current revision, so the target's place "
                         "is unknown; keep the review UI open until layout checking finishes")
            if not target_ref.startswith(f"p{page}:"):
                raise web.HTTPBadRequest(text=f"target {target_ref!r} is not on page {page}")
            space_page = next((value for value in runtime.space_pages if value["number"] == page), None)
            if space_page is None or target_ref not in space_page["nodes"]:
                raise web.HTTPNotFound(text=f"unknown target {target_ref!r} on page {page}")
            target_box = (space_page["nodes"][target_ref]["bbox"], space_page["bbox"])
        try:
            pdf = await self._pdf(runtime)
        except Exception as error:
            raise web.HTTPServiceUnavailable(text=f"PDF export failed: {error}") from error
        import fitz
        with fitz.open(stream=pdf, filetype="pdf") as doc:
            if not 1 <= page <= doc.page_count:
                raise web.HTTPBadRequest(text=f"page must be in 1..{doc.page_count}")
            colorspace = fitz.csGRAY if gray else fitz.csRGB
            clip = None
            if target_box is not None:
                # The measurement is in page pixels and the PDF in points; the ratio of the
                # two page widths carries one into the other. A small margin keeps the
                # block's immediate surroundings in the picture.
                (x, y, w, h), page_bbox = target_box
                scale = doc[page - 1].rect.width / page_bbox[2]
                margin = 8.0
                clip = fitz.Rect(
                    max(0.0, x - margin) * scale,
                    max(0.0, y - margin) * scale,
                    min(page_bbox[2], x + w + margin) * scale,
                    min(page_bbox[3], y + h + margin) * scale,
                )
            png = doc[page - 1].get_pixmap(dpi=dpi, colorspace=colorspace, clip=clip).tobytes("png")
        return web.Response(body=png, content_type="image/png")

    async def project_file(self, request: web.Request) -> web.StreamResponse:
        relative = request.match_info["path"]
        if relative == ".html-mcp-web.yaml" or relative.startswith(".html-mcp-web/"):
            raise web.HTTPNotFound()
        target = (self.project_dir / relative).resolve()
        if not target.is_relative_to(self.project_dir) or not target.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(target, headers={"Cache-Control": "no-store"})

    async def get_state(self, request: web.Request) -> web.Response:
        return web.json_response(self.project_state())

    async def apply_config(self) -> None:
        config = load_config(self.config.config_path)
        if config.port != self.config.port:
            raise ValueError(
                f"port changed from {self.config.port} to {config.port}; the new port applies when the agent restarts"
            )
        replacements = self._create_artifacts(config)
        for artifact_id, replacement in replacements.items():
            current = self.artifacts[artifact_id] if artifact_id in self.artifacts else None
            if current is not None and current.config == replacement.config:
                replacements[artifact_id] = current
            elif current is not None:
                replacement.revision = current.revision + 1
        self.config = config
        self.artifacts = replacements
        self.watcher.update_patterns(config.watch, config.ignore)
        state = self.project_state()
        await self.broadcast({"type": "config_reloaded", **state})

    async def update_layout(self, request: web.Request) -> web.Response:
        runtime = self.runtime(request)
        data = await request.json()
        try:
            revision = int(data["revision"])
            errors = data["errors"]
            if not isinstance(errors, list) or not all(isinstance(value, str) and value for value in errors):
                raise ValueError("errors must be a list of non-empty strings")
            space_pages = validated_space_pages(data["space"])
        except (KeyError, TypeError, ValueError) as error:
            raise web.HTTPBadRequest(text=str(error)) from error
        if revision != runtime.revision:
            raise web.HTTPConflict(text=f"layout revision {revision} does not match current revision {runtime.revision}")
        runtime.layout_revision = revision
        runtime.layout_errors = list(errors)
        runtime.space_revision = revision
        runtime.space_pages = space_pages
        runtime.layout_room = room_for_errors(errors, space_pages)
        return web.json_response(runtime.state())

    async def _ensure_layout_checked(self, runtime: ArtifactRuntime, host: str) -> None:
        """Run the layout check ourselves when no review UI is open to run it.

        The check is browser work (the page's own scripts measure it and post the result
        back), and with no browser on the page checked_revision sat at null and every
        measurement 409'd until someone opened the UI. The measurers only need a browser,
        not a reader: a headless one pointed at this server's own page runs the same
        scripts and posts the same result. A connected UI is left to do it instead, and
        one check runs at a time.
        """
        import shutil as _shutil
        import tempfile

        if runtime.space_revision == runtime.revision or self.websockets:
            return
        if _shutil.which("firefox") is None:
            return
        async with self.headless_check:
            if runtime.space_revision == runtime.revision:
                return
            profile = tempfile.mkdtemp(prefix="html_mcp_check_")
            process = await asyncio.create_subprocess_exec(
                "firefox", "-headless", "-no-remote", "-profile", profile,
                f"http://{host}/?artifact={runtime.artifact_id}",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                for _ in range(90):
                    if runtime.space_revision == runtime.revision:
                        return
                    await asyncio.sleep(0.5)
            finally:
                process.terminate()
                await process.wait()
                await asyncio.get_running_loop().run_in_executor(
                    None, lambda: _shutil.rmtree(profile, ignore_errors=True))

    async def measure_space(self, request: web.Request) -> web.Response:
        runtime = self.runtime(request)
        try:
            # A stated revision guards against measuring a page that changed underneath;
            # left out, the current one is meant, without an inspect round to learn it.
            revision = int(request.query["revision"]) if "revision" in request.query else runtime.revision
            page_number = int(request.query["page"])
            clearance = float(request.query["clearance"])
            min_width = float(request.query["min_width"]) if "min_width" in request.query else 0.0
            min_height = float(request.query["min_height"]) if "min_height" in request.query else 0.0
            if revision < 1 or page_number < 1:
                raise ValueError("revision and page must be positive integers")
            dimensions = (clearance, min_width, min_height)
            if not all(math.isfinite(value) and value >= 0 for value in dimensions):
                raise ValueError("clearance and minimum dimensions must be finite and non-negative")
        except (KeyError, ValueError) as error:
            raise web.HTTPBadRequest(text=str(error)) from error
        if revision != runtime.revision:
            raise web.HTTPConflict(text=f"requested revision {revision} does not match current revision {runtime.revision}")
        if runtime.space_revision != revision:
            await self._ensure_layout_checked(runtime, request.host)
        if runtime.space_revision != revision:
            raise web.HTTPConflict(
                text=f"space measurement is not ready for revision {revision}; keep the review UI open until layout checking finishes"
            )
        page = next((value for value in runtime.space_pages if value["number"] == page_number), None)
        if page is None:
            raise web.HTTPNotFound(text=f"page {page_number} does not exist")
        target_ref = request.query["target"] if "target" in request.query else None
        if target_ref is None:
            scope = page["bbox"]
            child_refs = page["children"]
            node = None
        else:
            try:
                node = page["nodes"][target_ref]
            except KeyError as error:
                raise web.HTTPNotFound(text=f"unknown target {target_ref!r} on page {page_number}") from error
            scope = node["bbox"]
            child_refs = node["children"]
        children = [page["nodes"][ref] for ref in child_refs]
        obstacles = [child["bbox"] for child in children]
        if node is not None:
            obstacles.extend(node["lines"])
            if node["kind"] == "object" and not obstacles:
                # The drawn extent is what an SVG actually covers; without it the whole
                # box counts as occupied and empty sides of a drawing stay invisible.
                obstacles.append(node["content_bbox"] if "content_bbox" in node else node["bbox"])
        clipped_content = [value for box in obstacles if (value := intersection(box, scope)) is not None]
        content_bbox = union_bbox(clipped_content)
        scope_area = scope[2] * scope[3]
        used_area = union_area(obstacles, scope)
        result: dict[str, Any] = {
            "artifact": runtime.artifact_id,
            "revision": revision,
            "page": page_number,
            "target": target_ref,
            "bbox": [round(value, 2) for value in scope],
            "clearance": clearance,
            "content_bbox": None if content_bbox is None else [round(value, 2) for value in content_bbox],
            "unused_ratio": round(1 - used_area / scope_area, 4) if scope_area > 0 else 0.0,
            "children": [
                {
                    "ref": ref,
                    "kind": child["kind"],
                    "element": child["element"],
                    "bbox": [round(value, 2) for value in child["bbox"]],
                    **({"row": child["row"], "column": child["column"]} if "row" in child else {}),
                }
                for ref, child in zip(child_refs, children)
            ],
            "free_regions": maximal_free_regions(scope, obstacles, clearance, min_width, min_height),
        }
        if content_bbox is not None:
            result["edge_space"] = {
                "top": round(content_bbox[1] - scope[1], 2),
                "right": round(scope[0] + scope[2] - content_bbox[0] - content_bbox[2], 2),
                "bottom": round(scope[1] + scope[3] - content_bbox[1] - content_bbox[3], 2),
                "left": round(content_bbox[0] - scope[0], 2),
            }
        if node is not None:
            result["kind"] = node["kind"]
            result["element"] = node["element"]
            result["padding"] = node["padding"]
            result["overflow"] = node["overflow"]
            if "width_constraints" in node:
                result["width_constraints"] = node["width_constraints"]
            if node["lines"]:
                last_line = sorted(node["lines"], key=lambda box: (box[1], box[0]))[-1]
                result["text"] = {
                    "line_count": len(node["lines"]),
                    "last_line_right_space": round(scope[0] + scope[2] - last_line[0] - last_line[2], 2),
                    "remaining_vertical_space": round(scope[1] + scope[3] - last_line[1] - last_line[3], 2),
                }
        return web.json_response(result)

    async def list_comments(self, request: web.Request) -> web.Response:
        runtime = self.runtime(request)
        status = request.query["status"] if "status" in request.query else None
        if status not in {None, "open", "resolved", "dismissed"}:
            raise web.HTTPBadRequest(text="invalid status")
        return web.json_response({"comments": [comment.to_dict() for comment in runtime.store.list(status=status)]})

    async def get_comment(self, request: web.Request) -> web.Response:
        runtime = self.runtime(request)
        try:
            comment = runtime.store.get(request.match_info["comment_id"])
        except KeyError as error:
            raise web.HTTPNotFound(text=str(error)) from error
        return web.json_response(comment.to_dict())

    async def add_comment(self, request: web.Request) -> web.Response:
        runtime = self.runtime(request)
        data = await request.json()
        try:
            comment = runtime.store.add(anchor_from_dict(data["anchor"]), str(data["text"]), author="human")
        except (KeyError, TypeError, ValueError) as error:
            raise web.HTTPBadRequest(text=str(error)) from error
        await self.broadcast({"type": "comment_added", "artifact": runtime.artifact_id, "comment": comment.to_dict()})
        return web.json_response(comment.to_dict(), status=201)

    async def _thread_mutation(self, request: web.Request, action: str) -> web.Response:
        runtime = self.runtime(request)
        data = await request.json()
        comment_id = request.match_info["comment_id"]
        author = data["author"] if "author" in data else "human"
        if author not in {"human", "agent"}:
            raise web.HTTPBadRequest(text="invalid author")
        try:
            if action == "reply":
                comment = runtime.store.reply(comment_id, str(data["text"]), author,
                                              [str(value) for value in data["edits"]] if "edits" in data else None)
            elif action == "resolve":
                comment = runtime.store.resolve(comment_id, str(data["summary"]), author,
                                                [str(value) for value in data["edits"]] if "edits" in data else None)
            elif action == "dismiss":
                comment = runtime.store.dismiss(comment_id, str(data["reason"]), author)
            elif action == "reopen":
                comment = runtime.store.reopen(comment_id, str(data["text"]), author)
            else:
                raise RuntimeError(f"unknown mutation: {action}")
        except KeyError as error:
            raise web.HTTPNotFound(text=str(error)) from error
        except (TypeError, ValueError) as error:
            raise web.HTTPBadRequest(text=str(error)) from error
        await self.broadcast({"type": "comment_updated", "artifact": runtime.artifact_id, "comment": comment.to_dict()})
        return web.json_response(comment.to_dict())

    def _anchor_text_survives(self, runtime: ArtifactRuntime, comment: Comment) -> bool:
        """Whether the spot a comment points at still reads the same in the artifact.

        The spot is the quote in its stored context. The quote alone proved nothing:
        lambda*delay rewritten into Sigma(lambda*delay) still contains the old quote, and
        the warning fired on a sentence that had just been changed. Context that is gone
        means the edit reached this spot; all of it intact means it was not touched, which
        is normal for a question or for a change made elsewhere, so it is reported rather
        than refused. Spacing is dropped on both sides: the anchor carries the rendered
        page's spacing, the artifact the source's.
        """
        anchor = comment.anchor.to_dict()
        if anchor["kind"] != "text":
            return False
        quote = "".join(anchor["quote"].split())
        if not quote:
            return False
        spot = "".join((anchor["prefix"] + anchor["quote"] + anchor["suffix"]).split())
        return spot in "".join(artifact_text(runtime.main_file).split())

    async def update_comments(self, request: web.Request) -> web.Response:
        runtime = self.runtime(request)
        data = await request.json()
        try:
            comment_ids = data["comment_ids"]
            message = data["message"] if "message" in data else ""
            status = data["status"] if "status" in data else None
            edited_files = data["edited_files"] if "edited_files" in data else None
            # The reviewer closes a batch from the page as well, and a thread that reads
            # "agent resolved" over the reviewer's own click misreports who decided.
            author = data["author"] if "author" in data else "agent"
            if author not in {"human", "agent"}:
                raise ValueError("author must be human or agent")
            if not isinstance(comment_ids, list) or not all(isinstance(value, str) for value in comment_ids):
                raise ValueError("comment_ids must be a list of strings")
            if not isinstance(message, str):
                raise ValueError("message must be a string")
            if status not in {None, "open", "resolved", "dismissed"}:
                raise ValueError("status must be open, resolved, or dismissed")
            if edited_files is not None and (
                not isinstance(edited_files, list) or not all(isinstance(value, str) for value in edited_files)
            ):
                raise ValueError("edited_files must be a list of strings")
            comments = runtime.store.update_many(
                comment_ids,
                author,
                message,
                status=status,
                edits=edited_files,
            )
        except KeyError as error:
            raise web.HTTPNotFound(text=str(error)) from error
        except (TypeError, ValueError) as error:
            raise web.HTTPBadRequest(text=str(error)) from error
        result: dict[str, Any] = {
            "updated": [
                {"id": comment.id, "status": comment.status, "updated": comment.updated}
                for comment in comments
            ]
        }
        # The reviewer closing a batch has just read the threads; the check exists to tell
        # an agent that its own edit did not land where the comment pointed.
        if status == "resolved" and author == "agent":
            untouched = [comment.id for comment in comments if self._anchor_text_survives(runtime, comment)]
            if untouched:
                listed = ", ".join(untouched)
                # With edits on record the untouched anchor is the normal case: the fix
                # landed elsewhere, or the comment anchored a heading over the body it
                # asked about. Without any, resolving with nothing changed anywhere is
                # what the warning is for.
                if edited_files:
                    result["note"] = (
                        f"anchor text unchanged for {listed}; normal when the fix landed in "
                        "the files recorded, no action needed"
                    )
                else:
                    result["warning"] = (
                        f"anchor text unchanged in the artifact for {listed}"
                        "; confirm the change landed or reopen"
                    )
        await self.broadcast({
            "type": "comments_updated",
            "artifact": runtime.artifact_id,
            "comment_ids": [comment.id for comment in comments],
        })
        return web.json_response(result)

    async def reply_comment(self, request: web.Request) -> web.Response:
        return await self._thread_mutation(request, "reply")

    async def resolve_comment(self, request: web.Request) -> web.Response:
        return await self._thread_mutation(request, "resolve")

    async def dismiss_comment(self, request: web.Request) -> web.Response:
        return await self._thread_mutation(request, "dismiss")

    async def reopen_comment(self, request: web.Request) -> web.Response:
        return await self._thread_mutation(request, "reopen")

    async def edit_comment_entry(self, request: web.Request) -> web.Response:
        runtime = self.runtime(request)
        data = await request.json()
        comment_id = request.match_info["comment_id"]
        author = data["author"] if "author" in data else "human"
        if author not in {"human", "agent"}:
            raise web.HTTPBadRequest(text="invalid author")
        try:
            comment = runtime.store.edit_entry(comment_id, int(data["index"]), str(data["text"]), author)
        except KeyError as error:
            raise web.HTTPNotFound(text=str(error)) from error
        except (IndexError, TypeError, ValueError) as error:
            raise web.HTTPBadRequest(text=str(error)) from error
        await self.broadcast({"type": "comment_updated", "artifact": runtime.artifact_id, "comment": comment.to_dict()})
        return web.json_response(comment.to_dict())

    async def delete_comment(self, request: web.Request) -> web.Response:
        runtime = self.runtime(request)
        comment_id = request.match_info["comment_id"]
        try:
            runtime.store.delete(comment_id)
        except KeyError as error:
            raise web.HTTPNotFound(text=str(error)) from error
        await self.broadcast({"type": "comment_deleted", "artifact": runtime.artifact_id, "comment_id": comment_id})
        return web.Response(status=204)

    # The reviewer's call button. An agent cannot be spoken to first over MCP, but its
    # harness can watch a process in the background and wake the agent when it exits, so
    # the button becomes: a waiter parks here in a long poll, the press releases it, and
    # the waiter's exit is the interrupt. The agent spends nothing while parked.
    def _review_line(self) -> str:
        opens = {artifact_id: sum(comment.status == "open" for comment in runtime.store.list())
                 for artifact_id, runtime in self.artifacts.items()}
        listed = ", ".join(f"{count} on '{artifact_id}'" for artifact_id, count in opens.items() if count)
        return (f"[review] reviewer called (press #{self.review_calls}): "
                + (f"open comments: {listed}" if listed else "no open comments")
                + " -- read them with list_comments(unanswered=True)")

    async def request_review(self, request: web.Request) -> web.Response:
        self.review_calls += 1
        delivered = self.review_waiters > 0
        released = self.review_called
        self.review_called = asyncio.Event()
        released.set()
        await self.broadcast({"type": "review_requested", "calls": self.review_calls, "delivered": delivered})
        return web.json_response({"calls": self.review_calls, "delivered": delivered})

    async def wait_review(self, request: web.Request) -> web.Response:
        try:
            since = int(request.query.get("since", "0"))
        except ValueError as error:
            raise web.HTTPBadRequest(text="since must be an integer") from error
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.REVIEW_POLL_TIMEOUT
        self.review_waiters += 1
        await self.broadcast({"type": "review_waiters", "waiters": self.review_waiters})
        try:
            while self.review_calls <= since:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return web.Response(status=204)
                waited = self.review_called
                try:
                    await asyncio.wait_for(waited.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    return web.Response(status=204)
            return web.Response(text=self._review_line())
        finally:
            self.review_waiters -= 1
            await self.broadcast({"type": "review_waiters", "waiters": self.review_waiters})

    async def websocket(self, request: web.Request) -> web.WebSocketResponse:
        socket = web.WebSocketResponse(heartbeat=30)
        await socket.prepare(request)
        self.websockets.add(socket)
        await socket.send_json({"type": "state", **self.project_state()})
        try:
            async for message in socket:
                if message.type == WSMsgType.ERROR:
                    break
        finally:
            self.websockets.discard(socket)
        return socket

    async def start_watcher(self, app: web.Application) -> None:
        self.watcher.start(asyncio.get_running_loop())

    async def stop_watcher(self, app: web.Application) -> None:
        self.watcher.stop()

    def create_app(self) -> web.Application:
        # The layout check posts a measurement of every block on every page, which grows
        # with the deck: a 26-page deck measured 1.2MB and aiohttp's default ceiling of 1MB
        # turned the check off with nothing on screen to say why. The body comes from the
        # page this server itself serves, over the loopback, so the ceiling only has to be
        # out of the way.
        app = web.Application(client_max_size=64 * 1024 * 1024)
        app["review_server"] = self
        app.router.add_get("/", self.index)
        app.router.add_get("/static/{name:.*}", self.static)
        app.router.add_get("/project/{path:.*}", self.project_file)
        app.router.add_get("/state", self.get_state)
        base = "/artifacts/{artifact_id}"
        app.router.add_get(f"{base}/artifact", self.artifact)
        app.router.add_get(f"{base}/download/pdf", self.download_pdf)
        app.router.add_post(f"{base}/export/pptx", self.export_pptx)
        app.router.add_get(f"{base}/download/pptx", self.download_pptx)
        app.router.add_get(f"{base}/render/page", self.render_page)
        app.router.add_post(f"{base}/layout", self.update_layout)
        app.router.add_get(f"{base}/space", self.measure_space)
        app.router.add_get(f"{base}/comments", self.list_comments)
        app.router.add_get(f"{base}/comments/{{comment_id}}", self.get_comment)
        app.router.add_post(f"{base}/comments", self.add_comment)
        app.router.add_post(f"{base}/comments/update", self.update_comments)
        app.router.add_post(f"{base}/comments/{{comment_id}}/reply", self.reply_comment)
        app.router.add_post(f"{base}/comments/{{comment_id}}/resolve", self.resolve_comment)
        app.router.add_post(f"{base}/comments/{{comment_id}}/dismiss", self.dismiss_comment)
        app.router.add_post(f"{base}/comments/{{comment_id}}/reopen", self.reopen_comment)
        app.router.add_post(f"{base}/comments/{{comment_id}}/edit", self.edit_comment_entry)
        app.router.add_delete(f"{base}/comments/{{comment_id}}", self.delete_comment)
        app.router.add_post("/review-request", self.request_review)
        app.router.add_get("/wait-review", self.wait_review)
        app.router.add_get("/ws", self.websocket)
        app.on_startup.append(self.start_watcher)
        app.on_cleanup.append(self.stop_watcher)
        return app


def run_server(config: Config, host: str = "127.0.0.1") -> None:
    server = HtmlReviewServer(config)
    web.run_app(server.create_app(), host=host, port=config.port, print=None)
