"""The review page in Google Chrome, or in Safari on macOS, for the tests, and what a failing
test leaves of the page it had open.

Chrome is the one the package finds (html_mcp_web/chrome.py), driven through Selenium, which
fetches the driver that fits it. ``launch()`` gives a headless window.
``HTML_MCP_BROWSER=headed`` shows it, to watch a test run. ``HTML_MCP_BROWSER_KIND=safari``
runs the same tests in Safari through safaridriver, which must be enabled once
(``safaridriver --enable``). Safari has no headless window and runs one automation session at
a time, so its window shows and the tests take it in turn. Its driver opens no file from a
test's temporary folder, so a file is served to it from its folder over HTTP. What Safari cannot
be made to do, a test marks with ``not_in_safari``.

Every Chrome a test starts, its own and those the package starts for it, sets the generic
font families in the faces the tests were written with (tests/fonts.py)."""

from __future__ import annotations

import base64
import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import url2pathname

import psutil
import pytest
from selenium import webdriver
from selenium.common.exceptions import NoAlertPresentException, SessionNotCreatedException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys  # noqa: F401  (the tests' keys)

from html_mcp_web.chrome import binary
from html_mcp_web.server import HtmlReviewServer
from tests.fonts import FONTS

KIND = os.environ.get("HTML_MCP_BROWSER_KIND", "chrome")
assert KIND in ("chrome", "safari"), f"HTML_MCP_BROWSER_KIND is chrome or safari, not {KIND}"
CHROME = binary()
if KIND == "chrome":
    needs_browser = pytest.mark.skipif(CHROME is None, reason="Chrome or Edge is required")
else:
    needs_browser = pytest.mark.skipif(shutil.which("safaridriver") is None, reason="Safari on macOS is required")


def not_in_safari(reason: str):
    """Skip a test in Safari, which cannot do what the reason says."""
    return pytest.mark.skipif(KIND == "safari", reason=f"Safari: {reason}")


# The key the page's own shortcuts are held with: Cmd on a Mac, where Option stands for Alt, and
# Ctrl elsewhere (shared/dom.js).
MOD = "" if sys.platform == "darwin" else ""
# The names the page gives those keys, in its tooltips and its notes.
MOD_ALT = "Cmd+Option" if sys.platform == "darwin" else "Ctrl+Alt"
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


class ActionSequence:
    """One input device's actions, built up and then performed: a keyboard's keys, or a
    mouse's or a finger's moves and presses, at the page's own coordinates."""

    def __init__(self, browser: "Chrome", kind: str, name: str, parameters: dict | None = None):
        self.browser, self.steps = browser, []
        self.source = {"type": kind, "id": name, **({"parameters": parameters} if parameters else {})}

    def key_down(self, key: str) -> "ActionSequence":
        self.steps.append({"type": "keyDown", "value": key})
        return self

    def key_up(self, key: str) -> "ActionSequence":
        self.steps.append({"type": "keyUp", "value": key})
        return self

    def pointer_move(self, x: float, y: float, duration: int = 0) -> "ActionSequence":
        self.steps.append({"type": "pointerMove", "x": int(x), "y": int(y), "duration": duration, "origin": "viewport"})
        return self

    def pointer_down(self, button: int = 0) -> "ActionSequence":
        self.steps.append({"type": "pointerDown", "button": button})
        return self

    def pointer_up(self, button: int = 0) -> "ActionSequence":
        self.steps.append({"type": "pointerUp", "button": button})
        return self

    def pause(self, duration: int) -> "ActionSequence":
        self.steps.append({"type": "pause", "duration": duration})
        return self

    def perform(self) -> None:
        self.browser.driver.execute("actions", {"actions": [{**self.source, "actions": self.steps}]})
        self.steps = []


