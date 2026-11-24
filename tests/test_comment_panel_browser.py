"""The comment panel the review pages share, as this page uses it, in Firefox: its search, its
orders, the line that undoes a change of status, the row above the list, and how each artifact
keeps its own comments."""

import json
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from html_mcp_web.comments import ArtifactAnchor, CommentStore, PageAnchor, SourceAnchor, SuggestedEdit
from html_mcp_web.config import load_config
from html_mcp_web.project_server import SharedProjectServer

marionette = pytest.importorskip("marionette_driver.marionette")
needs_firefox = pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")

DECK = ('<!doctype html><html><head><meta charset="utf-8"><title>Slides</title></head><body><main class="pages">'
        '<section class="page"><h1>First</h1><p>Tea is served.</p></section></main></body></html>')
TEXT_SIZES = 'return [...document.querySelectorAll("[data-text-choice]")].map((button) => button.dataset.textChoice)'
FITTED = 'return new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(true))))'
# The page's own fetch, wrapped so a test sees each call it makes and can hold the ones it names
# until it lets them go: window.calls lists "METHOD path", window.hold names what waits, and
# window.release() sends what waited. Run in the page's own scope (sandbox=None), as everything
# that reads them is.
WATCH_CALLS = '''
  window.calls = [];
  window.held = [];
  window.hold = null;
  const sent = window.fetch.bind(window);
  window.fetch = (url, options = {}) => {
    const call = `${options.method ?? "GET"} ${new URL(url, location.href).pathname}`;
    window.calls.push(call);
    if (window.hold !== null && window.hold(call)) return new Promise((go) => window.held.push(() => go(sent(url, options))));
    return sent(url, options);
  };
  window.release = () => {
    const held = window.held;
    window.held = [];
    window.hold = null;
    held.forEach((go) => go());
  };
'''


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_until(check, timeout: float = 15.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            last = check()
            if last:
                return last
        except Exception as error:
            last = error
        time.sleep(0.1)
    raise AssertionError(f"condition was not met: {last}")


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.loads(response.read().decode("utf-8") or "null")


def local_moment(month: int, day: int, hour: int = 12, minute: int = 0) -> str:
    """A moment this year on this machine's clock, which the browser's is."""
    return datetime(datetime.now().year, month, day, hour, minute).astimezone().isoformat()


def store_of(root: Path, alias: str) -> Path:
    """Where the server keeps an artifact's comments."""
    path = root / ".html-mcp-web" / "comments" / f"{alias}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def stamp(store: Path, moments: dict[str, list[str]]) -> None:
    """The stored comments written at the moments given, entry by entry: each one made at its
    first entry and touched last at its last."""
    data = json.loads(store.read_text(encoding="utf-8"))
    for comment in data["comments"]:
        if comment["id"] in moments:
            for entry, at in zip(comment["thread"], moments[comment["id"]]):
                entry["at"] = at
            comment["created"], comment["updated"] = moments[comment["id"]][0], moments[comment["id"]][-1]
    store.write_text(json.dumps(data), encoding="utf-8")


@contextmanager
def review_page(root: Path, aliases=("slides",)):
    """The review page of a project of one deck per alias, each in a folder of its own, opened in
    a headless Firefox 1500 by 1000, with its server's address."""
    for alias in aliases:
        (root / alias).mkdir()
        (root / alias / "slides.html").write_text(DECK, encoding="utf-8")
    port = available_port()
    config_path = root / ".html-mcp-web.yaml"
    config_path.write_text(yaml.safe_dump({
        "artifacts": {alias: {"layout": "slides", "main": f"{alias}/slides.html"} for alias in aliases},
        "watch": ["*.html"], "port": port}, sort_keys=False), encoding="utf-8")
    shared = SharedProjectServer(load_config(config_path))
    profile = tempfile.mkdtemp(prefix="html_mcp_panel_")
    marionette_port = available_port()
    (Path(profile) / "user.js").write_text(f'user_pref("marionette.port", {marionette_port});\n', encoding="utf-8")
    process = None
    browser = None
    try:
        shared.ensure()
        process = subprocess.Popen(["firefox", "-marionette", "-headless", "-no-remote", "-profile", profile, "about:blank"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        browser = marionette.Marionette(host="127.0.0.1", port=marionette_port, startup_timeout=30)
        browser.start_session()
        browser.set_window_rect(width=1500, height=1000)
        base = f"http://127.0.0.1:{port}"
        browser.navigate(base)
        wait_until(lambda: browser.execute_script('return document.querySelector("#comment-filter").options.length > 1'))
        yield browser, base
    finally:
        if browser is not None:
            try:
                browser.delete_session()
            except Exception:
                pass
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        shutil.rmtree(profile, ignore_errors=True)
        shared.stop()


def show_view(browser, view: str) -> None:
    browser.execute_script('const f = document.querySelector("#comment-filter"); f.value = arguments[0];'
                           ' f.dispatchEvent(new Event("change"));', script_args=[view])


def listed(browser) -> list[str]:
    return browser.execute_script(
        'return [...document.querySelectorAll("#comments-list .cmt")].map((card) => card.dataset.commentId)')


@needs_firefox
def test_the_search_finds_words_writers_files_and_days_in_every_status(tmp_path: Path) -> None:
    """The search box lists the comments that meet what is typed, whatever their status, while
    the view list reads all: words in the thread or in what a comment is on, from: the agent
    or the reviewer, file: the source file, after: and before: a day. Escape puts it away and
    the view comes back."""
    kept = CommentStore(store_of(tmp_path, "slides"))
    source = kept.add(SourceAnchor(file="slides/slides.html", quote="Tea is served.", prefix="", suffix="", line_start=1,
                                   line_end=1, column_start=0, column_end=5), "The bound is loose.")
    kept.reply(source.id, "Tightened the bound.", "agent")
    page = kept.add(PageAnchor(number=1, title="First"), "Please cite the survey.")
    whole = kept.add(ArtifactAnchor(), "Loose ends in the proof sketch.")
    kept.update_many([whole.id], "human", "", status="resolved")
    stamp(store_of(tmp_path, "slides"), {source.id: [local_moment(11, 10, 9), local_moment(11, 11)],
                                         page.id: [local_moment(11, 12, 9, 30)], whole.id: [local_moment(11, 14)]})
    names = {source.id: "source", page.id: "page", whole.id: "whole"}
    with review_page(tmp_path) as (browser, base):
        found = lambda: sorted(names[cid] for cid in listed(browser))
        wait_until(lambda: found() == ["page", "source"])
        # The conditions show under the box while it has the focus.
        browser.execute_script('document.querySelector("#comment-search").focus()')
        wait_until(lambda: browser.execute_script('return !document.querySelector("#search-terms").hidden'))
        for query, expected in [("loose", ["source", "whole"]), ("LOOSE tightened", ["source"]),
                                ("cite OR sketch", ["page", "whole"]), ('"proof sketch"', ["whole"]),
                                ("from:agent", ["source"]), ("-from:agent", ["page", "whole"]),
                                ("file:slides", ["source"]), ("first", ["page"]), ("after:11-12", ["page", "whole"]),
                                ("-from:agent before:11-12T09:31", ["page"])]:
            browser.execute_script('const box = document.querySelector("#comment-search"); box.value = arguments[0];'
                                   ' box.dispatchEvent(new Event("input"))', script_args=[query])
            wait_until(lambda: found() == expected
                       and browser.execute_script('return document.querySelector("#comment-filter").value') == "all")
        browser.execute_script('document.querySelector("#comment-search")'
                               '.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }))')
        wait_until(lambda: found() == ["page", "source"]
                   and browser.execute_script('return document.querySelector("#comment-filter").value') == "open")
        # A day on the cards is the browser's own, as the search reads it.
        browser.execute_script(f'document.querySelector(\'[data-comment-id="{page.id}"] .cmt-head\').click()')
        wait_until(lambda: browser.execute_script(
            f'return document.querySelector(\'[data-comment-id="{page.id}"] .thread-meta span\')?.textContent')
            == "human · 11-12 09:30")


@needs_firefox
def test_the_sort_list_orders_the_list_and_its_search_and_the_row_keeps_one_line(tmp_path: Path) -> None:
    """Beside the views, the sort list puts the list in page order, latest first or oldest
    first, by when each thread was last written in, in a view and in a search alike, and the
    browser keeps the order chosen across a reload. However narrow the panel, the row stays one
    line: the list shrinks to its icon before the word on Resolve goes, then waits behind the
    dots before Expand all does."""
    kept = CommentStore(store_of(tmp_path, "slides"))
    first = kept.add(ArtifactAnchor(), "First request, on the abstract.")
    kept.reply(first.id, "Still waiting on this request.", "human")
    second = kept.add(ArtifactAnchor(), "Second request, on the figures.")
    third = kept.add(ArtifactAnchor(), "Third request, on the tables.")
    # The first was written first and answered last, so the three orders all differ.
    stamp(store_of(tmp_path, "slides"), {first.id: [local_moment(11, 1), local_moment(11, 12)],
                                         second.id: [local_moment(11, 5)], third.id: [local_moment(11, 8)]})
    ids = {first.id: "first", second.id: "second", third.id: "third"}
    with review_page(tmp_path) as (browser, base):
        script = lambda code, *args: browser.execute_script(code, script_args=list(args))
        order = lambda: [ids[cid] for cid in listed(browser)]
        sorted_by = lambda value: script('const s = document.querySelector("#comment-sort"); s.value = arguments[0];'
                                         ' s.dispatchEvent(new Event("change"));', value)
        shown_sort = lambda: script('return [document.querySelector("#comment-sort").value,'
                                    ' document.querySelector("#comment-sort-name").textContent]')
        wait_until(lambda: order() == ["first", "second", "third"])
        assert shown_sort() == ["page", "page order"]
        sorted_by("latest")
        wait_until(lambda: order() == ["first", "third", "second"])
        sorted_by("oldest")
        wait_until(lambda: order() == ["second", "third", "first"])
        script('const box = document.querySelector("#comment-search"); box.value = "request";'
               ' box.dispatchEvent(new Event("input"))')
        wait_until(lambda: order() == ["second", "third", "first"]
                   and script('return document.querySelector("#comment-filter").value') == "all")
        sorted_by("latest")
        wait_until(lambda: order() == ["first", "third", "second"])
        sorted_by("page")
        wait_until(lambda: order() == ["first", "second", "third"])
        assert script('return document.querySelector("#comment-search").value') == "request"
        # No key works the list on this page, so the titles name none.
        assert script('return [document.querySelector("#comment-sort").title, document.querySelector("#comment-search").title]') \
            == ["Sort by page order", "Search the comments of this tab"]
        sorted_by("oldest")
        browser.refresh()
        wait_until(lambda: shown_sort() == ["oldest", "oldest first"] and order() == ["second", "third", "first"])
        steps = script('''return (async () => {
          const layout = document.querySelector(".layout");
          const row = document.querySelector(".filter-row");
          const sort = document.querySelector("#comment-sort-pick");
          const frame = () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
          const seen = [];
          for (let width = 700; width >= 240; width -= 5) {
            layout.style.gridTemplateColumns = `minmax(0, 1fr) ${width}px`;
            await frame();
            const icon = sort.querySelector(".sort-icon").getBoundingClientRect();
            const list = sort.querySelector("select").getBoundingClientRect();
            seen.push({
              width, line: row.scrollWidth <= row.clientWidth && row.getBoundingClientRect().height < 40,
              sort: sort.closest(".comment-rare-group") ? "behind" : icon.width > 0 ? "icon" : "words",
              over: icon.width > 0 && Math.abs(icon.left - list.left) < 1 && Math.abs(icon.right - list.right) < 1
                && getComputedStyle(sort.querySelector("select")).opacity === "0",
              fold: document.querySelector("#fold-all-btn").closest(".comment-rare-group") !== null,
              words: getComputedStyle(document.querySelector("#resolve-picked-btn .wide-label")).display !== "none",
            });
          }
          return seen;
        })();''')
        assert all(step["line"] for step in steps), steps
        states = [step["sort"] for step in steps]
        assert states[0] == "words" and states[-1] == "behind" and "icon" in states, states
        assert states == sorted(states, key=["words", "icon", "behind"].index), states
        assert all(step["over"] for step in steps if step["sort"] == "icon"), steps
        words = [step["words"] for step in steps]
        assert words == sorted(words, reverse=True), steps
        assert any(step["sort"] == "icon" and step["words"] for step in steps), steps
        assert all(not step["words"] for step in steps if step["sort"] == "behind"), steps
        assert all(step["sort"] == "behind" for step in steps if step["fold"]) and steps[-1]["fold"], steps
        # Behind the dots it is the list with its words, and an order chosen there closes them.
        browser.find_element("css selector", "#comment-rare-btn").click()
        assert script('return document.querySelector("#comment-sort").getBoundingClientRect().width > 60')
        sorted_by("latest")
        wait_until(lambda: order() == ["first", "third", "second"])
        assert script('return document.querySelector("#comment-rare").classList.contains("open")') is False


@needs_firefox
def test_the_row_stays_one_line_at_every_text_size_with_the_bell_in_it(tmp_path: Path) -> None:
    """At every text size, from a 700px panel down to 240px, a comment picked or not, the row
    above the list stays one line, the bell among its buttons until it waits behind the dots,
    where it still calls the agent."""
    kept = CommentStore(store_of(tmp_path, "slides"))
    kept.add(ArtifactAnchor(), "Tighten the opening.")
    with review_page(tmp_path) as (browser, base):
        script = lambda code: browser.execute_script(code)
        wait_until(lambda: len(listed(browser)) == 1)
        row = '''const row = document.querySelector(".filter-row");
          return row.scrollWidth <= row.clientWidth && !row.classList.contains("wrapped")
            && row.getBoundingClientRect().height < 2 * document.querySelector("#resolve-picked-btn").getBoundingClientRect().height;'''
        for picked in (False, True):
            if picked:
                script('document.querySelector("#pick-all-btn").click()')
                wait_until(lambda: script('return document.querySelector("#resolve-picked-btn .count").textContent') == "1")
            for size in script(TEXT_SIZES):
                script(f'document.querySelector(\'[data-text-choice="{size}"]\').click()')
                for width in range(700, 239, -20):
                    script(f'document.querySelector(".layout").style.gridTemplateColumns = "minmax(0, 1fr) {width}px"')
                    script(FITTED)
                    assert script(row), (picked, size, width)
        # At the largest text in the narrowest panel the bell waits behind the dots, named, and
        # a press there calls.
        assert script('return document.querySelector(".comment-rare-group #call-agent-btn") !== null')
        browser.find_element("css selector", "#comment-rare-btn").click()
        assert script('return document.querySelector("#call-agent-btn").getAttribute("aria-label")') == "Queue call for agent"
        browser.find_element("css selector", "#call-agent-btn").click()
        wait_until(lambda: get_json(f"{base}/state")["review"]["calls"] == 1)


@needs_firefox
def test_undo_puts_the_last_change_of_status_back(tmp_path: Path) -> None:
    """A change of status made from the row or on a card is said in a line above the list with
    Undo, which puts each comment back to the status it had, a resolved one with the moment it
    was resolved at. Only the last change is undone: the next takes the line's place, views and
    tabs leave it be, and the close button or a reload takes it away. The Comments tab counts
    the comments the agent answered last."""
    kept = CommentStore(store_of(tmp_path, "slides"))
    first, second, third, done, archived = (kept.add(ArtifactAnchor(), text).id
                                            for text in ("One.", "Two.", "Three.", "Done.", "Kept."))
    kept.update_many([done], "human", "", status="resolved")
    kept.update_many([archived], "human", "", status="reference")
    with review_page(tmp_path) as (browser, base):
        comments = f"{base}/artifacts/slides/comments"
        resolved_at = get_json(f"{comments}/{done}")["resolved"]
        statuses = lambda *ids: [get_json(f"{comments}/{cid}")["status"] for cid in ids]
        script = lambda code: browser.execute_script(code)
        click = lambda selector: browser.execute_script("document.querySelector(arguments[0]).click()",
                                                        script_args=[selector])
        line = lambda: script('return document.querySelector("#undo-line").offsetHeight > 0'
                              ' ? document.querySelector("#undo-text").textContent : null')
        shown = lambda: sorted(listed(browser))
        pick = lambda cid: click(f"[data-comment-id='{cid}'] .comment-pick")
        count = lambda: script('const count = document.querySelector("#comments-tab-count");'
                               ' return count.classList.contains("hidden") ? null : count.textContent')
        wait_until(lambda: shown() == sorted([first, second, third]))
        assert line() is None and count() is None
        assert script('return document.querySelector("#undo-btn").title') == "Undo the last status change"
        # Answered by the agent, a comment waits for the reviewer and the tab counts it; the
        # reviewer's reply answers it.
        post_json(f"{comments}/{third}/reply", {"text": "Done as asked.", "author": "agent"})
        wait_until(lambda: count() == "1")
        assert script(f'return document.querySelector(\'[data-comment-id="{third}"] .cmt-unanswered\') !== null')
        post_json(f"{comments}/{third}/reply", {"text": "Thanks."})
        wait_until(lambda: count() is None)
        # Three resolved from the row, and Undo opens each again.
        click("#pick-all-btn")
        click("#resolve-picked-btn")
        wait_until(lambda: line() == "Resolved 3 comments.")
        assert statuses(first, second, third) == ["resolved"] * 3
        click("#undo-btn")
        wait_until(lambda: statuses(first, second, third) == ["open"] * 3 and line() is None)
        # Resolved again, the line stays in another view. A reopen of one resolved and one
        # archived takes its place, stays through a tab change, and Undo puts each back.
        wait_until(lambda: shown() == sorted([first, second, third]))
        click("#pick-all-btn")
        click("#resolve-picked-btn")
        wait_until(lambda: line() == "Resolved 3 comments.")
        show_view(browser, "all")
        wait_until(lambda: shown() == sorted([first, second, third, done, archived]))
        assert line() == "Resolved 3 comments."
        pick(done)
        pick(archived)
        assert script('return document.querySelector("#resolve-picked-btn").getAttribute("aria-label")') == "Reopen 2"
        click("#resolve-picked-btn")
        wait_until(lambda: line() == "Reopened 2 comments.")
        assert statuses(done, archived) == ["open", "open"]
        click('.tab-btn[data-tab="pages"]')
        click('.tab-btn[data-tab="comments"]')
        assert line() == "Reopened 2 comments."
        click("#undo-btn")
        wait_until(lambda: statuses(done, archived) == ["resolved", "reference"] and line() is None)
        assert statuses(first, second, third) == ["resolved"] * 3
        assert get_json(f"{comments}/{done}")["resolved"] == resolved_at
        # A comment deleted after the change cannot be put back: Undo restores the other and
        # says how many no longer exist, with nothing left to undo.
        pick(done)
        pick(archived)
        click("#resolve-picked-btn")
        wait_until(lambda: line() == "Reopened 2 comments.")
        urllib.request.urlopen(urllib.request.Request(f"{comments}/{archived}", method="DELETE"), timeout=5).close()
        click("#undo-btn")
        wait_until(lambda: statuses(done) == ["resolved"]
                   and line() == "1 comment could not be restored because it no longer exists.")
        assert get_json(f"{comments}/{done}")["resolved"] == resolved_at
        assert script('return document.querySelector("#undo-btn").hidden') is True
        click("#undo-close")
        # The close button takes the line away and changes nothing.
        pick(first)
        click("#resolve-picked-btn")
        wait_until(lambda: line() == "Reopened 1 comment.")
        click("#undo-close")
        assert line() is None and statuses(first) == ["open"]
        # A card's Archive is said too, and a reload takes the line away.
        click(f"[data-comment-id='{second}'] .cmt-head")
        wait_until(lambda: script(f'return document.querySelector("[data-comment-id=\'{second}\'] .cmt-archive") !== null'))
        click(f"[data-comment-id='{second}'] .cmt-archive")
        wait_until(lambda: line() == "Archived 1 comment.")
        browser.refresh()
        wait_until(lambda: browser.execute_script('return document.querySelector("#comment-filter").options.length > 1'))
        show_view(browser, "all")
        wait_until(lambda: len(shown()) == 4)
        assert line() is None and statuses(second) == ["reference"]


@needs_firefox
def test_a_change_made_on_one_artifact_is_never_undone_on_another(tmp_path: Path) -> None:
    """Each artifact has its comments. A tab chosen, or the first artifact shown in place of one
    the configuration no longer names, lets go of what the panel held for the one before: the
    comments picked, a reply being written and the change Undo would put back, so an Undo
    pressed then posts nothing. A change, or an Undo, still on its way when the tab changes
    stops when it comes back, and offers nothing to undo on the other."""
    slides = CommentStore(store_of(tmp_path, "slides"))
    one, two, three = (slides.add(ArtifactAnchor(), text).id for text in ("One.", "Two.", "Three."))
    other = CommentStore(store_of(tmp_path, "report")).add(ArtifactAnchor(), "On the report.").id
    with review_page(tmp_path, aliases=("slides", "report")) as (browser, base):
        status = lambda alias, cid: get_json(f"{base}/artifacts/{alias}/comments/{cid}")["status"]
        script = lambda code: browser.execute_script(code, sandbox=None)
        click = lambda selector: browser.execute_script("document.querySelector(arguments[0]).click()",
                                                        script_args=[selector])
        line = lambda: script('return document.querySelector("#undo-line").offsetHeight > 0'
                              ' ? document.querySelector("#undo-text").textContent : null')
        artifact = lambda alias: click(f'.artifact-tab:nth-child({1 if alias == "slides" else 2})')
        statuses_posted = lambda: [call for call in script("return window.calls") if call.endswith("/comments/status")]
        wait_until(lambda: sorted(listed(browser)) == sorted([one, two, three]))
        script(WATCH_CALLS)
        # A change made, and the tab changed: the line goes, nothing stays picked or open, and an
        # Undo pressed then posts nothing.
        click(f"[data-comment-id='{one}'] .comment-pick")
        click("#resolve-picked-btn")
        wait_until(lambda: line() == "Resolved 1 comment.")
        click(f"[data-comment-id='{two}'] .comment-pick")
        click(f"[data-comment-id='{two}'] .cmt-head")
        click(f"[data-comment-id='{two}'] .cmt-reply")
        wait_until(lambda: script('return document.querySelector(".cmt-form-input") !== null'))
        artifact("report")
        wait_until(lambda: listed(browser) == [other] and line() is None)
        assert script('return [document.querySelector(".cmt-form-input"), document.querySelector("#resolve-picked-btn").disabled]') \
            == [None, True]
        before = len(statuses_posted())
        click("#undo-btn")
        time.sleep(0.5)
        assert len(statuses_posted()) == before
        assert status("slides", one) == "resolved" and status("report", other) == "open"
        # A change on its way when the tab changes is made where it was asked, and the other
        # artifact is offered no Undo of it.
        artifact("slides")
        wait_until(lambda: sorted(listed(browser)) == sorted([two, three]))
        script('window.hold = (call) => call === "POST /artifacts/slides/comments/status";')
        click(f"[data-comment-id='{two}'] .comment-pick")
        click("#resolve-picked-btn")
        wait_until(lambda: script("return window.held.length") == 1)
        artifact("report")
        wait_until(lambda: listed(browser) == [other])
        script("window.release()")
        wait_until(lambda: status("slides", two) == "resolved")
        time.sleep(0.5)
        assert line() is None and listed(browser) == [other]
        # An Undo on its way when the tab changes stops there: it posts nothing to either.
        artifact("slides")
        wait_until(lambda: listed(browser) == [three])
        click(f"[data-comment-id='{three}'] .comment-pick")
        click("#resolve-picked-btn")
        wait_until(lambda: line() == "Resolved 1 comment.")
        time.sleep(0.5)
        script('window.hold = (call) => call === "GET /artifacts/slides/comments";')
        before = len(statuses_posted())
        click("#undo-btn")
        wait_until(lambda: script("return window.held.length") == 1)
        artifact("report")
        wait_until(lambda: listed(browser) == [other])
        script("window.release()")
        time.sleep(0.8)
        assert len(statuses_posted()) == before
        assert status("slides", three) == "resolved" and status("report", other) == "open"
        assert line() is None
        # The artifact shown leaves the configuration with a change of it still to undo: the
        # page shows the first artifact's comments, with nothing to undo.
        four = post_json(f"{base}/artifacts/slides/comments", {"anchor": {"kind": "artifact"}, "text": "Four."})["id"]
        click(f"[data-comment-id='{other}'] .comment-pick")
        click("#resolve-picked-btn")
        wait_until(lambda: line() == "Resolved 1 comment.")
        config = tmp_path / ".html-mcp-web.yaml"
        settings = yaml.safe_load(config.read_text(encoding="utf-8"))
        del settings["artifacts"]["report"]
        config.write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
        wait_until(lambda: script('return document.querySelectorAll(".artifact-tab").length') == 1
                   and listed(browser) == [four] and line() is None)
        before = len(statuses_posted())
        click("#undo-btn")
        time.sleep(0.5)
        assert len(statuses_posted()) == before and status("slides", four) == "open"


@needs_firefox
def test_a_refused_suggestion_says_the_servers_words(tmp_path: Path) -> None:
    """The server refuses a change made to a thread that changed since the card was drawn, in
    words sent as JSON, and a suggestion the file no longer fits, in words sent as text. Either
    way the reviewer reads the server's words: the first in an alert, the second on the card,
    under the suggestion."""
    kept = CommentStore(store_of(tmp_path, "slides"))
    comment = kept.add(ArtifactAnchor(), "Tea is a weak verb.")
    kept.suggest(comment.id, comment.updated, "Poured reads better.",
                 SuggestedEdit(file="slides/slides.html", changes=[("Tea is served.", "Tea is poured.")]))
    with review_page(tmp_path) as (browser, base):
        script = lambda code: browser.execute_script(code, sandbox=None)
        card = f'[data-comment-id="{comment.id}"]'
        wait_until(lambda: listed(browser) == [comment.id])
        script('window.alerts = []; window.alert = (message) => window.alerts.push(message);')
        script(f'document.querySelector(\'{card} .cmt-head\').click()')
        wait_until(lambda: script(f'return document.querySelector(\'{card} .sugg-reject\') !== null'))
        # The thread changes behind the card's back, so the card's stamp is stale.
        data = json.loads(store_of(tmp_path, "slides").read_text(encoding="utf-8"))
        data["comments"][0]["updated"] = local_moment(11, 30)
        store_of(tmp_path, "slides").write_text(json.dumps(data), encoding="utf-8")
        script(f'document.querySelector(\'{card} .sugg-reject\').click()')
        wait_until(lambda: script("return window.alerts") == ["Action failed: stale thread: comment changed since it was read"])
        # Drawn again with the thread as it is, the card's suggestion no longer fits the file.
        show_view(browser, "all")
        show_view(browser, "open")
        (tmp_path / "slides" / "slides.html").write_text(DECK.replace("Tea is served.", "Tea is brewed."), encoding="utf-8")
        wait_until(lambda: script(f'return document.querySelector(\'{card} .sugg-apply\') !== null'))
        request = urllib.request.Request(f"{base}/artifacts/slides/comments/{comment.id}/apply-suggestion",
                                         data=json.dumps({"updated": local_moment(11, 30)}).encode("utf-8"),
                                         headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(request, timeout=3)
        assert refused.value.code == 409
        why = refused.value.read().decode("utf-8")
        script(f'document.querySelector(\'{card} .sugg-apply\').click()')
        wait_until(lambda: script(f'return document.querySelector(\'{card} .sugg-unfit\')?.textContent')
                   == "The file has changed since this was suggested, so it no longer applies. "
                      f"Reject it, or reply to ask the agent for a new one. ({why})")
