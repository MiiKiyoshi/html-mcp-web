"""Debounced project file watching."""

import asyncio
import errno
import fnmatch
import logging
import os
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
        on_new_directory: Callable[[str], None] | None = None,
    ):
        super().__init__()
        self.watch_dir = watch_dir.resolve()
        self.watch_patterns = watch_patterns
        self.ignore_patterns = ignore_patterns
        self.callback = callback
        self.loop = loop
        self.debounce_seconds = debounce_seconds
        self.on_new_directory = on_new_directory
        self.pending_task: Future[Any] | None = None
        self.pending_path: str | None = None

    def ignores(self, name: str) -> bool:
        """Whether a top-level entry of this name is one the config leaves out."""
        return any(fnmatch.fnmatch(name, pattern) for pattern in self.ignore_patterns)

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
        if event.is_directory:
            if self.on_new_directory is not None:
                self.on_new_directory(self._path(event))
            return
        path = self._path(event)
        if self._should_process(path):
            self._schedule(path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        # A deleted artifact is a change to it: without this, the layout measured from the
        # deleted file stayed on offer as current, revision and all.
        if not event.is_directory:
            path = self._path(event)
            if self._should_process(path):
                self._schedule(path)

    def on_moved(self, event: FileSystemEvent) -> None:
        destination = event.dest_path
        if event.is_directory:
            if self.on_new_directory is not None:
                self.on_new_directory(
                    destination.decode("utf-8", errors="replace") if isinstance(destination, bytes) else destination)
            return
        # A rename is a change at both ends: the file that appeared, and the artifact that
        # just lost its main to the reviewer renaming it away.
        source = self._path(event)
        if self._should_process(source):
            self._schedule(source)
        path = destination.decode("utf-8", errors="replace") if isinstance(destination, bytes) else destination
        if self._should_process(path):
            self._schedule(path)


class Watcher:
    # Counting no further than this keeps a runaway tree from turning a census into a wait.
    CENSUS_CAP = 20000

    def __init__(
        self,
        watch_dir: Path,
        watch_patterns: list[str],
        ignore_patterns: list[str],
        on_change: Callable[[str], Coroutine[Any, Any, None]],
        roots: list[Path],
        debounce_seconds: float = 0.25,
    ):
        self.watch_dir = watch_dir.resolve()
        self.watch_patterns = watch_patterns
        self.ignore_patterns = ignore_patterns
        self.on_change = on_change
        # The directories that hold artifact content, watched recursively; every other
        # tree under the project is never enumerated, so what it costs in inotify watches
        # and in a cold walk of the disk is never spent here.
        self.roots = self._merge_roots(roots)
        self.debounce_seconds = debounce_seconds
        self.observer: Any = None
        self.handler: HtmlFileHandler | None = None

    def _merge_roots(self, roots: list[Path]) -> list[Path]:
        """Roots below the project, an ancestor standing in for the roots below it.

        The project root itself is never one: an artifact kept at the top level is
        covered by the flat watch, and watching the whole project recursively for it
        would walk every unrelated tree beside it."""
        inside = sorted({root.resolve() for root in roots if self.watch_dir in root.resolve().parents})
        merged: list[Path] = []
        for root in inside:
            if not any(kept == root or kept in root.parents for kept in merged):
                merged.append(root)
        return merged

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self.handler = HtmlFileHandler(
            self.watch_dir,
            self.watch_patterns,
            self.ignore_patterns,
            self.on_change,
            loop,
            self.debounce_seconds,
            self._watch_new_directory,
        )
        self.observer = Observer()
        # A watch goes on every directory under a recursive root, and the limit belongs to
        # the login rather than to this server. Only the roots that hold artifact content
        # are watched recursively; the project root is watched flat, for the config file,
        # for artifacts kept at the top level, and for a root that appears later.
        try:
            self.observer.schedule(self.handler, str(self.watch_dir), recursive=False)
            for root in self.roots:
                if root.is_dir():
                    self.observer.schedule(self.handler, str(root), recursive=True)
            self.observer.start()
        except BaseException as error:
            # A partially scheduled observer keeps its inotify descriptor, and its
            # watches, until it is stopped; leaking it on every failed start is how a
            # process reaches the limit on its own.
            self.observer.stop()
            self.observer = None
            if isinstance(error, OSError) and error.errno == errno.ENOSPC:
                raise RuntimeError(self._watch_limit_message()) from error
            raise

    @staticmethod
    def _count_directories(root: Path, cap: int) -> int:
        """Directories under root, counting no further than cap so a runaway tree does not
        turn the error message into another long wait."""
        total = 1
        stack = [root]
        while stack and total < cap:
            try:
                entries = list(os.scandir(stack.pop()))
            except OSError:
                continue
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    total += 1
                    stack.append(Path(entry.path))
                    if total >= cap:
                        break
        return total

    def _census(self) -> list[tuple[int, str]]:
        """How many directories each watched root holds, dearest first."""
        counts = [(self._count_directories(root, self.CENSUS_CAP), root.relative_to(self.watch_dir).as_posix())
                  for root in self.roots if root.is_dir()]
        counts.sort(reverse=True)
        return counts

    def _dearest(self, counts: list[tuple[int, str]]) -> str:
        return ", ".join(f"{name} {'over ' if total >= self.CENSUS_CAP else ''}{total}"
                         for total, name in counts[:5])

    def _watch_limit_message(self) -> str:
        """What the reader has to know to get past a used-up limit: the watch is one per
        directory, the limit belongs to the whole login rather than this project, and which
        directories are spending it."""
        counts = self._census()
        listed = self._dearest(counts)
        return (
            "the inotify watch limit is used up, so the project cannot be watched. One watch "
            f"goes on every directory under the artifact directories ({sum(total for total, _ in counts) + 1} here) "
            "and the limit is shared by every session of this login, not per project. Directories "
            f"by cost: {listed}. Move unrelated trees out of the artifact directories, or raise "
            "fs.inotify.max_user_watches."
        )

    def _watch_new_directory(self, path: str) -> None:
        """A root that appeared under the project after the watch began.

        The project root is watched flat, so a root created later (an artifact directory
        written by a build) gets no watch of its own until it is scheduled here.
        """
        entry = Path(path)
        if self.observer is None or entry.parent.resolve() != self.watch_dir:
            return
        entry = entry.resolve()
        if entry not in self.roots or entry.is_symlink():
            return
        try:
            self.observer.schedule(self.handler, str(entry), recursive=True)
        except OSError as error:
            logger.error("Cannot watch new directory %s: %s", entry, error)

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
