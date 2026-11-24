"""The comment panel the review pages share, as this page uses it, in Firefox: its search, its
orders, the line that undoes a change of status, the row above the list, how each artifact
keeps its own comments, the keys that work the list beside the slides' own, Help, and the
Settings for the key letters and the editor's cursor."""

import json
import os
import shutil
import socket
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from marionette_driver.marionette import ActionSequence

from html_mcp_web.comments import ArtifactAnchor, CommentStore, PageAnchor, SourceAnchor, SuggestedEdit
from html_mcp_web.config import load_config
from html_mcp_web.firefox import stop
from html_mcp_web.project_server import SharedProjectServer
from tests.firefox import Browser, launch, needs_firefox

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


SERVERS: dict[str, SharedProjectServer] = {}


@contextmanager
def review_page(root: Path, aliases=("slides",), deck=DECK, prefs="", height=1000):
    """The review page of a project of one deck per alias, each in a folder of its own, opened in
    a headless Firefox 1500 wide and 1000 high unless told, with its server's address. `prefs`
    are Firefox's own settings, as user.js lines. SERVERS names the server by its address while
    the page is open."""
    for alias in aliases:
        (root / alias).mkdir()
        (root / alias / "slides.html").write_text(deck, encoding="utf-8")
    port = available_port()
    config_path = root / ".html-mcp-web.yaml"
    config_path.write_text(yaml.safe_dump({
        "artifacts": {alias: {"layout": "slides", "main": f"{alias}/slides.html"} for alias in aliases},
        "watch": ["*.html"], "port": port}, sort_keys=False), encoding="utf-8")
    shared = SharedProjectServer(load_config(config_path))
    profile = tempfile.mkdtemp(prefix="html_mcp_panel_")
    marionette_port = available_port()
    (Path(profile) / "user.js").write_text(f'user_pref("marionette.port", {marionette_port});\n{prefs}', encoding="utf-8")
    process = None
    browser = None
    try:
        shared.ensure()
        SERVERS[f"http://127.0.0.1:{port}"] = shared
        process = launch(profile)
        browser = Browser(host="127.0.0.1", port=marionette_port, startup_timeout=30)
        browser.start_session()
        browser.set_window_rect(width=1500, height=height)
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
            stop(process)
        shutil.rmtree(profile, ignore_errors=True)
        SERVERS.pop(f"http://127.0.0.1:{port}", None)
        shared.stop()


def show_view(browser, view: str) -> None:
    browser.execute_script('const f = document.querySelector("#comment-filter"); f.value = arguments[0];'
                           ' f.dispatchEvent(new Event("change"));', script_args=[view])


def listed(browser) -> list[str]:
    return browser.execute_script(
        'return [...document.querySelectorAll("#comments-list .cmt")].map((card) => card.dataset.commentId)')


ESCAPE, HOME, END, DOWN, CONTROL, ALT, SHIFT = "\ue00c", "\ue011", "\ue010", "\ue015", "\ue009", "\ue00a", "\ue008"


def press(browser, *keys) -> None:
    """Keys pressed one after the other, as a hand presses them, wherever the focus is."""
    actions = ActionSequence(browser, "key", "keyboard")
    for key in keys:
        actions.key_down(key).key_up(key).pause(15)
    actions.perform()


def chord(browser, *keys) -> None:
    """Keys held down together, as Ctrl+Alt+K."""
    actions = ActionSequence(browser, "key", "keyboard")
    for key in keys:
        actions.key_down(key)
    for key in reversed(keys):
        actions.key_up(key)
    actions.perform()


def ringed(browser):
    return browser.execute_script('return document.querySelector("#comments-list .cmt.is-focused")?.dataset.commentId ?? null')


def opened(browser) -> list[str]:
    return browser.execute_script('return [...document.querySelectorAll("#comments-list .cmt")]'
                                  '.filter((card) => card.querySelector(".cmt-actions")).map((card) => card.dataset.commentId)')


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
        # The titles name the keys that work them.
        assert script('return [document.querySelector("#comment-sort").title, document.querySelector("#comment-search").title]') \
            == ["Sort by page order (o)", "Search the comments of this tab (/)"]
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
def test_the_line_above_the_list_says_how_comments_reach_the_agent(tmp_path: Path) -> None:
    """After a comment is posted while comments wait for the agent, the line above the list says
    they reach it at the bell, with its key, until the bell is pressed. A press no agent hears is
    queued, which the line says until an agent listens and takes it, and the reminder is not
    said again in this visit. The server names no agents beside the session listening, so the
    bell has no lists of them, and with one way to call no button for the way."""
    with review_page(tmp_path) as (browser, base):
        script = lambda code: browser.execute_script(code)
        note = 'const note = document.querySelector("#call-agent-why"); return note.hidden ? null : note.textContent'
        assert script(note) is None
        assert script('''return ["#call-agent-select", "#agent-model-select", "#agent-effort-select"]
          .every((id) => document.querySelector(id).classList.contains("hidden"))
          && document.querySelector("#call-by-btn") === null''')
        script('document.querySelector("#artifact-comment-btn").click()')
        wait_until(lambda: script('return document.querySelector("#compose-dialog").open'))
        script('const box = document.querySelector("#compose-text"); box.value = "Tighten the opening.";'
               ' box.dispatchEvent(new Event("input", {bubbles: true})); document.querySelector("#compose-form").requestSubmit();')
        reminder = "Your comments reach the agent when you press the bell (Ctrl+Alt+Enter)."
        wait_until(lambda: script(note) == reminder)
        # Ctrl+Alt+Enter presses the bell, and no agent listens.
        script('document.body.dispatchEvent(new KeyboardEvent("keydown", {key: "Enter", ctrlKey: true, altKey: true, bubbles: true}))')
        wait_until(lambda: script('return document.querySelector("#call-agent-word").textContent') == "Queued")
        assert script(note) == "No agent is listening yet, so the call is queued until one listens."
        with urllib.request.urlopen(f"{base}/wait-review?listener=one&pid={os.getpid()}", timeout=10) as waited:
            assert waited.read().startswith(b"[review]")
        wait_until(lambda: script(note) is None)
        script('document.querySelector("#artifact-comment-btn").click()')
        wait_until(lambda: script('return document.querySelector("#compose-dialog").open'))
        script('const box = document.querySelector("#compose-text"); box.value = "And the closing.";'
               ' box.dispatchEvent(new Event("input", {bubbles: true})); document.querySelector("#compose-form").requestSubmit();')
        wait_until(lambda: len(listed(browser)) == 2)
        time.sleep(0.3)
        assert script(note) is None


