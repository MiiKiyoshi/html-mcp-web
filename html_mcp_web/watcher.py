"""Debounced project file watching."""

import asyncio
import fnmatch
import logging
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Callable, Coroutine

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


logger = logging.getLogger(__name__)


class HtmlFileHandler(FileSystemEventHandler):
    def __init__(
        self,
        watch_dir: Path,
        watch_patterns: list[str],
        ignore_patterns: list[str],
        callback: Callable[[str], Coroutine[Any, Any, None]],
        loop: asyncio.AbstractEventLoop,
        debounce_seconds: float = 0.25,
    ):
        super().__init__()
        self.watch_dir = watch_dir.resolve()
        self.watch_patterns = watch_patterns
        self.ignore_patterns = ignore_patterns
        self.callback = callback
        self.loop = loop
        self.debounce_seconds = debounce_seconds
        self.pending_task: Future[Any] | None = None
        self.pending_path: str | None = None

    def _relative(self, path: str) -> str:
        value = Path(path)
        return value.resolve().relative_to(self.watch_dir).as_posix() if value.is_absolute() else value.as_posix()

    def _matches(self, path: str, patterns: list[str]) -> bool:
        relative = self._relative(path)
        name = Path(relative).name
        return any(fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(relative, pattern) for pattern in patterns)

    def _should_process(self, path: str) -> bool:
        try:
            relative = self._relative(path)
        except ValueError:
            return False
        if relative == ".html-mcp-web.yaml":
            return True
        if relative.startswith(".html-mcp-web/"):
            return False
        if self._matches(path, self.ignore_patterns):
            return False
        return self._matches(path, self.watch_patterns)

    def _path(self, event: FileSystemEvent) -> str:
        value = event.src_path
        return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value

    def _schedule(self, path: str) -> None:
        self.pending_path = path
        if self.pending_task is not None and not self.pending_task.done():
            self.pending_task.cancel()

        async def delayed() -> None:
            await asyncio.sleep(self.debounce_seconds)
            if self.pending_path is None:
                raise RuntimeError("pending path disappeared")
            await self.callback(self.pending_path)

        self.pending_task = asyncio.run_coroutine_threadsafe(delayed(), self.loop)
        self.pending_task.add_done_callback(self._report_callback_result)

    @staticmethod
    def _report_callback_result(result: Future[Any]) -> None:
        if result.cancelled():
            return
        error = result.exception()
        if error is not None:
            logger.error("File update callback failed: %s", error)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            path = self._path(event)
            if self._should_process(path):
                self._schedule(path)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            path = self._path(event)
            if self._should_process(path):
                self._schedule(path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        destination = event.dest_path
        path = destination.decode("utf-8", errors="replace") if isinstance(destination, bytes) else destination
        if self._should_process(path):
            self._schedule(path)


class Watcher:
    def __init__(
        self,
        watch_dir: Path,
        watch_patterns: list[str],
        ignore_patterns: list[str],
        on_change: Callable[[str], Coroutine[Any, Any, None]],
        debounce_seconds: float = 0.25,
    ):
        self.watch_dir = watch_dir
        self.watch_patterns = watch_patterns
        self.ignore_patterns = ignore_patterns
        self.on_change = on_change
        self.debounce_seconds = debounce_seconds
        self.observer: Any = None
        self.handler: HtmlFileHandler | None = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self.handler = HtmlFileHandler(
            self.watch_dir,
            self.watch_patterns,
            self.ignore_patterns,
            self.on_change,
            loop,
            self.debounce_seconds,
        )
        self.observer = Observer()
        # One recursive watch on the project root costs an inotify watch per directory
        # underneath it, ignored trees included; a large ignored tree (checkpoints, a
        # baseline dump) exhausts the per-user limit. The root is watched flat and each
        # top-level entry that is not ignored is watched on its own, so ignoring a top-level
        # directory removes its whole tree from inotify.
        try:
            self.observer.schedule(self.handler, str(self.watch_dir), recursive=False)
            for entry in sorted(self.watch_dir.iterdir()):
                if not entry.is_dir() or entry.name == ".html-mcp-web":
                    continue
                # Match on the entry name, not the resolved path: a symlink into another
                # repository resolves outside the project and has no relative form.
                if self.handler._matches(entry.name, self.ignore_patterns):
                    continue
                self.observer.schedule(self.handler, str(entry), recursive=True)
            self.observer.start()
        except BaseException:
            # A partially scheduled observer keeps its inotify descriptor, and its
            # watches, until it is stopped; leaking it on every failed start is how a
            # process reaches the limit on its own.
            self.observer.stop()
            self.observer = None
            raise

    def stop(self) -> None:
        if self.handler is not None and self.handler.pending_task is not None:
            self.handler.pending_task.cancel()
        if self.observer is not None:
            self.observer.stop()
            self.observer.join(timeout=5)
            self.observer = None

    def update_patterns(self, watch_patterns: list[str], ignore_patterns: list[str]) -> None:
        self.watch_patterns = watch_patterns
        self.ignore_patterns = ignore_patterns
        if self.handler is not None:
            self.handler.watch_patterns = watch_patterns
            self.handler.ignore_patterns = ignore_patterns