class Chrome:
    """A Chrome window on the review page. *touch* makes its pointer a finger, *user_agent*
    has it say it is another browser, and *fullscreen* False takes its full screen away, as an
    iPhone's Safari has none for a page."""

    def __init__(self, downloads: Path | None = None, touch: bool = False, user_agent: str | None = None,
                 fullscreen: bool = True):
        edge = Path(CHROME).stem.lower() in ("msedge", "microsoft-edge", "microsoft-edge-stable")
        options = webdriver.EdgeOptions() if edge else webdriver.ChromeOptions()
        options.binary_location = CHROME
        environment = dict(os.environ)
        if os.environ.get("HTML_MCP_BROWSER") != "headed":
            options.add_argument("--headless=new")
            # A headless Chrome still connects to the display it is given. Over ssh with X
            # forwarding that display is the far machine's, which prints a refusal for each try.
            for name in ("DISPLAY", "WAYLAND_DISPLAY"):
                environment.pop(name, None)
        # A container has no user namespace for Chrome's sandbox, and its /dev/shm is small. A
        # key's scroll lands at once, as a test reads it: a smooth one went on past a scroll the
        # page made after it. The rest are the package's own (html_mcp_web/chrome.py).
        for flag in ("--no-sandbox", "--disable-dev-shm-usage", "--window-size=1500,1000",
                     "--force-device-scale-factor=1", "--disable-smooth-scrolling", "--hide-scrollbars",
                     "--password-store=basic", "--use-mock-keychain", "--disable-component-update",
                     "--disable-background-networking"):
            options.add_argument(flag)
        options.set_capability("unhandledPromptBehavior", "ignore")
        # The page's console, kept for what a failing test leaves behind (keep_failure).
        options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
        preferences = {f"webkit.webprefs.fonts.{generic}.Zyyy": family for generic, family in FONTS.items()}
        if downloads is not None:
            preferences.update({"download.default_directory": str(downloads), "download.prompt_for_download": False,
                                "plugins.always_open_pdf_externally": True})
        options.add_experimental_option("prefs", preferences)
        driver, service = (webdriver.Edge, webdriver.EdgeService) if edge else (webdriver.Chrome, webdriver.ChromeService)
        self.driver = driver(options=options, service=service(env=environment))
        self.driver.set_script_timeout(60)
        # The tests are written for a light system. A machine set to dark, whose setting
        # reaches headless Chrome, would otherwise turn System to dark.
        self.prefer_scheme(None)
        if touch:
            # A finger is a coarse pointer, which the page's touch rules key off.
            self.driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
        if user_agent is not None:
            self.driver.execute_cdp_cmd("Emulation.setUserAgentOverride", {"userAgent": user_agent})
        if not fullscreen:
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": 'Object.defineProperty(Document.prototype, "fullscreenEnabled", {get: () => false});'})

    def quit(self) -> None:
        # A test quits its browser in a finally clause, so a failing one quits with its failure
        # still on its way out: what the page showed then is kept in the folder
        # HTML_MCP_FAILURES names, which the CI keeps, a failure that passes when run again too.
        failure = sys.exc_info()[1]
        if failure is not None and not isinstance(failure, pytest.skip.Exception) and os.environ.get("HTML_MCP_FAILURES"):
            self.keep_failure(Path(os.environ["HTML_MCP_FAILURES"]))
        # Closed as its own Close does, and given the moment that takes, Chrome leaves nothing
        # in the temporary folder, where its driver's ending left a folder of Chrome's own. It
        # has exited once it waits for its driver to collect it.
        if not isinstance(self, Safari):
            try:
                browsers = psutil.Process(self.driver.service.process.pid).children()
                self.driver.execute_cdp_cmd("Browser.close", {})
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and any(
                        browser.is_running() and browser.status() != psutil.STATUS_ZOMBIE for browser in browsers):
                    time.sleep(0.05)
            except Exception:
                pass
        try:
            self.driver.quit()
        except Exception:
            pass

    def keep_failure(self, folder: Path) -> None:
        """The page as the test left it, under the test's name: a screenshot, the page's markup,
        the values of its fields and where the focus is, its console where the browser gives
        it, and the words of a dialog it left open, which is closed first: Safari answers no
        later command while one is open, and the screenshot waited until the test timed out.
        The record says too at which lines of the tests it failed, which a log leaves out once
        the test passes when run again. Each part that cannot be had is said in the record
        instead."""
        test = os.environ.get("PYTEST_CURRENT_TEST", "test").split(" ")[0]
        name = f"{re.sub(r'[^A-Za-z0-9_-]+', '_', test)[-120:]}-{time.time_ns()}"
        folder.mkdir(parents=True, exist_ok=True)
        _, failure, trace = sys.exc_info()
        record: dict[str, object] = {
            "test": test, "error": repr(failure)[:2000],
            "where": [f"{Path(frame.filename).name}:{frame.lineno}" for frame in traceback.extract_tb(trace)
                      if Path(frame.filename).parent == Path(__file__).parent],
        }
        try:
            dialog = self.driver.switch_to.alert
            record["dialog"] = dialog.text
            dialog.dismiss()
        except NoAlertPresentException:
            pass
        except Exception as error:
            record["dialog"] = repr(error)
        try:
            (folder / f"{name}.png").write_bytes(base64.b64decode(self.driver.get_screenshot_as_base64()))
        except Exception as error:
            record["screenshot"] = repr(error)
        try:
            (folder / f"{name}.html").write_text(
                self.driver.execute_script("return document.documentElement.outerHTML"), encoding="utf-8")
            record["page"] = self.driver.execute_script("""
              const named = (node) => node.id ? `#${node.id}` : `${node.tagName.toLowerCase()}.${[...node.classList].join(".")}`;
              return {url: location.href, focus: document.activeElement ? named(document.activeElement) : null,
                      fields: [...document.querySelectorAll("textarea, input, select")].filter((field) => field.value)
                        .map((field) => [named(field), field.closest("[data-comment-id]")?.dataset.commentId ?? null, field.value])};""")
        except Exception as error:
            record["page"] = repr(error)
        try:
            record["console"] = [f"{entry['level']} {entry['message']}" for entry in self.driver.get_log("browser")][-200:]
        except Exception as error:
            record["console"] = repr(error)
        (folder / f"{name}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")

    def navigate(self, url: str) -> None:
        self.driver.get(url)

    def refresh(self) -> None:
        self.driver.refresh()

    def execute_script(self, script: str, script_args=(), **_):
        """Run the script in the page, its arguments as ``arguments``, and give what it
        returns: a promise's value once it settles. The page's own scope is the only one."""
        return self.driver.execute_script(script, *script_args)

    def set_window_rect(self, x: int = 0, y: int = 0, width: int = 1500, height: int = 1000) -> None:
        """Size the page's viewport, which is what a test measures against."""
        self.driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
            "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})

    @property
    def window_rect(self) -> dict:
        width, height = self.driver.execute_script("return [innerWidth, innerHeight]")
        return {"x": 0, "y": 0, "width": width, "height": height}

    def find_element(self, strategy: str, selector: str):
        assert strategy == "css selector"
        return self.driver.find_element(By.CSS_SELECTOR, selector)

    def screenshot(self, format: str = "base64"):
        shot = self.driver.get_screenshot_as_base64()
        return base64.b64decode(shot) if format == "binary" else shot

    def out_of_sight(self, hidden: bool) -> None:
        """Take the page out of sight, as a tab behind another is, or bring it back. Every tab
        of a headless Chrome stays in sight, so its window is minimized instead."""
        window = self.driver.execute_cdp_cmd("Browser.getWindowForTarget", {})["windowId"]
        self.driver.execute_cdp_cmd("Browser.setWindowBounds", {
            "windowId": window, "bounds": {"windowState": "minimized" if hidden else "normal"}})

    def prefer_scheme(self, scheme: str | None) -> None:
        """Have the system say it prefers dark or light, or with None light, the scheme the
        tests take a system to have whatever this machine is set to."""
        self.driver.execute_cdp_cmd("Emulation.setEmulatedMedia", {
            "features": [{"name": "prefers-color-scheme", "value": scheme or "light"}]})

    def platform(self, name: str) -> None:
        """Have the browser say it runs on the system *name*, as navigator.platform gives it,
        for the pages loaded from then on."""
        self.driver.execute_cdp_cmd("Emulation.setUserAgentOverride", {
            "userAgent": self.driver.execute_script("return navigator.userAgent"), "platform": name})