@needs_firefox
def test_the_bell_calls_an_agent_the_configuration_names(tmp_path: Path) -> None:
    """With agents in the configuration, the reviewer picks beside the bell which agent it
    calls, with the effort that agent lists. Naming them while the page is open brings the
    choice. The bell is green for the agent picked while that agent waits, and the press
    reaches its waiter alone."""
    from concurrent.futures import ThreadPoolExecutor

    with review_page(tmp_path) as (browser, base):
        script = lambda code, *args: browser.execute_script(code, script_args=list(args))
        shown = lambda: script('''return ["#call-agent-select", "#agent-effort-select"].map((id) => {
            const box = document.querySelector(id);
            return box.classList.contains("hidden") ? null
              : [...box.options].map((option) => option.textContent).join() + "=" + box.value;
          });''')
        assert shown() == [None, None]
        config_path = tmp_path / ".html-mcp-web.yaml"
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        data["agents"] = {"second": {"efforts": ["low", "high"]}}
        config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        wait_until(lambda: shown() == ["Agent,Second=", None])
        pick = lambda box, value: script('const box = document.querySelector(arguments[0]); box.value = arguments[1];'
                                         ' box.dispatchEvent(new Event("change", {bubbles: true}));', box, value)
        pick("#call-agent-select", "second")
        assert shown() == ["Agent,Second=second", "low,high=low"]
        pick("#agent-effort-select", "high")
        ready = lambda: script('return document.querySelector("#call-agent-btn").classList.contains("agent-ready")')
        assert not ready()
        with ThreadPoolExecutor(max_workers=1) as pool:
            waiter = pool.submit(lambda: urllib.request.urlopen(
                f"{base}/wait-review?agent=second&listener=-&pid={os.getpid()}", timeout=20).read())
            wait_until(ready)
            script('document.querySelector("#call-agent-btn").click()')
            assert waiter.result(timeout=20).endswith(b"[effort=high]")
        assert SERVERS[base].runner.app["review_server"].review.calls == 0


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
    kept.update_many([archived], "human", "", status="archived")
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
        assert script('return document.querySelector("#undo-btn").title') == "Undo the last status change (u)"
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
        wait_until(lambda: statuses(done, archived) == ["resolved", "archived"] and line() is None)
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
        assert line() is None and statuses(second) == ["archived"]


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
    """The server refuses a change made to a thread that changed since the card was drawn, and a
    suggestion the file no longer fits, each in words sent as JSON. The reviewer reads the
    server's words: the first in an alert, the second on the card, under the suggestion."""
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
        why = json.loads(refused.value.read().decode("utf-8"))["error"]
        script(f'document.querySelector(\'{card} .sugg-apply\').click()')
        wait_until(lambda: script(f'return document.querySelector(\'{card} .sugg-unfit\')?.textContent')
                   == "The file has changed since this was suggested, so it no longer applies. "
                      f"Reject it, or reply to ask the agent for a new one. ({why})")


