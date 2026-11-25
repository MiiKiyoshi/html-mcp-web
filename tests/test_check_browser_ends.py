"""A layout check's browser and its profile go with the server that started them when the
server stops: by stop(), with a pytest worker ending after it, and with its client closing the
pipe (server.py stop_checks()).

Each server serves a deck whose image never arrives, so its check runs until the server stops.
Each process a test starts has a temporary folder of its own, where the browsers' profiles are
made and by which the browsers are found. A browser left on one is ended when the test ends,
whether the test passed or failed."""

import contextlib
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import urllib.request
from pathlib import Path

import psutil
import pytest
import yaml

from html_mcp_web.config import load_config
from html_mcp_web.project_server import SharedProjectServer
from tests.html_chrome import needs_browser

REPOSITORY = Path(__file__).resolve().parents[1]
# The MCP server, as a client starts it.
MCP = [sys.executable, "-c", "from html_mcp_web.cli import main_mcp; raise SystemExit(main_mcp())"]


class Never:
    """An image that never arrives, from a port that takes connections and never answers."""

    def __init__(self):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(64)
        self.url = f"http://127.0.0.1:{self.listener.getsockname()[1]}/never.png"
        self.held: list[socket.socket] = []

    def asked(self) -> None:
        """Wait until a page asks for the image: it has loaded and waits for the image."""
        self.listener.settimeout(60)
        self.held.append(self.listener.accept()[0])

    def close(self) -> None:
        for connection in (*self.held, self.listener):
            connection.close()


@pytest.fixture
def never():
    image = Never()
    try:
        yield image
    finally:
        image.close()


@pytest.fixture
def tmp():
    """The temporary folder of what the test starts: a short one in the system's own. Chrome
    makes a socket in it, whose path has room for about a hundred characters, and a folder in
    pytest's own leaves too few for Chrome to start."""
    folder = Path(tempfile.mkdtemp(prefix="html_mcp_test_"))
    try:
        yield folder
    finally:
        for process in browsers(folder):
            with contextlib.suppress(psutil.Error):
                process.kill()
        shutil.rmtree(folder, ignore_errors=True)


def slow_project(folder: Path, image: str) -> tuple[Path, int]:
    """A project in *folder* whose one deck shows *image*: its config and its port."""
    folder.mkdir(exist_ok=True)
    (folder / "slides.html").write_text(
        '<!doctype html><html><head><meta charset="utf-8"><title>Slow</title></head><body>'
        '<main class="pages"><section class="page"><div data-layout-guard><h1>Slow</h1>'
        f'<img src="{image}" width="100" height="100"></div></section></main></body></html>', encoding="utf-8")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = folder / ".html-mcp-web.yaml"
    config.write_text(yaml.safe_dump({"artifacts": {"slides": {"layout": "slides", "main": "slides.html"}},
                                      "port": port}), encoding="utf-8")
    return config, port


def environment(folder: Path, cache: Path) -> dict[str, str]:
    """The environment of a process the test starts: its temporary folder is *folder*, it
    imports this copy of the package, and it hands nothing to a plugin monitor, whose folder
    is under *cache*."""
    return {**os.environ, "TMPDIR": str(folder), "PYTHONPATH": str(REPOSITORY), "XDG_CACHE_HOME": str(cache)}


def browsers(folder: Path) -> list[psutil.Process]:
    """The processes of the browsers whose profiles are in *folder*."""
    return [process for process in psutil.process_iter(["cmdline"])
            if any(argument.startswith(f"--user-data-dir={folder}") for argument in process.info["cmdline"] or ())]


def wait_for_browser(folder: Path, process: subprocess.Popen | None = None) -> None:
    """Wait until a browser runs on a profile in *folder*, started by *process*, which is not
    to have exited meanwhile."""
    deadline = time.monotonic() + 60
    while not browsers(folder):
        assert process is None or process.poll() is None, f"exited with {process.returncode}"
        assert time.monotonic() < deadline, "no browser started"
        time.sleep(0.1)