def osascript(script: str) -> str:
    return subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL).stdout.strip()


class QuietFiles(http.server.SimpleHTTPRequestHandler):
    """A folder's files for Safari, with no line printed for each request."""

    def log_message(self, format: str, *args) -> None:
        pass


class SafariElement:
    """An element in Safari, clicked as a pointer does it. The driver's own click, and a
    quick pointer press, sometimes reach the page as a release before the press when they
    closely follow another click, and the page then sees no click at all. A pause before
    the press and before the release keeps them in order."""

    def __init__(self, browser: "Safari", element):
        self.browser, self.element = browser, element

    def __getattr__(self, name: str):
        return getattr(self.element, name)

    def click(self) -> None:
        box = self.browser.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'nearest', inline: 'nearest'});"
            " const box = arguments[0].getBoundingClientRect();"
            " return [box.left + box.width / 2, box.top + box.height / 2];", self.element)
        ActionSequence(self.browser, "pointer", "mouse", {"pointerType": "mouse"}) \
            .pointer_move(box[0], box[1]).pause(50).pointer_down().pause(50).pointer_up().perform()


class Safari(Chrome):
    """A Safari window on the review page. It shows on the screen, since Safari has no
    headless window, and its viewport is sized by sizing the window around it."""

    def __init__(self, downloads: Path | None = None, touch: bool = False, user_agent: str | None = None,
                 fullscreen: bool = True):
        assert downloads is None and not touch and user_agent is None and fullscreen, \
            "a test that needs these is marked not_in_safari"
        self.files: http.server.ThreadingHTTPServer | None = None
        options = webdriver.SafariOptions()
        options.set_capability("unhandledPromptBehavior", "ignore")
        # One session at a time: the one before may still be closing. One that never closes,
        # left by a test that hung, would refuse every test after it, so Safari and its driver
        # are then ended and started afresh.
        deadline, ended = time.monotonic() + 30, False
        while True:
            try:
                self.driver = webdriver.Safari(options=options)
                break
            except SessionNotCreatedException:
                if time.monotonic() > deadline:
                    if ended:
                        raise
                    for program in ("Safari", "safaridriver"):
                        subprocess.run(["pkill", "-x", program], stdin=subprocess.DEVNULL, check=False)
                    deadline, ended = time.monotonic() + 30, True
                time.sleep(1)
        self.driver.set_script_timeout(60)
        # Safari may open the window in full screen, which no window size changes, and
        # behind another program's window, where no pointer or key action reaches its page.
        window = 'tell application "System Events" to tell process "Safari" to '
        osascript(window + "set frontmost to true")
        if osascript(window + 'get value of attribute "AXFullScreen" of every window') == "true":
            osascript(window + 'set value of attribute "AXFullScreen" of window 1 to false')
            time.sleep(2)
        self.set_window_rect()
        self.system_dark = None
        self.prefer_scheme(None)

    def quit(self) -> None:
        if self.system_dark is not None:
            self.dark(self.system_dark)
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

    def _loaded(self) -> None:
        """Wait for the page's scripts to have run: Safari's driver gives a page back while
        it is still loading, before the page has wired up what a test presses next."""
        deadline = time.monotonic() + 30
        while self.driver.execute_script("return document.readyState") != "complete" and time.monotonic() < deadline:
            time.sleep(0.05)

    def navigate(self, url: str) -> None:
        super().navigate(self._reachable(url))
        self._loaded()

    def refresh(self) -> None:
        super().refresh()
        self._loaded()

    def set_window_rect(self, x: int = 0, y: int = 0, width: int = 1500, height: int = 1000) -> None:
        """Size the window so that the viewport inside it has the size asked for."""
        self.driver.set_window_rect(x=x, y=y, width=width, height=height)
        for _ in range(3):
            inner = self.driver.execute_script("return [innerWidth, innerHeight]")
            if inner == [width, height]:
                return
            rect = self.driver.get_window_rect()
            self.driver.set_window_rect(x=x, y=y, width=rect["width"] + width - inner[0],
                                        height=rect["height"] + height - inner[1])

    def screenshot(self, format: str = "base64"):
        """The viewport at one image pixel per CSS pixel, as the tests measure it."""
        import pymupdf
        shot = base64.b64decode(self.driver.get_screenshot_as_base64())
        pixmap = pymupdf.Pixmap(shot)
        ratio = round(pixmap.width / self.driver.execute_script("return innerWidth"))
        if ratio > 1:
            pixmap.shrink(ratio.bit_length() - 1)
            shot = pixmap.tobytes("png")
        return shot if format == "binary" else base64.b64encode(shot).decode()

    def platform(self, name: str) -> None:
        pytest.skip("Safari: the system a browser says it runs on cannot be set")

    def out_of_sight(self, hidden: bool) -> None:
        pytest.skip("Safari: a window taken out of sight is not brought back by its driver")

    def find_element(self, strategy: str, selector: str):
        return SafariElement(self, super().find_element(strategy, selector))

    @staticmethod
    def dark(value: bool | None = None) -> bool:
        """The system's appearance is dark, or is set to dark or light."""
        script = 'tell application "System Events" to tell appearance preferences to '
        return osascript(script + ("get dark mode" if value is None
                                   else f"set dark mode to {str(value).lower()}")) == "true"

    def prefer_scheme(self, scheme: str | None) -> None:
        """Safari takes the colour scheme from the system alone, so this sets the system's
        appearance, dark or light (None), and quitting puts back the one it had."""
        if self.system_dark is None:
            self.system_dark = self.dark()
        if self.dark() != (scheme == "dark"):
            self.dark(scheme == "dark")


def launch(downloads: Path | None = None, touch: bool = False, user_agent: str | None = None,
           fullscreen: bool = True) -> Chrome:
    return (Safari if KIND == "safari" else Chrome)(downloads, touch, user_agent, fullscreen)


if __name__ == "__main__":
    # Run by the CI before the tests: on a runner without Chrome every browser test would be
    # skipped and the job would pass.
    from html_mcp_web.chrome import chrome

    if CHROME is None:
        sys.exit("No Chrome or Edge found: every browser test would be skipped.")
    started = time.monotonic()
    with chrome() as page:
        page.navigate("data:text/html,<!doctype html><p>Chrome</p>")
        page.screenshot([0, 0, 100, 40])
        version = page.call("Browser.getVersion")["product"]
    print(f"{version}, {CHROME}: started, drew a page and ended in {time.monotonic() - started:.1f} s")
