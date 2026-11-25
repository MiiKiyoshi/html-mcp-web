"""The headless Firefox the browser tests drive, found and ended as the package finds and ends
it (html_mcp_web/firefox.py), and what a failing test leaves of the page it had open."""

import base64
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
from marionette_driver.marionette import Marionette

from html_mcp_web.firefox import binary, command, headless_environment
from html_mcp_web.server import HtmlReviewServer

FIREFOX = binary()
needs_firefox = pytest.mark.skipif(FIREFOX is None, reason="Firefox is required")
# What the page writes to its console, in its profile, for keep_failure.
CONSOLE = "console.log"
# The key the page's own shortcuts are held with: Cmd on a Mac, where Option stands for Alt, and
# Ctrl elsewhere (shared/dom.js).
MOD = "\ue03d" if sys.platform == "darwin" else "\ue009"
# The names the page gives those keys, in its tooltips and its notes.
MOD_ALT = "Cmd+Option" if sys.platform == "darwin" else "Ctrl+Alt"
# A test that waits for the outcome of the server's layout check waits as long as the server
# allows a check, and CHECK_MARGIN beyond it for what comes before and after the check itself:
# the page loading and asking for it, and the outcome reaching the page or the state.
LAYOUT_CHECK_SECONDS = HtmlReviewServer.LAYOUT_CHECK_SECONDS
CHECK_MARGIN = 15.0


def launch(profile: str, *arguments: str) -> subprocess.Popen:
    """A headless Firefox under marionette on *profile*, whose user.js names the marionette
    port, with *arguments* before the blank page it opens. The page's console goes to a file in
    the profile."""
    with open(Path(profile, "user.js"), "a", encoding="utf-8") as prefs:
        prefs.write('user_pref("devtools.console.stdout.content", true);\n')
    with open(Path(profile, CONSOLE), "wb") as console:
        return subprocess.Popen(
            command("-marionette", "-headless", "-no-remote", "-profile", profile, *arguments, "about:blank"),
            stdin=subprocess.DEVNULL, stdout=console, stderr=subprocess.STDOUT, env=headless_environment())


class Browser(Marionette):
    """A marionette client that, when a test ends its session while failing, first keeps
    what the page showed in the folder HTML_MCP_FAILURES names, which the CI keeps."""

    cleaning = False

    def delete_session(self, send_request: bool = True):
        # A test ends its session in a finally clause, so a failing one ends it with its
        # failure still on its way out, a failure that passes when run again too. Marionette
        # ends a session itself as well: without a request when its connection fails, and in
        # cleanup when a client that still has one is collected. Neither is a test's end.
        failure = sys.exc_info()[1]
        if (send_request and self.session is not None and not self.cleaning and failure is not None
                and not isinstance(failure, pytest.skip.Exception) and os.environ.get("HTML_MCP_FAILURES")):
            self.keep_failure(Path(os.environ["HTML_MCP_FAILURES"]))
        return super().delete_session(send_request)

    def cleanup(self):
        self.cleaning = True
        super().cleanup()

    def keep_failure(self, folder: Path) -> None:
        """The page as the test left it, under the test's name: a screenshot, the page's markup,
        the values of its fields and where the focus is, and its console. Each part that cannot
        be had is said in the record instead."""
        test = os.environ.get("PYTEST_CURRENT_TEST", "test").split(" ")[0]
        name = f"{re.sub(r'[^A-Za-z0-9_-]+', '_', test)[-120:]}-{time.time_ns()}"
        folder.mkdir(parents=True, exist_ok=True)
        record: dict[str, object] = {"test": test, "error": repr(sys.exc_info()[1])[:2000]}
        try:
            (folder / f"{name}.png").write_bytes(base64.b64decode(self.screenshot()))
        except Exception as error:
            record["screenshot"] = repr(error)
        try:
            (folder / f"{name}.html").write_text(
                self.execute_script("return document.documentElement.outerHTML"), encoding="utf-8")
            record["page"] = self.execute_script("""
              const named = (node) => node.id ? `#${node.id}` : `${node.tagName.toLowerCase()}.${[...node.classList].join(".")}`;
              return {url: location.href, focus: document.activeElement ? named(document.activeElement) : null,
                      fields: [...document.querySelectorAll("textarea, input, select")].filter((field) => field.value)
                        .map((field) => [named(field), field.closest("[data-comment-id]")?.dataset.commentId ?? null, field.value])};""")
        except Exception as error:
            record["page"] = repr(error)
        try:
            said = Path(self.session_capabilities["moz:profile"], CONSOLE).read_text(encoding="utf-8", errors="replace")
            record["console"] = [line for line in said.splitlines()
                                 if line.startswith(("console.", "JavaScript error", "JavaScript warning"))][-200:]
        except Exception as error:
            record["console"] = repr(error)
        (folder / f"{name}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    # Run by the CI before the tests: on a runner without Firefox every browser test would be
    # skipped and the job would pass.
    from html_mcp_web.firefox import firefox

    if FIREFOX is None:
        sys.exit("No Firefox found: every browser test would be skipped.")
    started = time.monotonic()
    with firefox() as client:
        client.navigate("data:text/html,<!doctype html><p>Firefox</p>")
        base64.b64decode(client.screenshot())
        version = client.session_capabilities["browserVersion"]
    print(f"Firefox {version}, {FIREFOX}: started, drew a page and ended in {time.monotonic() - started:.1f} s")
