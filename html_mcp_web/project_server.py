"""Shared ownership of the project review HTTP server."""

import asyncio
import fcntl
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from aiohttp import web

from .config import Config, load_config


class SharedProjectServer:
    """One MCP process serves; peers using the same config share its listener."""

    START_TIMEOUT = 10

    def __init__(self, config: Config):
        if config.config_path is None:
            raise ValueError("configuration has no file path")
        self.config_path = config.config_path.resolve()
        self.port = config.port
        self.lock_handle = None
        self.lock_guard = threading.Lock()
        self.thread: threading.Thread | None = None
        self.ready = threading.Event()
        self.start_error: BaseException | None = None
        self.start_task: asyncio.Task | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.runner: web.AppRunner | None = None

    def _remote_identity(self) -> str | None:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/state", timeout=0.5) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None
        return str(data["config_path"])

    def _serve(self) -> None:
        from .server import HtmlReviewServer

        loop = asyncio.new_event_loop()
        self.loop = loop
        asyncio.set_event_loop(loop)

        async def start() -> None:
            try:
                config = load_config(self.config_path)
                self.runner = web.AppRunner(HtmlReviewServer(config).create_app())
                await self.runner.setup()
                await web.TCPSite(self.runner, "127.0.0.1", self.port).start()
            except BaseException as error:
                # A cancelled start lands here too, once the startup hooks return.
                self.start_error = error
                if self.runner is not None:
                    # Startup hooks that ran (the file watcher among them) hold inotify
                    # watches; drop them here or a failed start leaks them.
                    await self.runner.cleanup()
                    self.runner = None
            finally:
                self.ready.set()

        try:
            self.start_task = loop.create_task(start())
            loop.run_until_complete(self.start_task)
            if self.start_error is None:
                loop.run_forever()
                if self.runner is not None:
                    loop.run_until_complete(self.runner.cleanup())
        finally:
            loop.close()
            # The lock is tied to this thread's life: a start that was given up on still
            # frees it when its cleanup is done, and nobody has to wait for that.
            self._release_lock()

    def ensure(self) -> None:
        identity = self._remote_identity()
        if identity is not None:
            if Path(identity).resolve() != self.config_path:
                raise RuntimeError(
                    f"port {self.port} serves {identity}, not {self.config_path}; change one project's port")
            return
        if self.thread is not None and self.thread.is_alive():
            if self.ready.is_set() and self.start_error is None:
                return
            # A start given up on earlier is still winding down; a second thread on top of
            # it is how a slow project once piled up a hundred of them.
            if not self.ready.wait(timeout=self.START_TIMEOUT):
                raise RuntimeError(
                    "project server is still starting; its earlier start was cancelled and "
                    "is cleaning up, try again")
            self.thread.join(timeout=self.START_TIMEOUT)
            if self.thread.is_alive():
                raise RuntimeError("project server is still cleaning up a cancelled start; try again")
            self.thread = None
        lock_path = self.config_path.parent / ".html-mcp-web" / "server.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            claimed = False
            for _ in range(50):
                time.sleep(0.1)
                identity = self._remote_identity()
                if identity is not None:
                    if Path(identity).resolve() != self.config_path:
                        handle.close()
                        raise RuntimeError(f"port {self.port} is used by another project: {identity}")
                    handle.close()
                    return
                # The holder can die mid-poll; flock dies with it, and the takeover is
                # ours rather than an error naming a pid that no longer exists.
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    claimed = True
                    break
                except BlockingIOError:
                    continue
            if not claimed:
                # A holder that serves nothing. flock dies with its process, so this holder
                # is alive; the file says who it is, so the way out can be named instead of
                # left to be dug up by hand.
                handle.seek(0)
                recorded = handle.read().strip()
                handle.close()
                holder = f"held by {recorded}" if recorded else "holder unknown (an older version left no note)"
                raise RuntimeError(
                    f"project server lock is held but port {self.port} is not reachable; {holder}. "
                    "The holding process is alive but not serving: reconnect MCP in that session or kill "
                    "that pid, and the lock frees itself with it."
                )
        # Who holds it, for the message above when a later claimant finds us absent.
        handle.truncate(0)
        handle.seek(0)
        handle.write(f"pid {os.getpid()}, port {self.port}")
        handle.flush()
        self.lock_handle = handle
        self.ready.clear()
        self.start_error = None
        self.start_task = None
        self.thread = threading.Thread(target=self._serve, name="html-mcp-web", daemon=True)
        self.thread.start()
        if not self.ready.wait(timeout=self.START_TIMEOUT):
            # The startup hooks run synchronously on the loop, so a cancel takes effect
            # only once they return; the thread then cleans up what they started and
            # frees the lock. Stopping the loop instead skipped that cleanup and left
            # every watch the hooks had taken.
            if self.loop is not None and self.start_task is not None:
                self.loop.call_soon_threadsafe(self.start_task.cancel)
            raise RuntimeError(
                f"project server did not start within {self.START_TIMEOUT} seconds; "
                "the start is cancelled and cleans up in the background, try again")
        if self.start_error is not None:
            error = self.start_error
            self.stop()
            raise RuntimeError(f"project server failed to start: {error}")

    def stop(self) -> None:
        if self.loop is not None and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self.thread is not None:
            self.thread.join(timeout=10)
        self.thread = None
        self.loop = None
        self.runner = None
        self._release_lock()

    def _release_lock(self) -> None:
        with self.lock_guard:
            if self.lock_handle is not None:
                fcntl.flock(self.lock_handle.fileno(), fcntl.LOCK_UN)
                self.lock_handle.close()
                self.lock_handle = None