@needs_firefox
def test_the_comment_list_goes_by_keys(tmp_path: Path) -> None:
    """The comments go by keys as tex-mcp-web's do, as a notebook's cells do: j and k move the
    ring and leave every card as it was, a key presses the ringed card's button and shows its
    letter there, a key that changes the file or deletes is pressed twice, v holds a range, K
    goes between a comment and its words in the source, and the keys rest while another tab or
    a dialog is shown."""
    kept = CommentStore(store_of(tmp_path, "slides"))
    first = kept.add(ArtifactAnchor(), "Name the second example.").id
    at = DECK.index("Tea is served.")
    source = kept.add(SourceAnchor(file="slides/slides.html", quote="Tea is served.", prefix="", suffix="", line_start=1,
                                   line_end=1, column_start=at, column_end=at + 14), "Say who is served.")
    kept.suggest(source.id, source.updated, "Poured reads better.",
                 SuggestedEdit(file="slides/slides.html", changes=[("Tea is served.", "Tea is poured.")]))
    source = source.id
    third = kept.add(PageAnchor(number=1, title="First"), "Shorten the title.").id
    fourth = kept.add(ArtifactAnchor(), "Cite the survey here.").id
    with review_page(tmp_path) as (browser, base):
        script = lambda code, *args: browser.execute_script(code, script_args=list(args), sandbox=None)
        keys = lambda *pressed: press(browser, *pressed)
        ring = lambda: ringed(browser)
        status = lambda cid: get_json(f"{base}/artifacts/slides/comments/{cid}")["status"]
        editor = 'const editor = (window.wrappedJSObject || window).ace.edit("source-editor");'
        wait_until(lambda: listed(browser) == [first, source, third, fourth])
        script("document.activeElement.blur()")
        # The ring moves and opens no card.
        keys("j")
        assert [ring(), opened(browser)] == [first, []]
        keys("j")
        assert ring() == source
        keys("k")
        assert ring() == first
        keys("G")
        assert ring() == fourth
        keys("g", "g")
        assert ring() == first
        keys(END)
        assert ring() == fourth
        keys(HOME)
        assert ring() == first
        # With a Korean input method on, a letter key arrives as the letter it composes, and is
        # read by where it sits on the keyboard.
        script('document.body.dispatchEvent(new KeyboardEvent("keydown", {key: "ㅓ", code: "KeyJ", bubbles: true, cancelable: true}))')
        assert ring() == source
        # Space opens the ringed card, which shows its words selected in the source while the
        # keys stay with the list, and stays open as the ring moves on.
        keys(" ")
        assert opened(browser) == [source]
        wait_until(lambda: script(f'{editor} return editor.getSelectedText()') == "Tea is served.")
        assert script('return document.querySelector(".layout").classList.contains("view-source")')
        assert script('return document.activeElement.id') == "comments-list"
        assert script(f'{editor} return editor.isFocused()') is False
        keys("j")
        assert [ring(), opened(browser)] == [third, [source]]
        keys("k", " ")
        assert opened(browser) == []
        keys(" ")
        assert [ring(), opened(browser)] == [source, [source]]
        assert script('return document.querySelector("#comments-list .is-focused .cmt-resolve").title') == "Resolve (R)"
        # Moving by keys puts each key's letter on the ringed comment's controls, a touch of the
        # mouse takes the letters away, and Settings can turn them off.
        letters = ('return [document.querySelector("#comments-list").classList.contains("show-keys"),'
                   ' [...document.querySelectorAll("#comments-list [data-key]")].map((node) => node.dataset.key)]')
        shown, marked = script(letters)
        assert shown is True and sorted(marked) == sorted(["x", "e", "D", "aa", "nn", "r", "R", "A", "dd"])
        ActionSequence(browser, "pointer", "mouse", {"pointerType": "mouse"}).pointer_move(300, 300) \
            .pointer_move(340, 340).perform()
        assert script(letters)[0] is False
        script('document.querySelector(\'[data-letters-choice="off"]\').click()')
        keys("j", "k")
        assert script(letters)[0] is False
        script('document.querySelector(\'[data-letters-choice="on"]\').click()')
        keys("j", "k")
        assert script(letters)[0] is True
        assert ring() == source
        # K takes the keys into the source at the ringed comment's words, and Ctrl+Alt+K there
        # brings them back to the comment.
        keys("K")
        wait_until(lambda: script(f'{editor} return editor.isFocused()'))
        assert script(f'{editor} return editor.getSelectedText()') == "Tea is served."
        chord(browser, CONTROL, ALT, "k")
        wait_until(lambda: script('return document.activeElement.id') == "comments-list")
        assert ring() == source
        # Ctrl+Alt+K goes from the list as K does, and back.
        chord(browser, CONTROL, ALT, "k")
        wait_until(lambda: script(f'{editor} return editor.isFocused()'))
        chord(browser, CONTROL, ALT, "k")
        wait_until(lambda: script('return document.activeElement.id') == "comments-list")
        # A comment on a page has its words there, not in the source: K shows its place and
        # the keys stay with the list.
        keys("j", "K")
        assert ring() == third
        assert script('return document.activeElement.id') == "comments-list"
        assert script(f'{editor} return editor.isFocused()') is False
        keys("k")
        # Ctrl+Alt+K takes the keys back to the list with the comments hidden too, which it
        # shows.
        script(f"{editor} editor.focus();")
        script('document.querySelector("#sidebar-toggle-btn").click()')
        assert script('return document.querySelector(".layout").classList.contains("sidebar-collapsed")') is True
        chord(browser, CONTROL, ALT, "k")
        wait_until(lambda: script('return document.activeElement.id') == "comments-list")
        assert script('return document.querySelector(".layout").classList.contains("sidebar-collapsed")') is False
        assert ring() == source
        # r and e put the cursor in the reply and in the last thing written, and Escape drops
        # either, the keys going on.
        keys("r")
        assert script('return document.activeElement.matches("#comments-list .is-focused .cmt-form-input")') is True
        keys(ESCAPE)
        assert script('return document.querySelector("#comments-list .cmt-form")') is None
        keys("e")
        assert script('return document.activeElement.matches("#comments-list .is-focused .entry-edit-input")') is True
        keys(ESCAPE)
        assert script('return document.querySelector("#comments-list .cmt-form")') is None
        # A suggestion is applied by a doubled a: one a, or two a second apart, does nothing.
        keys("a")
        time.sleep(1.3)
        keys("a")
        time.sleep(0.5)
        assert "suggestion" in get_json(f"{base}/artifacts/slides/comments/{source}")
        keys("a", "a")
        wait_until(lambda: "suggestion" not in get_json(f"{base}/artifacts/slides/comments/{source}"))
        assert (tmp_path / "slides" / "slides.html").read_text(encoding="utf-8").count("Tea is poured.") == 1
        assert script(f'{editor} return editor.isFocused()') is False

        # x picks the ringed comment. v holds a range that the moving keys stretch, and x picks
        # the range, or lets it go when it is all picked. Escape lets a range go and changes
        # nothing, and * picks all or lets all go.
        def picked():
            return script('return [...document.querySelectorAll("#comments-list .cmt")]'
                          '.filter((card) => card.querySelector(".comment-pick").checked).map((card) => card.dataset.commentId)')

        def ranged():
            return script('return [...document.querySelectorAll("#comments-list .cmt.in-range")].map((card) => card.dataset.commentId)')

        keys("x")
        assert picked() == [source]
        keys("v", "j", "j")
        assert ranged() == [source, third, fourth]
        keys("x")
        assert [picked(), ranged()] == [[source, third, fourth], []]
        keys("v", "k", "x")
        assert picked() == [source]
        keys("v", "k", ESCAPE)
        assert [picked(), ranged(), ring()] == [[source], [], source]
        keys("*")
        assert picked() == [first, source, third, fourth]
        keys("*")
        assert picked() == []
        # R resolves the ringed comment, and the one now in its place takes the ring. Held
        # down, R does no more.
        keys("j", "R")
        wait_until(lambda: status(third) == "resolved" and ring() == fourth)
        script('document.body.dispatchEvent(new KeyboardEvent("keydown", {key: "R", repeat: true, bubbles: true, cancelable: true}))')
        time.sleep(0.5)
        assert status(fourth) == "open"
        # f moves to the next view, unanswered, archived and then resolved, where R reopens a
        # resolved comment, and F moves back.
        keys("f", "f", "f")
        wait_until(lambda: script('return document.querySelector("#comment-filter").value') == "resolved"
                   and listed(browser) == [third])
        keys("j", "R")
        wait_until(lambda: status(third) == "open")
        keys("F", "F", "F")
        wait_until(lambda: script('return document.querySelector("#comment-filter").value') == "open"
                   and len(listed(browser)) == 4)
        # With comments picked, R resolves them rather than the ringed one. Over a range, R acts
        # on the range at once, and a comment picked outside it stays picked.
        keys("g", "g", "x", "j", "R")
        wait_until(lambda: status(first) == "resolved")
        assert status(source) == "open"
        wait_until(lambda: picked() == [])
        keys("G", "x")
        keys("g", "g", "v", "j", "R")
        wait_until(lambda: status(source) == "resolved" and status(third) == "resolved")
        assert status(fourth) == "open"
        wait_until(lambda: picked() == [fourth] and ring() == fourth)
        keys("x")
        assert picked() == []
        # With no comment ringed in a view, v holds the range from the first. A archives.
        keys("f", "f", "f")
        wait_until(lambda: len(listed(browser)) == 3)
        assert ring() is None
        keys("v", "G", "R")
        wait_until(lambda: [status(cid) for cid in (first, source, third)] == ["open"] * 3)
        keys("F", "F", "F")
        wait_until(lambda: script('return document.querySelector("#comment-filter").value') == "open"
                   and len(listed(browser)) == 4)
        keys("G", "A")
        wait_until(lambda: status(fourth) == "archived")
        # dd deletes once the reader says yes, and a d not doubled is dropped.
        script("window.asked = []; window.confirm = (message) => window.asked.push(message) && false;")
        keys("g", "g")
        keys("d", "j")
        assert ring() == source
        keys("d", "d")
        assert script("return window.asked") == [f"Permanently delete {source}?"]
        # The list's keys rest while another tab is shown, and t and T move between tabs.
        keys("t")
        assert script('return document.querySelector(".tab-btn.active").dataset.tab') == "problems"
        keys("j")
        assert ring() == source
        keys("T", "T")
        assert script('return document.querySelector(".tab-btn.active").dataset.tab') == "pages"
        keys("t")
        assert script('return document.querySelector(".tab-btn.active").dataset.tab') == "comments"
        # ? lists the keys from the keys themselves, which rest under it until it closes.
        keys("?")
        assert script('return document.querySelector("#help-dialog").open') is True
        listed_keys = script('return document.querySelector("#help-dialog").textContent')
        assert "aaApply its suggestion to the file" in listed_keys
        assert "With comments selected, R and A act on the selection." in listed_keys
        assert "Overleaf" not in listed_keys
        keys("j")
        assert ring() == source
        keys(ESCAPE)
        assert script('return document.querySelector("#help-dialog").open') is False
        # A view chosen in the list atop gives the keys back to the comments.
        script('const f = document.querySelector("#comment-filter"); f.focus(); f.value = "all"; f.dispatchEvent(new Event("change"));')
        wait_until(lambda: len(listed(browser)) == 4)
        assert script('return document.activeElement.id') == "comments-list"
        # A click on a card puts the ring on it and gives the list the keys, from the editor too.
        script(f"{editor} editor.focus();")
        browser.find_element("css selector", f"#comments-list [data-comment-id='{third}'] .cmt-status").click()
        assert ring() == third
        assert script('return document.activeElement.id') == "comments-list"
        # c opens a note on the whole artifact.
        keys("c")
        assert script('return document.querySelector("#compose-dialog").open') is True
        assert script('return document.querySelector("#compose-anchor").textContent') == "Whole artifact"


