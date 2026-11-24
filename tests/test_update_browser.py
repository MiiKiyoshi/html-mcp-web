"""The ⋯ menu's Update in Firefox, for an install from a git clone: the version line names the
version with the clone's commit, the menu offers Update when the clone's upstream has commits
the clone lacks, and the band under the top bar says what is left once an update is in."""

import asyncio
from pathlib import Path

from html_mcp_web.shared.update import Update, UpdateError
from tests.test_comment_panel_browser import SERVERS, needs_firefox, review_page, wait_until


@needs_firefox
def test_the_more_menu_updates_the_clone_and_says_what_is_left(tmp_path: Path, monkeypatch) -> None:
    """The ⋯ menu names what runs and offers Update only when the upstream has new commits. A
    click updates, and a band stays under the top bar: first to reconnect the agent, since the
    server keeps its code, and once the new code's server answers, to reload the page. An
    install that cannot update itself says to ask the agent, and a failed update says why."""
    newest = {"ahead": None}
    ran = []

    async def news(self):
        return None, newest["ahead"]

    async def run(self):
        ran.append(True)
        monkeypatch.setattr(Update, "on_disk", lambda self: "0.1.0+abc1234")
        return "0.1.0+abc1234"

    monkeypatch.setattr(Update, "news", news)
    monkeypatch.setattr(Update, "run", run)
    monkeypatch.setattr(Update, "way", lambda self: None)
    monkeypatch.setattr(Update, "on_disk", lambda self: self.version)
    with review_page(tmp_path) as (browser, base):
        shared = SERVERS[base]
        update = shared.runner.app["review_server"].update
        script = lambda code: browser.execute_script(code, sandbox=None)
        shown = lambda selector: script(f'return !document.querySelector("{selector}").hidden')
        said = lambda: script('return document.querySelector("#update-alert-text").textContent')

        def asked_again():
            """The page's socket is closed, as when the agent connects again, and the page asks
            the server that answers what runs."""
            server = shared.runner.app["review_server"]

            async def close():
                for socket in list(server.websockets):
                    await socket.close()
            asyncio.run_coroutine_threadsafe(close(), shared.loop).result(5)
            wait_until(lambda: len(server.websockets) == 1, timeout=10)

        # With nothing newer the menu names what runs, the version with the commit.
        wait_until(lambda: script('return document.querySelector("#version-line").textContent')
                   == f"html-mcp-web v{update.version}")
        assert "+" in update.version and not shown("#update-btn") and not shown("#update-alert")
        assert script('return document.querySelector("#more-menu").lastElementChild.id') == "version-line"
        assert script('return document.querySelector("#update-alert").previousElementSibling.matches("header.topbar")')
        newest["ahead"] = 1
        asked_again()
        wait_until(lambda: shown("#update-btn"), timeout=10)
        assert script('return document.querySelector("#update-btn").textContent') == "Update (1 new commit)"
        newest["ahead"] = 3
        asked_again()
        wait_until(lambda: script('return document.querySelector("#update-btn").textContent') == "Update (3 new commits)")
        # An install that cannot update itself runs nothing and says who can.
        script('document.querySelector("#update-btn").click()')
        wait_until(lambda: said() == "3 new commits are out. Ask your agent to update html-mcp-web.")
        assert ran == [] and shown("#update-alert-how")
        assert script('return document.querySelector("#update-alert-how").href').endswith("html-mcp-web/blob/main/INSTALL.md")
        # A failed update says why, and the button stays for another try.

        async def failed(self):
            raise UpdateError("fatal: Not possible to fast-forward, aborting.")

        monkeypatch.setattr(Update, "way", lambda self: "checkout")
        monkeypatch.setattr(Update, "run", failed)
        asked_again()
        wait_until(lambda: script('return document.querySelector("#update-btn").dataset.selfUpdate') == "true", timeout=10)
        script('document.querySelector("#update-btn").click()')
        wait_until(lambda: said() == "The update failed.\nfatal: Not possible to fast-forward, aborting.")
        assert shown("#update-btn") and script('return document.querySelector("#update-btn").disabled') is False
        # One that goes through: the server keeps its code, so the band asks for the agent to
        # connect again, and the menu offers no second update.
        monkeypatch.setattr(Update, "run", run)
        script('document.querySelector("#update-btn").click()')
        wait_until(lambda: said() == "Updated to v0.1.0+abc1234. Reconnect html-mcp in your agent to start using it.")
        assert ran == [True] and not shown("#update-btn") and not shown("#update-reload-btn")
        # The server that answers after the agent connected again runs the new code: the page,
        # loaded from the old one, asks to be reloaded.
        monkeypatch.setattr(update, "version", "0.1.0+abc1234")
        newest["ahead"] = 0
        asked_again()
        wait_until(lambda: said() == "html-mcp-web v0.1.0+abc1234 is now running. Reload this page to use it.", timeout=10)
        assert shown("#update-reload-btn") and not shown("#update-alert-how")
        script('document.querySelector("#update-reload-btn").click()')
        wait_until(lambda: script('return document.querySelector("#update-alert")?.hidden === true'
                                  ' && document.querySelector("#version-line").textContent') == "html-mcp-web v0.1.0+abc1234",
                   timeout=10)
        assert not shown("#update-btn")
