"""The browser html-mcp-web's tests drive: the one the review tools share (tests/chrome.py), with
what this tool's tests alone need.

Chrome is the one the package finds (html_mcp_web/chrome.py), which may be Chromium or Edge. It
starts with the package's own flags and one that makes a key's scroll land at once, and it sets
the generic font families in the faces the tests were written with (tests/fonts.py), as every
Chrome the package starts for a test does (tests/conftest.py). Safari's driver opens no file
from a test's temporary folder, so a file is served to it from its folder over HTTP.

Run by the CI as python -m tests.html_chrome before the tests."""

from __future__ import annotations

import functools
import http.server
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import url2pathname

import pytest
from selenium import webdriver

from html_mcp_web.chrome import binary
from html_mcp_web.server import HtmlReviewServer
from tests import chrome
from tests.fonts import FONTS

CHROME = binary()
EDGE = CHROME is not None and Path(CHROME).stem.lower() in ("msedge", "microsoft-edge", "microsoft-edge-stable")
if chrome.KIND == "chrome":
    needs_browser = pytest.mark.skipif(CHROME is None, reason="Chrome or Edge is required")
else:
    needs_browser = chrome.needs_browser

# A test that waits for the outcome of the server's layout check waits as long as the server
# allows a check, and CHECK_MARGIN beyond it for what comes before and after the check itself:
# the page loading and asking for it, and the outcome reaching the page or the state.
LAYOUT_CHECK_SECONDS = HtmlReviewServer.LAYOUT_CHECK_SECONDS
CHECK_MARGIN = 15.0
# What a test waiting for the review page to say "ready" reports when it does not: the status
# the page shows, and each artifact's layout check and error as the server has them.
READY_SEEN = """
  const status = document.querySelector("#artifact-status")?.textContent;
  return fetch("/state").then((reply) => reply.json()).then((state) => JSON.stringify({status,
    artifacts: Object.fromEntries(Object.entries(state.artifacts).map(([alias, artifact]) =>
      [alias, {error: artifact.error, checked: artifact.layout_check.checked_revision, revision: artifact.revision,
               errors: artifact.layout_check.errors, warnings: artifact.layout_check.warnings}]))}).slice(0, 3000));
"""


class Chrome(chrome.Chrome):
    """A Chrome window on the review page. *user_agent* has it say it is another browser, and
    *fullscreen* False takes its full screen away, as an iPhone's Safari has none for a page."""

    def __init__(self, downloads: Path | None = None, touch: bool = False, user_agent: str | None = None,
                 fullscreen: bool = True):
        super().__init__(downloads, touch)
        if user_agent is not None:
            self.user_agent(user_agent)
        if not fullscreen:
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": 'Object.defineProperty(Document.prototype, "fullscreenEnabled", {get: () => false});'})

    def options(self) -> webdriver.ChromeOptions:
        options = webdriver.EdgeOptions() if EDGE else webdriver.ChromeOptions()
        options.binary_location = CHROME
        # A key's scroll lands at once, as a test reads it: a smooth one went on past a scroll the
        # page made after it. The rest are the package's own (html_mcp_web/chrome.py).
        for flag in ("--disable-smooth-scrolling", "--password-store=basic", "--use-mock-keychain",
                     "--disable-component-update", "--disable-background-networking"):
            options.add_argument(flag)
        options.add_experimental_option("prefs", {f"webkit.webprefs.fonts.{generic}.Zyyy": family
                                                  for generic, family in FONTS.items()})
        return options

    def start(self, options: webdriver.ChromeOptions, environment: dict[str, str]):
        if EDGE:
            return webdriver.Edge(options=options, service=webdriver.EdgeService(env=environment))
        return super().start(options, environment)

    def out_of_sight(self, hidden: bool) -> None:
        """Take the page out of sight, as a tab behind another is, or bring it back. Every tab
        of a headless Chrome stays in sight, so its window is minimized instead."""
        window = self.driver.execute_cdp_cmd("Browser.getWindowForTarget", {})["windowId"]
        self.driver.execute_cdp_cmd("Browser.setWindowBounds", {
            "windowId": window, "bounds": {"windowState": "minimized" if hidden else "normal"}})


class QuietFiles(http.server.SimpleHTTPRequestHandler):
    """A folder's files for Safari, with no line printed for each request."""

    def log_message(self, format: str, *args) -> None:
        pass


class Safari(chrome.Safari):
    """A Safari window on the review page, which opens a file of a test's temporary folder over
    HTTP."""

    def __init__(self, downloads: Path | None = None, touch: bool = False, user_agent: str | None = None,
                 fullscreen: bool = True):
        assert user_agent is None and fullscreen, "a test that needs these is marked not_in_safari"
        self.files: http.server.ThreadingHTTPServer | None = None
        super().__init__(downloads, touch)

    def quit(self) -> None:
        super().quit()
        self._serve(None)

    def _serve(self, folder: Path | None) -> None:
        """Serve *folder* over HTTP on a port of its own, or with None nothing."""
        if self.files is not None:
            self.files.shutdown()
            self.files.server_close()
            self.files = None
        if folder is not None:
            self.files = http.server.ThreadingHTTPServer(
                ("127.0.0.1", 0), functools.partial(QuietFiles, directory=str(folder)))
            self.files.folder = folder
            threading.Thread(target=self.files.serve_forever, daemon=True).start()

    def _reachable(self, url: str) -> str:
        """The address Safari opens for *url*. Its driver loads no file from outside
        Safari's sandbox, which a test's temporary folder is, and shows an error page
        instead: a file is served from its own folder, with what lies beside it, which a
        page refers to as it would beside the file."""
        if urlsplit(url).scheme != "file":
            return url
        page = Path(url2pathname(urlsplit(url).path))
        if self.files is None or self.files.folder != page.parent:
            self._serve(page.parent)
        return f"http://127.0.0.1:{self.files.server_address[1]}/{quote(page.name)}"

    def navigate(self, url: str) -> None:
        super().navigate(self._reachable(url))

    def out_of_sight(self, hidden: bool) -> None:
        pytest.skip("Safari: a window taken out of sight is not brought back by its driver")


def launch(downloads: Path | None = None, touch: bool = False, user_agent: str | None = None,
           fullscreen: bool = True) -> Chrome:
    return (Safari if chrome.KIND == "safari" else Chrome)(downloads, touch, user_agent, fullscreen)


if __name__ == "__main__":
    # Run by the CI before the tests: on a runner without Chrome every browser test would be
    # skipped and the job would pass.
    from html_mcp_web.chrome import chrome as package_chrome

    if CHROME is None:
        sys.exit("No Chrome or Edge found: every browser test would be skipped.")
    started = time.monotonic()
    with package_chrome() as page:
        page.navigate("data:text/html,<!doctype html><p>Chrome</p>")
        page.screenshot([0, 0, 100, 40])
        version = page.call("Browser.getVersion")["product"]
    print(f"{version}, {CHROME}: started, drew a page and ended in {time.monotonic() - started:.1f} s")