@needs_firefox
def test_the_ring_holds_a_third_of_the_way_down_and_an_opened_card_shows_its_end(tmp_path: Path) -> None:
    """Moving by keys keeps the ringed card's middle a third of the way down the list, so the
    eye stays put, a card opened by Space shows its end, where the latest words are, and a
    ringed card that leaves the view hands the ring to the next in its place."""
    kept = CommentStore(store_of(tmp_path, "slides"))
    ids = [kept.add(ArtifactAnchor(), f"Request number {n}.").id for n in range(12)]
    for n in range(6):
        kept.reply(ids[-1], f"Thought number {n} on the last request.", "human")
    with review_page(tmp_path, height=700) as (browser, base):
        script = lambda code: browser.execute_script(code, sandbox=None)
        wait_until(lambda: len(listed(browser)) == 12)
        script("document.activeElement.blur()")
        place = """const list = document.querySelector("#comments-list");
          const card = list.querySelector(".cmt.is-focused");
          const box = list.getBoundingClientRect(), it = card.getBoundingClientRect();
          return {id: card.dataset.commentId, middle: it.top + it.height / 2 - box.top,
                  below: it.bottom - box.bottom, third: list.clientHeight / 3, scroll: list.scrollTop};"""
        at_end = ('const list = document.querySelector("#comments-list");'
                  ' return list.scrollTop + list.clientHeight >= list.scrollHeight - 1')
        press(browser, *["j"] * 6)
        at = script(place)
        assert at["id"] == ids[5] and at["scroll"] > 0
        assert abs(at["middle"] - at["third"]) <= 2 or script(at_end), at
        press(browser, "j")
        moved = script(place)
        assert moved["id"] == ids[6]
        assert abs(moved["middle"] - at["middle"]) <= 2 or script(at_end), (at, moved)
        press(browser, "g", "g")
        assert script(place)["scroll"] == 0
        # Space opens the last card and shows its end.
        press(browser, "G", " ")
        shown = script(place)
        assert shown["id"] == ids[-1] and shown["below"] <= 0
        assert "Thought number 5 on the last request." in script(
            'return document.querySelector("#comments-list .cmt.is-focused .cmt-thread").textContent')
        # Shift+Space opens every card, and again closes them all.
        every = 'return document.querySelectorAll("#comments-list .cmt .cmt-actions").length'
        chord(browser, SHIFT, " ")
        assert script(every) == 12
        chord(browser, SHIFT, " ")
        assert script(every) == 0
        press(browser, "g", "g", *["j"] * 5)
        script('document.querySelector("#comments-list").scrollTop = 0;')
        script("window.confirm = () => true;")
        for pressed, then in ((["R"], ids[6]), (["A"], ids[7]), (["d", "d"], ids[8])):
            press(browser, *pressed)
            wait_until(lambda: script(place)["id"] == then)
            handed = script(place)
            assert script(at_end) or (handed["scroll"] > 0 and abs(handed["middle"] - handed["third"]) <= 2), (pressed, handed)
            script('document.querySelector("#comments-list").scrollTop = 0;')


