"""A Firefox the package starts, to print a page or set a report's pages (html_mcp_web/firefox.py)."""

import socket
from pathlib import Path

from html_mcp_web.firefox import firefox
from tests.firefox import needs_firefox


@needs_firefox
def test_a_firefox_is_gone_with_its_profile_once_its_session_ends() -> None:
    """Nothing listens on its port afterwards, and its profile is removed, which Windows
    refuses while a browser still holds it."""
    with firefox() as client:
        port = client.port
        profile = Path(client.session_capabilities["moz:profile"])
        assert profile.is_dir()
    assert not profile.exists()
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0


@needs_firefox
def test_firefoxes_started_at_once_each_open_their_page() -> None:
    """The server's layout checks, prints and the browser tests start Firefoxes side by side,
    each headless on a profile of its own with the page it is to open. Started at once on
    Windows, most of four once stayed on a blank page. Each asks for its page, and is gone
    with its profile once ended."""
    import http.server
    import shutil
    import subprocess
    import tempfile
    import threading
    import time

    from html_mcp_web.firefox import command, headless_environment, stop

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
    profiles = [tempfile.mkdtemp(prefix="html_mcp_together_") for _ in servers]
    processes = [subprocess.Popen(
        command("-headless", "-no-remote", "-profile", profile, f"http://127.0.0.1:{server.server_port}/"),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=headless_environment())
        for server, profile in zip(servers, profiles)]
    try:
        deadline = time.monotonic() + 40
        while set(asked) != {server.server_port for server in servers} and time.monotonic() < deadline:
            time.sleep(0.2)
        assert sorted(set(asked)) == sorted(server.server_port for server in servers)
    finally:
        for process in processes:
            stop(process)
        for server in servers:
            server.shutdown()
    for profile in profiles:
        shutil.rmtree(profile)
