"""A Chrome the package starts, to check a layout, print a page or set a report's pages
(html_mcp_web/chrome.py)."""

import os
import shutil
import socket
from pathlib import Path

import pytest

from html_mcp_web import chrome
from tests.html_chrome import needs_browser


def test_chrome_is_looked_for_before_chromium_and_edge(tmp_path: Path, monkeypatch) -> None:
    """Chrome is taken when there is one, then Chromium, then Edge, which every Windows has."""
    # None where a Mac's or Windows' installers put them, only on the PATH.
    monkeypatch.setattr(chrome.sys, "platform", "linux")
    for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        monkeypatch.setenv(variable, str(tmp_path))
    for installed, found in ((["msedge", "chromium", "google-chrome"], "google-chrome"),
                             (["msedge", "chromium"], "chromium"), (["msedge"], "msedge"), ([], None)):
        monkeypatch.setattr(shutil, "which", lambda name, installed=installed: f"/bin/{name}" if name in installed else None)
        assert chrome.binary() == (None if found is None else f"/bin/{found}")


@needs_browser
def test_a_chrome_is_gone_with_its_profile_once_its_page_closes(monkeypatch) -> None:
    """Nothing listens on its port afterwards, its profile is removed, which Windows refuses
    while a browser still holds it, and the folder it kept its socket in, outside the profile,
    is gone too: a browser ended by a signal left that folder behind."""
    made: list[str] = []
    pinned = chrome.profile

    def kept(prefix: str) -> str:
        made.append(pinned(prefix))
        return made[-1]

    monkeypatch.setattr(chrome, "profile", kept)
    with chrome.chrome() as page:
        page.navigate("data:text/html,<p>page")
        assert page.execute_script("return document.body.textContent") == "page"
        port = int(chrome._endpoint(made[0]).split(":")[2].split("/")[0])
        link = Path(made[0], "SingletonSocket")
        socket_folder = Path(os.readlink(link)).parent if link.is_symlink() else None
    assert not Path(made[0]).exists()
    assert socket_folder is None or not socket_folder.exists()
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0


@pytest.mark.skipif(os.name == "nt", reason="Chrome on Windows keeps no socket in the temporary folder")
def test_a_profile_goes_with_the_folder_its_browser_kept_its_socket_in(tmp_path: Path) -> None:
    """A browser ended by a signal leaves the folder it kept its socket in, beside its profile
    in the temporary folder, and the folder goes with the profile. A folder elsewhere that a
    profile's link points to is left alone."""
    for name, place in (("profile_a", tmp_path), ("profile_b", tmp_path / "elsewhere")):
        profile, own = tmp_path / name, place / f"com.google.Chrome.{name}"
        own.mkdir(parents=True)
        (own / "SingletonSocket").touch()
        profile.mkdir()
        (profile / "SingletonSocket").symlink_to(own / "SingletonSocket")
        chrome.remove(str(profile))
        assert not profile.exists()
    assert sorted(path.name for path in tmp_path.rglob("com.google.Chrome.*")) == ["com.google.Chrome.profile_b"]


@needs_browser
def test_chromes_started_at_once_each_open_their_page() -> None:
    """The server's layout checks, prints and the browser tests start browsers side by side,
    each headless on a profile of its own with the page it is to open. Each asks for its page,
    and is gone with its profile once stopped."""
    import http.server
    import threading
    import time

    asked: list[int] = []

    class Page(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            asked.append(self.server.server_port)
            body = b"<!doctype html><title>page</title><p>page"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    servers = [http.server.ThreadingHTTPServer(("127.0.0.1", 0), Page) for _ in range(4)]
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    profiles = [chrome.profile("html_mcp_together_") for _ in servers]
    processes = [chrome.start(profile, f"http://127.0.0.1:{server.server_port}/")
                 for server, profile in zip(servers, profiles)]
    try:
        deadline = time.monotonic() + 40
        while set(asked) != {server.server_port for server in servers} and time.monotonic() < deadline:
            time.sleep(0.2)
        assert sorted(set(asked)) == sorted(server.server_port for server in servers)
    finally:
        for process, profile in zip(processes, profiles):
            chrome.stop(process, profile)
        for server in servers:
            server.shutdown()
    for profile in profiles:
        shutil.rmtree(profile)