@needs_firefox
def test_the_slides_and_their_previews_keep_their_keys(tmp_path: Path) -> None:
    """The slide show takes its keys on the page itself as in the artifact, where the comment
    keys rest until it ends: Space, the arrows, n, Home and End move the slides and leave the
    ring where it was, and ? opens no Help. Keys typed in the artifact and in its slide previews
    stay there, where the previews' arrows go through the deck."""
    deck = ('<!doctype html><html><head><meta charset="utf-8"><title>Slides</title></head><body><main class="pages">'
            + "".join(f'<section class="page"><h1>Page {n}</h1><p>Tea is served on page {n}.</p></section>' for n in range(1, 5))
            + '</main></body></html>')
    kept = CommentStore(store_of(tmp_path, "slides"))
    first = kept.add(ArtifactAnchor(), "Name the second example.").id
    kept.add(ArtifactAnchor(), "Cite the survey here.")
    # Without the browser's full screen the pane lies over the page, as on an iPhone, and the
    # show runs the same.
    with review_page(tmp_path, deck=deck, prefs='user_pref("full-screen-api.enabled", false);\n') as (browser, base):
        script = lambda code: browser.execute_script(code, sandbox=None)
        frame = 'document.querySelector("#artifact-frame")'
        wait_until(lambda: len(listed(browser)) == 2
                   and script(f'return {frame}.contentDocument.querySelectorAll("main.pages > section.page").length') == 4)
        ring = lambda: ringed(browser)
        script("document.activeElement.blur()")
        press(browser, "j")
        assert ring() == first
        script('document.querySelector("#fullscreen-btn").click()')
        wait_until(lambda: script(f'return {frame}.contentDocument.documentElement.hasAttribute("data-html-mcp-presentation")'))
        page = lambda: script('return document.querySelector("#presentation-page").textContent')
        wait_until(lambda: page() == "1 / 4")
        # The keys on the page itself, as after a press of the show's own buttons. The show gives
        # the artifact the keys a frame after it starts, which is let pass first.
        wait_until(lambda: script('return document.activeElement.id') == "artifact-frame")
        script(FITTED)
        script("document.activeElement.blur()")
        assert script("return document.activeElement === document.body") is True
        for key, then in ((" ", "2 / 4"), (DOWN, "3 / 4"), ("n", "4 / 4"), ("j", "4 / 4"), (HOME, "1 / 4"),
                          (END, "4 / 4"), ("?", "4 / 4")):
            press(browser, key)
            wait_until(lambda: page() == then)
            assert [ring(), opened(browser), script('return document.querySelector("#help-dialog").open')] \
                == [first, [], False], key
        # And in the artifact, which the show gives the keys.
        script(f"{frame}.contentWindow.focus()")
        press(browser, "p")
        wait_until(lambda: page() == "3 / 4")
        assert ring() == first
        script('document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", bubbles: true}))')
        wait_until(lambda: not script(f'return {frame}.contentDocument.documentElement.hasAttribute("data-html-mcp-presentation")'))
        # Out of the show, keys typed in the artifact stay there too.
        script(f"{frame}.contentWindow.focus()")
        press(browser, "j", " ")
        assert [ring(), opened(browser)] == [first, []]
        # The previews' arrows go through the deck, and the ring stays.
        script('document.querySelector("#thumbs-btn").click()')
        thumbs = 'document.querySelector("#thumbs-frame")'
        wait_until(lambda: script(f'return {thumbs}.contentDocument?.querySelectorAll("main.pages > section.page").length') == 4)
        script(f"{thumbs}.contentWindow.focus()")
        current = (f'return [...{thumbs}.contentDocument.querySelectorAll("main.pages > section.page")]'
                   '.findIndex((page) => page.classList.contains("html-mcp-thumb-current")) + 1')
        press(browser, HOME)
        wait_until(lambda: script(current) == 1)
        press(browser, DOWN)
        wait_until(lambda: script(current) == 2)
        press(browser, "j", END)
        wait_until(lambda: script(current) == 4)
        assert [ring(), opened(browser)] == [first, []]
        # Back on the page, the comment keys work the list again.
        script("document.activeElement.blur()")
        press(browser, "j")
        assert ring() != first


