"""Startup of the shared project server: a slow or failing start must not leak."""

import asyncio
import json
import socket
import threading
import time
import urllib.request
from pathlib import Path

import pytest
import yaml

from html_mcp_web.config import load_config
from html_mcp_web.project_server import SharedProjectServer
from html_mcp_web.server import HtmlReviewServer
from html_mcp_web.shared import filelock


def _config(tmp_path: Path):
    (tmp_path / "html").mkdir()
    (tmp_path / "html" / "slides.html").write_text(
        '<!doctype html><html><body><main class="pages"><section class="page"></section></main></body></html>',
        encoding="utf-8",
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = int(listener.getsockname()[1])
    path = tmp_path / ".html-mcp-web.yaml"
    path.write_text(yaml.safe_dump({
        "artifacts": {"slides": {"layout": "slides", "main": "html/slides.html"}},
        "port": port,
    }, sort_keys=False), encoding="utf-8")
    return load_config(path)


def _server_threads() -> int:
    return sum(1 for thread in threading.enumerate() if thread.name == "html-mcp-web")


def _lock_is_free(config) -> bool:
    with (config.config_path.parent / ".html-mcp-web" / "server.lock").open("a+", encoding="utf-8") as handle:
        try:
            filelock.lock(handle, wait=False)
        except BlockingIOError:
            return False
        filelock.unlock(handle)
        return True


def _wait(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met in time")


def test_a_slow_start_is_cancelled_after_it_returns_and_cleans_up(tmp_path: Path, monkeypatch) -> None:
    """The startup hooks run synchronously on the loop, so the cancel cannot land before
    they return; when they do, the thread cleans up its watcher, closes, and frees the lock,
    and a retry made meanwhile adds no thread."""
    config = _config(tmp_path)
    shared = SharedProjectServer(config)
    monkeypatch.setattr(SharedProjectServer, "START_TIMEOUT", 0.3)
    servers: list[HtmlReviewServer] = []
    original = HtmlReviewServer.start_watcher

    async def slow_start(self, app):
        servers.append(self)
        time.sleep(0.9)  # a cold walk of a big tree, on the loop thread
        await original(self, app)

    monkeypatch.setattr(HtmlReviewServer, "start_watcher", slow_start)
    before = _server_threads()
    try:
        with pytest.raises(RuntimeError, match="did not start within"):
            shared.ensure()
        # The hooks are still running: the cancel has not taken effect yet.
        assert _server_threads() == before + 1
        assert not shared.ready.is_set()
        with pytest.raises(RuntimeError, match="still starting"):
            shared.ensure()
        assert _server_threads() == before + 1
        _wait(lambda: shared.thread is not None and not shared.thread.is_alive())
        assert len(servers) == 1 and servers[0].watcher.observer is None
        assert _lock_is_free(config)
        assert _server_threads() == before

        # A retry after the cleanup starts afresh and serves.
        monkeypatch.setattr(HtmlReviewServer, "start_watcher", original)
        monkeypatch.setattr(SharedProjectServer, "START_TIMEOUT", 10)
        shared.ensure()
        assert shared._remote_identity() == str(config.config_path)
        assert _server_threads() == before + 1
    finally:
        shared.stop()
    assert _server_threads() == before
    assert _lock_is_free(config)


async def test_config_reload_watches_a_newly_declared_artifact_directory(tmp_path: Path) -> None:
    """A config change can declare an artifact in a directory that exists already; the
    project root is watched flat, so that directory gets its recursive watch only when
    the reload recomputes the roots, and gives it back when the artifact goes."""
    config = _config(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "report.html").write_text("<!doctype html><html><body></body></html>", encoding="utf-8")
    review = HtmlReviewServer(config)
    review.watcher.start(asyncio.get_running_loop())
    try:
        watches = lambda: {(w.path, w.is_recursive) for w in review.watcher.observer._watches}
        assert review.watcher.roots == [tmp_path / "html"]
        assert watches() == {(str(tmp_path), False), (str(tmp_path / "html"), True)}

        data = yaml.safe_load(config.config_path.read_text(encoding="utf-8"))
        data["artifacts"]["report"] = {"layout": "report", "main": "docs/report.html"}
        config.config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        await review.apply_config()
        assert review.watcher.roots == [tmp_path / "docs", tmp_path / "html"]
        assert (str(tmp_path / "docs"), True) in watches()

        # An edit deep in the new directory reaches the artifact through the watch.
        before = review.artifacts["report"].revision
        await asyncio.sleep(0.2)
        (tmp_path / "docs" / "report.html").write_text("<!doctype html><html><body><p>x</p></body></html>",
                                                       encoding="utf-8")
        for _ in range(60):
            await asyncio.sleep(0.05)
            if review.artifacts["report"].revision > before:
                break
        assert review.artifacts["report"].revision > before

        del data["artifacts"]["report"]
        config.config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        await review.apply_config()
        assert review.watcher.roots == [tmp_path / "html"]
        assert watches() == {(str(tmp_path), False), (str(tmp_path / "html"), True)}
    finally:
        review.watcher.stop()


def test_a_stop_right_after_the_start_ends_the_server(tmp_path: Path, monkeypatch) -> None:
    """The start is reported ready a moment before the server's loop runs on for good. A stop
    in that moment found the loop not running and asked nothing of it: the server served on
    with its lock released, and the next start in the project found it answering and stayed
    out, even with the lock held by a process that served nothing. Stopped then, it cleans up
    as any stop does."""
    config = _config(tmp_path)
    shared = SharedProjectServer(config)
    original = HtmlReviewServer.catch_up
    servers: list[HtmlReviewServer] = []

    def late(self):
        servers.append(self)
        time.sleep(0.5)  # the moment between the start and the loop running on, drawn out
        return original(self)

    monkeypatch.setattr(HtmlReviewServer, "catch_up", late)
    before = _server_threads()
    shared.ensure()
    shared.stop()
    assert _server_threads() == before
    assert shared._remote_identity() is None
    assert _lock_is_free(config)
    assert len(servers) == 1 and servers[0].watcher.observer is None


def test_a_build_due_at_start_runs_once_the_server_serves(tmp_path: Path, monkeypatch) -> None:
    """A report whose content was newer than its built file was built before the server
    reported its start, and a report's build sets its pages in Chrome: on a slow machine the
    start gave up first. The server now starts, and builds next, a request asked meanwhile
    waiting for the build."""
    from html_mcp_web import config as config_module

    monkeypatch.setattr(config_module, "USER_CONFIG_DIR", tmp_path / "user")
    template = tmp_path / "user" / "templates" / "slow"
    template.mkdir(parents=True)
    (template / "build.py").write_text(
        "import sys, time\nfrom pathlib import Path\ntime.sleep(1.5)\n"
        "Path(sys.argv[2]).write_text(Path(sys.argv[1]).read_text())\n", encoding="utf-8")
    (tmp_path / "content.html").write_text("<p>built</p>", encoding="utf-8")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = int(listener.getsockname()[1])
    path = tmp_path / ".html-mcp-web.yaml"
    path.write_text(yaml.safe_dump({
        "artifacts": {"report": {"layout": "report", "main": "report.html",
                                 "template": "slow", "content": "content.html"}},
        "port": port,
    }, sort_keys=False), encoding="utf-8")
    shared = SharedProjectServer(load_config(path))
    monkeypatch.setattr(SharedProjectServer, "START_TIMEOUT", 1)
    try:
        shared.ensure()
        assert not (tmp_path / "report.html").exists()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/state", timeout=10) as response:
            state = json.loads(response.read().decode("utf-8"))["artifacts"]["report"]
        assert (tmp_path / "report.html").read_text(encoding="utf-8") == "<p>built</p>"
        assert state["build_error"] is None and "error" not in state
    finally:
        shared.stop()


def test_a_failed_start_names_its_cause_and_frees_the_lock(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    shared = SharedProjectServer(config)

    async def broken_start(self, app):
        raise RuntimeError("the inotify watch limit is used up")

    monkeypatch.setattr(HtmlReviewServer, "start_watcher", broken_start)
    before = _server_threads()
    with pytest.raises(RuntimeError, match="failed to start: the inotify watch limit is used up"):
        shared.ensure()
    assert _server_threads() == before
    assert _lock_is_free(config)
    assert shared._remote_identity() is None