def left(folder: Path, seconds: float = 2) -> tuple[int, list[str]]:
    """How many browser processes are left on profiles in *folder* once they have had
    *seconds* to exit, and what is left in it: profiles, and the folders browsers make there
    for themselves. Pytest's own folder is not counted."""
    deadline = time.monotonic() + seconds
    while browsers(folder) and time.monotonic() < deadline:
        time.sleep(0.1)
    return len(browsers(folder)), sorted(path.name for path in folder.iterdir()
                                         if not path.name.startswith("pytest-of-"))


def ask_layout(port: int) -> None:
    """Ask for the deck's layout, as the layout tool does, and wait for the answer on a thread
    of its own. The server stops before it answers."""
    def asked() -> None:
        with contextlib.suppress(OSError):
            urllib.request.urlopen(f"http://127.0.0.1:{port}/artifacts/slides/layout", timeout=60).read()

    threading.Thread(target=asked, daemon=True).start()


def serving_mcp(config: Path, port: int, folder: Path, never: Never) -> subprocess.Popen:
    """The MCP server, started in the project of *config* as a client starts it, once it
    serves the project and the page of its layout check waits for the image *never*."""
    # In a process group of its own, as the MCP SDK's client starts it.
    server = subprocess.Popen(MCP, cwd=config.parent, env=environment(folder, config.parent / "cache"),
                              stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              start_new_session=os.name != "nt")
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/state", timeout=2).read()
                break
            except OSError:
                assert server.poll() is None, f"exited with {server.returncode}"
                assert time.monotonic() < deadline, "the server did not start"
                time.sleep(0.1)
        ask_layout(port)
        wait_for_browser(folder, server)
        never.asked()
    except BaseException:
        ended(server)
        raise
    return server


def ended(process: subprocess.Popen) -> None:
    """End a process the test started, if it is still running, and wait for it."""
    if process.poll() is None:
        process.kill()
    process.wait()


@needs_browser
def test_stop_ends_a_check_in_flight_with_its_browser_and_profile(tmp, tmp_path, never, monkeypatch) -> None:
    """stop() returns once the check a layout request waits for has ended, with its browser
    and its profile, and the server's thread with them."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    monkeypatch.setenv("TMPDIR", str(tmp))
    config, port = slow_project(tmp_path, never.url)
    shared = SharedProjectServer(load_config(config))
    try:
        shared.ensure()
        ask_layout(port)
        wait_for_browser(tmp)
        never.asked()
        thread = shared.thread
        shared.stop()
        assert not thread.is_alive()
        assert left(tmp, seconds=0) == (0, [])
    finally:
        shared.stop()


@needs_browser
def test_a_pytest_worker_ending_after_its_test_stops_the_server_leaves_nothing(tmp, tmp_path) -> None:
    """A test stops its server in a finally clause, and its worker ends once the tests are
    done."""
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    test = tmp_path / "test_worker.py"
    test.write_text(textwrap.dedent(f"""
        from pathlib import Path
        from html_mcp_web.config import load_config
        from html_mcp_web.project_server import SharedProjectServer
        from tests.test_check_browser_ends import Never, ask_layout, slow_project

        def test_a_check_in_flight():
            never = Never()
            config, port = slow_project(Path({str(tmp_path / "project")!r}), never.url)
            shared = SharedProjectServer(load_config(config))
            try:
                shared.ensure()
                ask_layout(port)
                never.asked()
            finally:
                shared.stop()
                never.close()
        """), encoding="utf-8")
    worker = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-n", "1", str(test)],
                            cwd=tmp_path, env=environment(tmp, tmp_path / "cache"), stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=100)
    assert worker.returncode == 0, worker.stdout.decode(errors="replace")[-2000:]
    assert left(tmp) == (0, [])


@needs_browser
def test_a_client_closing_the_pipe_leaves_nothing(tmp, tmp_path, never) -> None:
    """A client closes the pipe once it is done with the server, which then stops."""
    config, port = slow_project(tmp_path, never.url)
    server = serving_mcp(config, port, tmp, never)
    try:
        server.stdin.close()
        server.wait(timeout=30)
        assert left(tmp) == (0, [])
    finally:
        ended(server)