@needs_firefox
def test_help_opens_from_the_menu_and_the_question_mark_on_the_page_shown_last(tmp_path: Path) -> None:
    """Help (?) in the ⋯ menu, or ? anywhere on the page, opens Help: its Start here page says
    how to comment on this page, its tabs go round with the arrows, it opens on the page shown
    last and at that page's top, its text follows the size Settings chooses, and more… under
    the search box opens its Search page."""
    with review_page(tmp_path) as (browser, base):
        script = lambda code, *args: browser.execute_script(code, script_args=list(args), sandbox=None)
        shown = lambda: script('''const d = document.querySelector("#help-dialog");
          const tab = document.querySelector('#help-tabs [aria-selected="true"]');
          return d.open ? [tab.dataset.page, document.activeElement === tab,
                           [...document.querySelectorAll(".help-page")].filter((p) => !p.hidden).map((p) => p.id),
                           document.querySelector("#help-pages").scrollTop] : null''')
        close = lambda: script('document.querySelector("#help-dialog").close(); document.activeElement.blur();')
        assert script('return document.querySelector("#help-btn").textContent') == "Help (?)"
        browser.find_element("css selector", "#more-btn").click()
        browser.find_element("css selector", "#help-btn").click()
        wait_until(lambda: shown() == ["start", True, ["help-start"], 0])
        assert script('return document.querySelector("#more-menu").hidden') is True
        assert script('return [...document.querySelectorAll("#help-tabs [role=tab]")].map((t) => t.textContent)') \
            == ["Start here", "Search", "Keys"]
        start = script('return document.querySelector("#help-start").textContent.replace(/\\s+/g, " ")')
        for words in ("Select words on a page and choose Comment", "+ comment beside it in the Pages tab",
                      "Add a note on the whole artifact… in the ⋯ menu", "box tool", "bell"):
            assert words in start, words
        # Right and Left go round the tabs, and Home and End go to the ends.
        for key, page in [("", "search"), ("", "keys"), ("", "start"), ("", "keys"),
                          (HOME, "start"), (END, "keys")]:
            press(browser, key)
            wait_until(lambda: shown() == [page, True, [f"help-{page}"], 0])
        # The Keys page names this page's own keys after the comments'.
        keys_page = script('return document.querySelector("#help-keys").textContent')
        for words in ("Slide show", "Slide previews", "Source editor", "With Vim keys", "Next slide"):
            assert words in keys_page, words
        # A page scrolled down opens at its top next time, and ? opens the page shown last.
        browser.find_element("css selector", "#help-tab-search").click()
        script('return new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))')
        script('document.querySelector("#help-pages").scrollTop = 300')
        assert script('return document.querySelector("#help-pages").scrollTop') > 0
        close()
        press(browser, "?")
        wait_until(lambda: shown() == ["search", True, ["help-search"], 0])
        close()
        browser.refresh()
        wait_until(lambda: script('return document.querySelector("#comment-filter").options.length > 1'))
        press(browser, "?")
        wait_until(lambda: (shown() or [None])[0] == "search")
        # The text follows the size Settings chooses, as the other dialogs do.
        size = lambda: script('return parseFloat(getComputedStyle(document.querySelector("#help-search p")).fontSize)')
        at_100 = size()
        script('document.querySelector("[data-text-choice=\'130\']").click()')
        assert size() == pytest.approx(at_100 * 1.3, abs=0.1)
        script('document.querySelector("[data-text-choice=\'100\']").click()')
        # more… under the search box opens the Search page, whichever page was shown last.
        browser.find_element("css selector", "#help-tab-keys").click()
        close()
        browser.find_element("css selector", "#comment-search").click()
        wait_until(lambda: script('return !document.querySelector("#search-terms").hidden'))
        assert script('return document.querySelector("#search-help-btn").textContent') == "more…"
        browser.find_element("css selector", "#search-help-btn").click()
        wait_until(lambda: shown() == ["search", True, ["help-search"], 0])


@needs_firefox
def test_the_search_example_in_help_finds_what_help_says(tmp_path: Path) -> None:
    """The Search page's example, typed into the search box step by step, lists what each step
    says: the threads with the word, those the agent wrote in, and the one answered on the day,
    in any status. Each other example on the page reads as the condition its row names."""
    kept = CommentStore(store_of(tmp_path, "slides"))
    sought = kept.add(PageAnchor(number=1, title="First"), "Move the legend under the chart.")
    kept.reply(sought.id, "Moved the legend under the chart.", "agent")
    kept.update_many([sought.id], "human", "", status="resolved")
    later = kept.add(ArtifactAnchor(), "The legend still covers a bar.")
    kept.reply(later.id, "Shrunk the legend.", "agent")
    unanswered = kept.add(ArtifactAnchor(), "Is the legend needed at all?")
    other = kept.add(ArtifactAnchor(), "Cite the survey.")
    kept.reply(other.id, "Cited it.", "agent")
    stamp(store_of(tmp_path, "slides"), {
        sought.id: [local_moment(11, 12, 15), local_moment(11, 13, 10)],
        later.id: [local_moment(11, 14, 9), local_moment(11, 14, 10)],
        unanswered.id: [local_moment(11, 13, 11)],
        other.id: [local_moment(11, 10), local_moment(11, 12)]})
    names = {sought.id: "sought", later.id: "later", unanswered.id: "unanswered", other.id: "other"}
    with review_page(tmp_path) as (browser, base):
        script = lambda code, *args: browser.execute_script(code, script_args=list(args), sandbox=None)
        wait_until(lambda: len(listed(browser)) == 3)
        typed = script('return [...document.querySelectorAll("#help-search .help-typed")].map((c) => c.textContent)')
        assert typed == ["legend", "legend from:agent", "legend from:agent after:11-13 before:11-14"]
        for text, expected in zip(typed, [["later", "sought", "unanswered"], ["later", "sought"], ["sought"]]):
            script('const box = document.querySelector("#comment-search"); box.value = arguments[0];'
                   ' box.dispatchEvent(new Event("input"))', text)
            wait_until(lambda: sorted(names[cid] for cid in listed(browser)) == expected)
            assert script('return document.querySelector("#comment-filter").value') == "all", text
        # Each other example on the page reads as the condition its row names. A date in the
        # dates table is read after after:.
        year = datetime.now().year
        word = lambda value, no=False: {"not": no, "field": "", "value": value}
        term = lambda field, value, no=False: {"not": no, "field": field, "value": value}
        moment = lambda *at: datetime(year, *at).timestamp() * 1000
        readings = {
            "legend color": [[word("legend"), word("color")]],
            "chart OR table": [[word("chart")], [word("table")]],
            '"title slide"': [[word("title slide")]],
            "-backup": [[word("backup", True)]],
            "from:agent": [[term("from", "agent")]],
            "file:slides": [[term("file", "slides")]],
            "after:11-12": [[term("after", moment(11, 12))]],
            "after:11-13": [[term("after", moment(11, 13))]],
            "before:11-14": [[term("before", moment(11, 14))]],
            "legend color OR table": [[word("legend"), word("color")], [word("table")]],
            "-from:agent": [[term("from", "agent", True)]],
            "from:me": [[term("from", "me")]],
            "from:me after:11-12": [[term("from", "me"), term("after", moment(11, 12))]],
            "note:": [[word("note:")]],
            "11-12": [[term("after", moment(11, 12))]],
            f"{year}-11-12": [[term("after", moment(11, 12))]],
            "11-12T09": [[term("after", moment(11, 12, 9))]],
            "11-12T09:30": [[term("after", moment(11, 12, 9, 30))]],
            '"11-12 09:30"': [[term("after", moment(11, 12, 9, 30))]],
        }
        examples = script('return [...document.querySelectorAll("#help-search code:not(.help-typed)")].map((c) => c.textContent)')
        examples = [f"{year}-11-12" if text == "2026-11-12" else text for text in examples]
        assert sorted(set(examples)) == sorted(readings)
        dated = [f"{year}-11-12" if text == "2026-11-12" else text for text in script(
            'return [...document.querySelectorAll("#help-search-dates code")].map((c) => c.textContent)')]
        read = script('''return import("/static/shared/comment-search.js").then(({ parseSearch }) =>
          arguments[0].map((text) => parseSearch(arguments[1].includes(text) ? `after:${text}` : text, arguments[2])))''',
                      examples, dated, year)
        assert dict(zip(examples, read)) == {text: readings[text] for text in examples}
        # A thread is met as a whole: from:me after:11-12 finds a thread written in on 11-10
        # that the agent answered on 11-12.
        script('const box = document.querySelector("#comment-search"); box.value = "from:me after:11-12";'
               ' box.dispatchEvent(new Event("input"))')
        wait_until(lambda: "other" in [names[cid] for cid in listed(browser)])


