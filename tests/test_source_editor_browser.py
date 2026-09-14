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
def test_source_selection_wraps_exactly_and_split_divider_resizes(tmp_path: Path) -> None:
    target = "SELECT START " + "exact wrapped characters " * 12 + "SELECT END"
    source = tmp_path / "slides.html"
    source.write_text(
        '<!doctype html><html><head><title>Source</title></head><body><main class="pages">'
        f'<section class="page"><p>before {target} after</p></section></main></body></html>',
        encoding="utf-8",
    )
    port = available_port()
    config_path = tmp_path / ".html-mcp-web.yaml"
    config_path.write_text(yaml.safe_dump({
        "artifacts": {"slides": {"label": "Slides", "layout": "slides", "main": "slides.html"}},
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

        browser.find_element("css selector", '[data-view="source"]').click()
        wait_until(lambda: browser.execute_script(
            'const page = window.wrappedJSObject || window;'
            'return page.ace && page.ace.edit("source-editor").getValue().includes("SELECT START")'))
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
