import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest
import yaml

from html_mcp_web.config import load_config
from html_mcp_web.project_server import SharedProjectServer


marionette = pytest.importorskip("marionette_driver.marionette")
from marionette_driver.marionette import ActionSequence  # noqa: E402


def type_keys(browser, keys):
    """Keys pressed one by one, with <C-[> for Ctrl+[ and <Enter> for Enter."""
    actions = ActionSequence(browser, "key", "keyboard")
    for key in keys:
        if key == "<C-[>":
            actions.key_down("\ue009").key_down("[").key_up("[").key_up("\ue009")
        elif key == "<Enter>":
            actions.key_down("\ue007").key_up("\ue007")
        else:
            actions.key_down(key).key_up(key)
    actions.perform()

def available_port() -> int:
    import socket

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_until(check, timeout: float = 12):
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


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_source_selection_wraps_exactly_and_split_divider_resizes(tmp_path: Path, monkeypatch) -> None:
    target = "SELECT START " + "exact wrapped characters " * 12 + "SELECT END"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    source = home / "slides.html"
    source.write_text(
        '<!doctype html><html><head><title>Source</title></head><body><main class="pages">'
        f'<section class="page"><p>before {target} after</p></section></main></body></html>',
        encoding="utf-8",
    )
    port = available_port()
    config_path = home / ".html-mcp-web.yaml"
    config_path.write_text(yaml.safe_dump({
        "artifacts": {"slides": {"label": "Slides", "layout": "slides", "main": str(source)}},
        "watch": ["*.html"],
        "port": port,
    }, sort_keys=False), encoding="utf-8")
    shared = SharedProjectServer(load_config(config_path))
    profile = tempfile.mkdtemp(prefix="html_mcp_source_editor_")
    marionette_port = available_port()
    (Path(profile) / "user.js").write_text(
        f'user_pref("marionette.port", {marionette_port});\n', encoding="utf-8")
    browser_process = None
    browser = None
    try:
        shared.ensure()
        browser_process = subprocess.Popen(
            ["firefox", "-marionette", "-headless", "-no-remote", "-profile", profile, "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        browser = marionette.Marionette(host="127.0.0.1", port=marionette_port, startup_timeout=30)
        browser.start_session()
        browser.set_window_rect(width=1200, height=760)
        browser.navigate(f"http://127.0.0.1:{port}")
        wait_until(lambda: browser.execute_script(
            'return document.querySelector("#artifact-status")?.textContent === "ready"'))
        assert browser.execute_script(
            'return [document.querySelector("#main-file").textContent, document.querySelector("#main-file").title]'
        ) == ["slides.html", "~/slides.html"]
        assert get_json(f"http://127.0.0.1:{port}/state")["artifacts"]["slides"]["main_file"] == str(source)
        placement = browser.execute_script('''
          const tabs = document.querySelector(".view-tabs");
          const toolbar = document.querySelector(".workspace-toolbar");
          const topbar = document.querySelector(".topbar");
          const fit = document.querySelector("#zoom-reset-btn");
          fit.classList.remove("hidden");
          const toolbarBox = toolbar.getBoundingClientRect();
          const tabsBox = tabs.getBoundingClientRect();
          const fitBox = fit.getBoundingClientRect();
          const searchBox = document.querySelector("#search-btn").getBoundingClientRect();
          const areaBox = document.querySelector("#area-btn").getBoundingClientRect();
          const thumbsBox = document.querySelector("#thumbs-btn").getBoundingClientRect();
          const artifactTabs = document.querySelector("#artifact-tabs").getBoundingClientRect();
          return {
            inTopbar: topbar.contains(tabs),
            inWorkspace: document.querySelector("#workspace").contains(tabs),
            toolbarAboveArtifact: toolbarBox.bottom <=
              document.querySelector("#artifact-pane").getBoundingClientRect().top + 1,
            fitInToolbar: toolbar.contains(fit),
            tabsLeftOfArtifactTabs: tabsBox.right <= artifactTabs.left,
            boxFitSearchAtRight: thumbsBox.right < areaBox.left && areaBox.right < fitBox.left
              && fitBox.right < searchBox.left,
            searchAtRight: Math.abs(
              toolbarBox.right - searchBox.right - parseFloat(getComputedStyle(toolbar).paddingRight)
            ) < 1,
            toolbarHeight: toolbarBox.height,
            topbarHeight: topbar.getBoundingClientRect().height,
          };
        ''')
        assert {key: placement[key] for key in (
            "inTopbar", "inWorkspace", "toolbarAboveArtifact", "fitInToolbar",
            "tabsLeftOfArtifactTabs", "boxFitSearchAtRight", "searchAtRight",
        )} == {
            "inTopbar": True,
            "inWorkspace": False,
            "toolbarAboveArtifact": True,
            "fitInToolbar": True,
            "tabsLeftOfArtifactTabs": True,
            "boxFitSearchAtRight": True,
            "searchAtRight": True,
        }
        # The panels' bars share one height: the artifact's, the editor's and the comments' tabs.
        bars = browser.execute_script(
            'return [".workspace-toolbar", ".source-toolbar", ".sidebar-tabs"].map((s) =>'
            ' document.querySelector(s).getBoundingClientRect().height);')
        assert max(bars) - min(bars) < 0.5 or bars[1] == 0, bars

        browser.find_element("css selector", '[data-view="source"]').click()
        wait_until(lambda: browser.execute_script(
            'const page = window.wrappedJSObject || window;'
            'return page.ace && page.ace.edit("source-editor").getValue().includes("SELECT START")'))
        # A− and A+ step the editor's type by a pixel and keep the size for the next visit.
        font_size = 'return (window.wrappedJSObject || window).ace.edit("source-editor").getFontSize();'
        assert browser.execute_script(font_size) == "13px"
        for button in ("larger", "larger", "smaller"):
            browser.execute_script(f'document.querySelector("#source-font-{button}-btn").click()')
        assert browser.execute_script(font_size) == "14px"
        assert browser.execute_script('return localStorage.getItem("htmlMcpSourceFontSize")') == "14"
        browser.execute_script('document.querySelector("#source-font-smaller-btn").click()')
        # The moon button turns the page dark and back, keeps the choice, and takes the
        # editor and the artifact's frame with it; the artifact keeps its own colours.
        theme = '''
          const page = window.wrappedJSObject || window;
          const frame = document.querySelector("#artifact-frame").contentDocument.documentElement;
          return [document.documentElement.dataset.theme, localStorage.getItem("htmlMcpTheme"),
                  page.ace.edit("source-editor").getTheme(), frame.dataset.htmlMcpTheme];
        '''
        browser.execute_script('document.querySelector("#theme-btn").click()')
        assert browser.execute_script(theme) == ["dark", "dark", "ace/theme/one_dark", "dark"]
        browser.execute_script('document.querySelector("#theme-btn").click()')
        assert browser.execute_script(theme) == ["light", "light", "ace/theme/textmate", "light"]
        # Long lines wrap until the wrap button turns it off, and the Vim button gives the
        # editor Vim keys, with Ctrl+[ as Escape and :w saving.
        editor = '(window.wrappedJSObject || window).ace.edit("source-editor")'
        assert browser.execute_script(f"return {editor}.session.getUseWrapMode();") is True
        browser.execute_script('document.querySelector("#source-wrap-btn").click()')
        assert browser.execute_script(f"return {editor}.session.getUseWrapMode();") is False
        assert browser.execute_script('return localStorage.getItem("htmlMcpSourceWrap")') == "0"
        browser.execute_script('document.querySelector("#source-wrap-btn").click()')
        assert browser.execute_script(f"return {editor}.session.getUseWrapMode();") is True
        before = browser.execute_script(f"return {editor}.getValue();")
        browser.execute_script('document.querySelector("#source-vim-btn").click()')
        wait_until(lambda: browser.execute_script(f"return Boolean({editor}.$vimModeHandler);"))
        # Outside Insert mode the editor's input field is read-only, so a held key repeats
        # rather than opening macOS's accent menu; Insert mode writes again.
        # A yank goes to the system clipboard too.
        browser.execute_script('''
          navigator.clipboard.writeText = (text) => { window.copied = text; return Promise.resolve(); };
        ''', sandbox=None)
        type_keys(browser, [*"ggyy"])
        assert wait_until(lambda: browser.execute_script("return window.copied ?? null;", sandbox=None)) \
            == browser.execute_script(f"return {editor}.session.getLine(0) + '\\n';")
        field = f"{editor}.textInput.getElement().readOnly"
        assert browser.execute_script(f"return {field};") is True
        type_keys(browser, ["i"])
        assert browser.execute_script(f"return {field};") is False
        type_keys(browser, ["<C-[>"])
        assert browser.execute_script(f"return {field};") is True
        # jj typed quickly leaves Insert mode too, and leaves no j behind.
        kept = browser.execute_script(f"return {editor}.getValue();")
        type_keys(browser, ["i", "j", "j"])
        assert wait_until(lambda: browser.execute_script(f"return {field};") is True)
        assert browser.execute_script(f"return {editor}.getValue();") == kept
        # With a Korean input method on, a key outside Insert mode is read by where it sits
        # (the key that gives ㅣ is l), and the letter the method composes is dropped.
        ime = browser.execute_script(f"""
          const editor = {editor};
          editor.focus();
          editor.gotoLine(1, 0);
          const press = (code) => editor.textInput.getElement().dispatchEvent(new KeyboardEvent("keydown",
            {{key: "Process", code, bubbles: true, cancelable: true}}));
          let blurred = 0;
          editor.textInput.getElement().addEventListener("blur", () => {{ blurred += 1; }});
          editor.textInput.getElement().dispatchEvent(new CompositionEvent("compositionstart", {{bubbles: true, data: ""}}));
          editor.textInput.getElement().dispatchEvent(new CompositionEvent("compositionupdate", {{bubbles: true, data: "ㅣ"}}));
          press("KeyL");
          const column = editor.getCursorPosition().column;
          editor.onTextInput("ㅣ");
          press("KeyH");
          return [column, editor.getCursorPosition().column, editor.getValue() === arguments[0], blurred];
        """, script_args=[before], sandbox=None)
        # A composition outside Insert mode never reaches Ace, which cancelled it by taking
        # the focus off the editor and back: the cursor flickered in Safari at each key.
        assert ime == [1, 0, True, 0], ime
        type_keys(browser, [*"ggOvimtest", "<C-[>", *"dd"])
        assert browser.execute_script(f"return {editor}.getValue();") == before
        assert browser.execute_script('return document.querySelector("#source-save-btn").disabled') is False
        type_keys(browser, [*":w", "<Enter>"])
        wait_until(lambda: browser.execute_script('return document.querySelector("#source-save-btn").disabled'))
        # gc comments on what a motion or a selection covers, here the one line this file
        # has, and the editor has the keys back once the comment is dropped.
        for keys in ("gggcc", "gg0vegc"):
            type_keys(browser, [*keys])
            wait_until(lambda: browser.execute_script('return document.querySelector("#compose-dialog").open'))
            assert browser.execute_script(
                'return document.querySelector("#compose-anchor").textContent').startswith("slides.html:1")
            browser.execute_script('document.querySelector("#compose-cancel").click()')
            wait_until(lambda: browser.execute_script(
                'return document.querySelector("#source-editor").contains(document.activeElement)'))
        browser.execute_script('document.querySelector("#source-vim-btn").click()')
        wait_until(lambda: not browser.execute_script(f"return Boolean({editor}.$vimModeHandler);"))
        assert browser.execute_script(f"return {editor}.textInput.getElement().readOnly;") is False
        # Without Vim keys, Ctrl+Alt+M comments on the selection.
        browser.execute_script(f"{editor}.focus(); {editor}.selection.selectLine();")
        ActionSequence(browser, "key", "keyboard").key_down("\ue009").key_down("\ue00a").key_down("m") \
            .key_up("m").key_up("\ue00a").key_up("\ue009").perform()
        wait_until(lambda: browser.execute_script('return document.querySelector("#compose-dialog").open'))
        # Ctrl+[ drops the comment being written, as Escape does where Safari keeps Escape.
        ActionSequence(browser, "key", "keyboard").key_down("\ue009").key_down("[") \
            .key_up("[").key_up("\ue009").perform()
        wait_until(lambda: browser.execute_script('return !document.querySelector("#compose-dialog").open'))
        assert browser.execute_script(
            'return document.querySelector("#source-file").textContent') == "slides.html"
        selected = browser.execute_script('''
          const page = window.wrappedJSObject || window;
          const editor = page.ace.edit("source-editor");
          const text = editor.getValue();
          const start = text.indexOf("SELECT START");
          const end = text.indexOf("SELECT END") + "SELECT END".length;
          const Range = page.ace.require("ace/range").Range;
          editor.selection.setRange(new Range(0, start, 0, end));
          return editor.getSelectedText();
        ''')
        assert selected == target
        browser.find_element("css selector", "#source-comment-btn").click()
        wait_until(lambda: browser.execute_script('return document.querySelector("#compose-dialog").open'))
        browser.find_element("css selector", "#compose-text").send_keys("Review exactly this source selection")
        browser.find_element("css selector", "#compose-submit").click()

        comments = wait_until(lambda: (
            payload["comments"] if len((payload := get_json(
                f"http://127.0.0.1:{port}/artifacts/slides/comments"))["comments"]) == 1 else None
        ))
        assert comments[0]["anchor"]["quote"] == target
        assert comments[0]["anchor"]["line_start"] == comments[0]["anchor"]["line_end"] == 1
        marker_count = wait_until(lambda: browser.execute_script(
            'return document.querySelectorAll("#source-editor .source-comment-highlight").length'))
        assert marker_count >= 2
        # Ctrl+Alt+K on the commented characters opens their comment in the comments.
        browser.execute_script('''
          const editor = (window.wrappedJSObject || window).ace.edit("source-editor");
          editor.focus();
          editor.moveCursorTo(0, editor.getValue().indexOf("SELECT START") + 5);
        ''')
        ActionSequence(browser, "key", "keyboard").key_down("\ue009").key_down("\ue00a").key_down("k") \
            .key_up("k").key_up("\ue00a").key_up("\ue009").perform()
        wait_until(lambda: browser.execute_script(
            'return document.querySelector(".comment-card.focused")?.dataset.commentId') == comments[0]["id"])

        browser.find_element("css selector", '[data-view="split"]').click()
        before = browser.execute_script('''
          return [document.querySelector("#artifact-pane").getBoundingClientRect().width,
                  document.querySelector("#source-pane").getBoundingClientRect().width];
        ''')
        grip = browser.execute_script('''
          const r = document.querySelector("#split-grip").getBoundingClientRect();
          return {x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2)};
        ''')
        drag = browser.actions.sequence("pointer", "mouse", {"pointerType": "mouse"})
        drag.pointer_move(grip["x"], grip["y"]).pointer_down()
        drag.pointer_move(grip["x"] - 120, grip["y"], duration=250).pointer_up().perform()
        after = browser.execute_script('''
          return [document.querySelector("#artifact-pane").getBoundingClientRect().width,
                  document.querySelector("#source-pane").getBoundingClientRect().width];
        ''')
        assert after[0] < before[0] - 80
        assert after[1] > before[1] + 80
    finally:
        if browser is not None:
            try:
                browser.delete_session()
            except Exception:
                pass
        if browser_process is not None:
            browser_process.terminate()
            try:
                browser_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                browser_process.kill()
        shutil.rmtree(profile, ignore_errors=True)
        shared.stop()