@needs_firefox
def test_the_editor_holds_the_cursor_line_where_settings_says(tmp_path: Path) -> None:
    """Settings can hold the source editor's cursor line a third or half of the way down, as the
    comment keys hold the ring in the list: the keys move the text under the cursor, the ends
    of the file stay at the editor's ends, a click leaves the text where it is, and the choice
    is kept for next time."""
    deck = ('<!doctype html><html><head><meta charset="utf-8"><title>Slides</title></head><body><main class="pages">\n'
            + "".join(f'<section class="page"><p>Line {n}</p></section>\n' for n in range(1, 121))
            + '</main></body></html>\n')
    with review_page(tmp_path, deck=deck, height=900) as (browser, base):
        script = lambda code: browser.execute_script(code, sandbox=None)
        editor = 'const editor = (window.wrappedJSObject || window).ace.edit("source-editor");'
        script('localStorage.setItem("htmlMcpVimKeys", "1")')
        browser.refresh()
        wait_until(lambda: script('return document.querySelector("#comment-filter").options.length > 1'))
        script('document.querySelector("[data-view=source]").click()')
        wait_until(lambda: script(f'{editor} return editor.getValue().includes("Line 120")'))
        choice = lambda name: f'document.querySelector(\'[data-cursor-choice="{name}"]\')'
        script(f"{choice('third')}.click()")
        assert script(f'return {choice("third")}.getAttribute("aria-checked")') == "true"
        # Which row the cursor is on, the screen line it shows on, and the line a third down.
        place = (f'{editor} const row = editor.getCursorPosition().row;'
                 ' const top = editor.renderer.textToScreenCoordinates(row, 0).pageY'
                 ' - editor.renderer.scroller.getBoundingClientRect().top;'
                 ' return [row, Math.round(top / editor.renderer.lineHeight),'
                 ' Math.round(editor.renderer.scroller.clientHeight / 3 / editor.renderer.lineHeight)];')
        held = lambda row: (lambda r: r[0] == row and abs(r[1] - r[2]) <= 1)(script(place))
        script(f"{editor} editor.focus();")
        press(browser, *["j"] * 40)
        wait_until(lambda: held(40))
        # At the end the last line goes only as low as the editor scrolls, with no room made below.
        press(browser, "G")
        bottom = (f'{editor} return editor.session.getScrollTop() <= editor.session.getScreenLength()'
                  ' * editor.renderer.lineHeight - 0.75 * editor.renderer.scroller.clientHeight'
                  ' + editor.renderer.lineHeight;')
        last = script(f'{editor} return editor.session.getLength() - 1;')
        wait_until(lambda: script(place)[0] == last and script(bottom))
        assert script(place)[1] > script(place)[2] + 1
        press(browser, "g", "g")
        wait_until(lambda: script(place)[:2] == [0, 0])
        press(browser, *["j"] * 30)
        wait_until(lambda: held(30))
        # A click moves the cursor and leaves the text where it is.
        scroll = f"{editor} return editor.session.getScrollTop();"
        before = script(scroll)
        point = script(f"{editor} const at = editor.renderer.textToScreenCoordinates(44, 2);"
                       " return [Math.round(at.pageX + 4), Math.round(at.pageY + 4)];")
        ActionSequence(browser, "pointer", "mouse", {"pointerType": "mouse"}).pointer_move(point[0], point[1]) \
            .pointer_down().pointer_up().perform()
        wait_until(lambda: script(place)[0] == 44)
        assert script(scroll) == before
        # Anywhere again: the keys move the cursor and the text stays.
        script(f"{choice('free')}.click()")
        script(f"{editor} editor.focus();")
        press(browser, *["j"] * 5)
        wait_until(lambda: script(place)[0] == 49)
        assert script(scroll) == before
        # 1/2 down holds the cursor's line in the middle of the editor, and is kept for next time.
        script(f"{choice('half')}.click()")
        assert [script(f'return {choice(name)}.getAttribute("aria-checked")') for name in ("free", "third", "half")] \
            == ["false", "false", "true"]
        script(f"{editor} editor.focus();")
        press(browser, *["j"] * 5)
        middle = place.replace("clientHeight / 3", "clientHeight / 2")
        wait_until(lambda: (lambda r: r[0] == 54 and abs(r[1] - r[2]) <= 1)(script(middle)))
        browser.refresh()
        assert wait_until(lambda: script(f'return {choice("half")}.getAttribute("aria-checked")')) == "true"
        assert script('return [...document.querySelectorAll("[data-cursor-choice]")].map((button) => button.textContent)') \
            == ["Anywhere", "1/3 down", "1/2 down"]
        assert script('return [...document.querySelectorAll("[data-letters-choice]")].map((button) => button.textContent)') \
            == ["On", "Off"]


