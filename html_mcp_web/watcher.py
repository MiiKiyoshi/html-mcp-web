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
            self._watch_new_directory,
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
                if self._watchable(entry):
                    self.observer.schedule(self.handler, str(entry), recursive=True)
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

    def _watch_limit_message(self) -> str:
        """What the reader has to know to get past a used-up limit: the watch is one per
        directory, the limit belongs to the whole login rather than this project, and which
        directories are spending it."""
        cap = 20000
        counts = []
        for entry in sorted(self.watch_dir.iterdir()):
            if self._watchable(entry):
                counts.append((self._count_directories(entry, cap), entry.name))
        counts.sort(reverse=True)
        listed = ", ".join(f"{name} {'over ' if total >= cap else ''}{total}" for total, name in counts[:5])
        return (
            "the inotify watch limit is used up, so the project cannot be watched. One watch "
            f"goes on every directory being watched ({sum(total for total, _ in counts) + 1} here) "
            "and the limit is shared by every session of this login, not per project. Directories "
            f"by cost: {listed}. Put the trees that hold no artifact content into ignore in "
            ".html-mcp-web.yaml (their top-level name is enough), or raise "
            "fs.inotify.max_user_watches."
        )

    def _watchable(self, entry: Path) -> bool:
        """A top-level directory whose tree this watcher takes inotify watches for.

        A symlink is left out: an event under it carries a path that resolves outside the
        project, which the handler drops, so watching through one spends the per-user limit
        on events that can never be acted on.
        """
        if entry.is_symlink() or not entry.is_dir() or entry.name == ".html-mcp-web":
            return False
        # The name, not the resolved path: a link into another repository has no form
        # relative to the project, and matching by name is what the config's list means.
        return self.handler is not None and not self.handler.ignores(entry.name)

    def _watch_new_directory(self, path: str) -> None:
        """A directory that appeared under the root after the watch began.

        The root is watched flat so that ignoring a top-level directory frees its whole
        tree, and that means a directory created later gets no watch of its own: files
        written into it would never reach the artifact until the server restarted.
        """
        entry = Path(path)
        if self.observer is None or entry.parent.resolve() != self.watch_dir.resolve():
            return
        if not self._watchable(entry):
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