@needs_firefox
@pytest.mark.parametrize("platform, held, alt", [("MacIntel", "Cmd", "Option"), ("Linux x86_64", "Ctrl", "Alt")])
def test_on_a_mac_the_page_names_the_keys_a_mac_has(tmp_path: Path, platform: str, held: str, alt: str) -> None:
    """A Mac holds the page's shortcuts with Cmd and Option. Its tooltips and every page of Help
    name them so, while Ctrl+[ stays Ctrl, and another system reads Ctrl and Alt."""
    with review_page(tmp_path, prefs=f'user_pref("general.platform.override", "{platform}");\n') as (browser, base):
        script = lambda code: browser.execute_script(code, sandbox=None)
        assert script("return navigator.platform") == platform
        wait_until(lambda: f"{held}+{alt}+Enter" in script('return document.querySelector("#call-agent-btn").title'))
        script('document.querySelector("#help-btn").click()')
        wait_until(lambda: script('return document.querySelector("#help-dialog").open'))
        assert f"{held}+{alt}+Enter" in script('return document.querySelector("#help-start").textContent')
        script('document.querySelector("#help-tab-keys").click()')
        keys = script('return document.querySelector("#help-keys").textContent')
        assert all(f"{held}+{key}" in keys for key in ("S", f"{alt}+M", f"{alt}+P", f"{alt}+K", f"{alt}+Enter"))
        assert "Ctrl+[" in keys
        saved = script('return document.querySelector("#source-save-btn").title')
        assert f"({held}+S)" in saved
        other = "Ctrl+Alt+" if held == "Cmd" else "Cmd+Option+"
        assert other not in keys + saved + script('return document.querySelector("#call-agent-btn").title')


@needs_firefox
def test_help_fits_a_narrow_window_on_every_page(tmp_path: Path) -> None:
    """At 480 pixels wide, every page of Help fits the dialog at the default text size and at
    the largest: nothing sticks out of it, and nothing in it scrolls sideways."""
    with review_page(tmp_path) as (browser, base):
        script = lambda code, *args: browser.execute_script(code, script_args=list(args), sandbox=None)
        browser.set_window_rect(width=480, height=700)
        for size in ("100", "150"):
            script('document.querySelector(`[data-text-choice="${arguments[0]}"]`).click()', size)
            for page in ("start", "search", "keys"):
                script('document.querySelector("#help-dialog").open || document.querySelector("#help-btn").click();'
                       ' document.querySelector(`#help-tab-${arguments[0]}`).click()', page)
                spill = script('''const dialog = document.querySelector("#help-dialog");
                  const box = dialog.getBoundingClientRect();
                  const out = [...dialog.querySelectorAll("*")].filter((node) => {
                    const at = node.getBoundingClientRect();
                    return at.width > 0 && (at.right > box.right + 0.5 || at.left < box.left - 0.5);
                  }).map((node) => `${node.tagName} ${node.getAttribute("class") ?? ""} ${node.textContent.slice(0, 40)}`);
                  const sideways = [dialog, ...dialog.querySelectorAll("*")].filter((node) => node.clientWidth > 0
                    && node.scrollWidth > node.clientWidth + 1 && getComputedStyle(node).overflowX !== "visible")
                    .map((node) => node.id || node.tagName);
                  return [out, sideways, box.right <= innerWidth, document.documentElement.scrollWidth <= innerWidth];''')
                assert spill == [[], [], True, True], (size, page, spill)



@needs_firefox
def test_a_reply_written_while_the_page_cannot_hear_its_server_shows_once_it_can(tmp_path: Path) -> None:
    """The page hears of a reply over its socket. A reply written while the socket is closed,
    or before it first opens, reaches no page, so each opening reads the comments again."""
    import asyncio

    kept = CommentStore(store_of(tmp_path, "slides"))
    asked = kept.add(ArtifactAnchor(), "Shorten the title.").id
    with review_page(tmp_path) as (browser, base):
        wait_until(lambda: listed(browser) == [asked])
        unanswered = lambda: browser.execute_script(
            f'return document.querySelector(\'[data-comment-id="{asked}"] .cmt-unanswered\') !== null')
        assert not unanswered()
        shared = SERVERS[base]
        review = next(route.handler.__self__ for route in shared.runner.app.router.routes()
                      if route.resource is not None and route.resource.canonical == "/ws")

        async def close_sockets() -> None:
            for page in list(review.websockets):
                await page.close()

        asyncio.run_coroutine_threadsafe(close_sockets(), shared.loop).result(5)
        # The page asks again a moment later; the reply is written before it does.
        post_json(f"{base}/artifacts/slides/comments/{asked}/reply", {"text": "Shortened.", "author": "agent"})
        wait_until(unanswered)


@needs_firefox
def test_an_agents_reply_shows_its_markdown_and_a_closed_card_its_words(tmp_path: Path) -> None:
    """An opened card draws a reply's bold, list and code. A closed card shows the same words
    without their marks."""
    kept = CommentStore(store_of(tmp_path, "slides"))
    asked = kept.add(ArtifactAnchor(), "Shorten the title.").id
    kept.reply(asked, "**Done.** The title is shorter.\n- Cut `the subtitle`\n- Kept the date", "agent")
    with review_page(tmp_path) as (browser, base):
        card = f'document.querySelector(\'[data-comment-id="{asked}"]\')'
        wait_until(lambda: browser.execute_script(f'return {card}?.querySelector(".cmt-latest")?.textContent')
                   == "agent  Done. The title is shorter.\n• Cut the subtitle\n• Kept the date")
        browser.execute_script(f"{card}.querySelector('.cmt-head').click()")
        reply = f"{card}.querySelector('.thread-entry.author-agent .thread-text')"
        wait_until(lambda: browser.execute_script(f"return {reply}?.querySelector('strong')?.textContent") == "Done.")
        assert browser.execute_script(f"return [...{reply}.querySelectorAll('ul > li')].map((item) => item.textContent)") \
            == ["Cut the subtitle", "Kept the date"]
        assert browser.execute_script(f"return {reply}.querySelector('li code').textContent") == "the subtitle"
