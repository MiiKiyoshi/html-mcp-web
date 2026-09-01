import json
import re
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
Keys = pytest.importorskip("marionette_driver.keys").Keys


def available_port() -> int:
    import socket

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def slides_html(text: str = "Selected sentence.") -> str:
    return f'''<!doctype html>
<html><head><meta charset="utf-8"><title>Slides</title></head><body>
<main class="pages">
  <section class="page"><div data-layout-guard><h1>First</h1><p id="target">{text}</p>
    <!-- Three lines: the first two live inside a bold run whose subscript dips below the
         baseline. Counting only bare text nodes, or letting the dip glue lines together,
         both undercount. -->
    <p id="subscript" style="width: 300px; font-size: 18px; line-height: 1.2"><b>Optimization History (H<span style="position: relative; top: 14px; font-size: 12px">k−1</span>) is the first line here</b> and only the tail is bare text</p>
    <!-- One line shaped like inline KaTeX: a superscript arrives before the body text, a
         3px vlist row sits just under it, and a big operator's lower limit reaches only
         partway into the text band. Each of these once started a phantom second line. -->
    <p id="mathlike" style="width: 700px; font-size: 18px; line-height: 1.4">node (n<span style="position: relative; top: -9px; font-size: 12px">s</span><span style="position: relative; top: 8px; font-size: 12px">k</span><span style="display: inline-block; width: 10px; height: 3px; vertical-align: -14px"></span>) (5) and <span style="font-size: 26px">&int;</span><span style="position: relative; top: 12px; font-size: 12px">0</span> stays on one line</p>
  </div></section>
  <div class="script-block"><div class="script-text"><p>Speaker script for the first page.</p></div></div>
  <section class="page"><div data-layout-guard><h1>Second</h1><p>Second page.</p></div>
    <table id="metrics" style="width: 400px"><tr><td style="width: 200px">Used<br>Value</td><td style="width: 200px"></td></tr></table>
    <table id="wrapped" style="width: 120px; table-layout: fixed"><tr><td>Automatic wrapping is detected here</td></tr></table>
    <svg id="chart" width="200" height="100" viewBox="0 0 200 100"><rect x="10" y="8" width="180" height="50"/><text x="12" y="88">label</text></svg>
    <!-- Drawn at twice its viewBox, the way a deck's figures are: a Range inside svg text
         reports the whole element once the viewBox scales, and reports it in user units. -->
    <svg id="scaled-chart" width="224" height="24" viewBox="0 0 112 12">
      <text id="svg-words" x="1" y="9" font-size="9">many words in this label</text></svg>
    <table id="hidden" style="width: 420px"><tr><td>alpha</td><td style="display:none">ghost</td><td>beta has much longer content</td></tr></table>
  </section>
</main>
</body></html>'''


def report_html() -> str:
    pages = "".join(
        f'<section class="page"><div data-layout-guard><h1>Report {number}</h1></div></section>'
        for number in range(1, 4)
    )
    return f'<!doctype html><html><head><title>Report</title></head><body><main class="pages">{pages}</main></body></html>'


def problem_html() -> str:
    return '''<!doctype html>
<html><head><meta charset="utf-8"><title>Problems</title></head><body>
<main class="pages"><section class="page">
  <div data-layout-guard style="width: 900px; height: 180px; overflow: hidden">
    <!-- The formula carries the shape KaTeX emits: a MathML copy holding the TeX source,
         hidden the way KaTeX hides it, beside the glyphs the reader sees. -->
    <p style="font-size: 20px; width: 600px"><span class="katex"><span class="katex-mathml"
      style="position:absolute;clip:rect(1px,1px,1px,1px);width:1px;height:1px;overflow:hidden"
      >\\overline{x}</span><span class="katex-html">x&#8254;</span></span> A deliberately long first line for the layout checker.<br>x</p>
    <div><div style="height: 50px">first sibling</div><div style="height: 50px; margin-top: -20px">second sibling</div></div>
    <!-- Borderline cases: both verdicts flip when measured geometry is read at the
         pane's zoom instead of in page pixels. -->
    <!-- The shape runs past the viewBox bottom, which no box-model measurement sees. -->
    <svg id="cut" viewBox="0 -14 400 60" width="400" height="60"><rect x="10" y="0" width="380" height="56"/></svg>
    <!-- Declares a box twice the width of what it draws, so half the strip is held idle. -->
    <svg id="idle" viewBox="0 0 800 80" width="800" height="80"><rect x="10" y="10" width="380" height="60"/></svg>
    <!-- The drawing fills its viewBox, but the element box is a different shape, so the
         rendering keeps the viewBox's proportions and leaves a band at each side. Nothing
         inside the viewBox is idle, which is why measuring the viewBox alone misses it. -->
    <svg id="banded" viewBox="0 0 100 200" width="400" height="100"><rect x="0" y="0" width="100" height="200"/></svg>
    <!-- One label grew into the next one's place; the pair below it is merely adjacent. -->
    <svg id="collide" viewBox="0 0 800 120" width="800" height="120">
      <text x="20" y="30" font-size="16">after routing with a commercial tool</text>
      <text x="180" y="30" font-size="16">extracted from the real path</text>
      <text x="20" y="70" font-size="16">first line of a stacked pair</text>
      <text x="20" y="88" font-size="16">second line of a stacked pair</text>
      <rect x="0" y="100" width="800" height="18" fill="none" stroke="#333"/>
      <text x="20" y="114" font-size="14">a label inside a box is normal</text>
    </svg>
    <!-- A marker parked outside the viewBox is painted where the line references it, and
         a stroke on the boundary bleeds by half its width. Neither is a cut drawing. -->
    <svg id="quiet" viewBox="0 0 400 60" width="400" height="60">
      <defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto">
        <path d="M0,0 L8,4 L0,8 z"/></marker></defs>
      <line x1="20" y1="30" x2="380" y2="30" stroke="#333" stroke-width="3" marker-end="url(#arrow)"/>
      <rect x="0" y="0" width="120" height="60" fill="none" stroke="#333" stroke-width="2"/>
    </svg>
    <p id="ordinary" style="font-size: 20px; width: 900px">This second paragraph wraps onto
      two lines as well, and its final line carries a perfectly ordinary amount of text.</p>
    <!-- One line tall, but the box set low at the end sits too far under the text for the
         rects to group as one line. Nothing here wastes a line: the block is one line. -->
    <p id="dipped" style="font-size: 15px; line-height: 1.55; width: 900px">A line that ends
      with a small box set low<span style="position: relative; top: 19px; font-size: 12px">k</span></p>
    <div id="near-pair"><div style="height: 40px">third sibling</div>
      <div id="near-second" style="height: 40px; margin-top: -6px">fourth sibling</div></div>
    <div style="height: 300px">overflow</div>
  </div>
</section></main>
</body></html>'''


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
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_browser_review_contract(tmp_path: Path) -> None:
    slides = tmp_path / "slides.html"
    report = tmp_path / "report.html"
    slides.write_text(slides_html(), encoding="utf-8")
    report.write_text(report_html(), encoding="utf-8")
    port = available_port()
    config_path = tmp_path / ".html-mcp-web.yaml"
    config_path.write_text(yaml.safe_dump({
        "artifacts": {
            "slides": {"label": "Slides", "layout": "slides", "main": "slides.html"},
            "report": {"label": "Report", "layout": "report", "main": "report.html"},
        },
        "watch": ["*.html"],
        "port": port,
    }, sort_keys=False), encoding="utf-8")

    shared = SharedProjectServer(load_config(config_path))
    profile = tempfile.mkdtemp(prefix="html_mcp_browser_")
    marionette_port = available_port()
    (Path(profile) / "user.js").write_text(
        f'user_pref("marionette.port", {marionette_port});\n',
        encoding="utf-8",
    )
    browser_process = None
    browser = None
    try:
        shared.ensure()
        browser_process = subprocess.Popen(
            ["firefox", "-marionette", "-headless", "-no-remote", "-profile", profile, "about:blank"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        browser = marionette.Marionette(host="127.0.0.1", port=marionette_port, startup_timeout=30)
        browser.start_session()
        base = f"http://127.0.0.1:{port}"
        browser.navigate(base)

        wait_until(lambda: browser.execute_script(
            'return document.querySelector("#artifact-status")?.textContent === "ready"'))
        state = get_json(f"{base}/state")
        slides_state = state["artifacts"]["slides"]
        assert slides_state["layout_check"] == {
            "checked_revision": slides_state["revision"],
            "errors": [],
            "room": {},  # nothing to answer, so no page is measured for room
        }
        assert slides_state["space_revision"] == slides_state["revision"]
        measured_page = get_json(
            f"{base}/artifacts/slides/space?revision={slides_state['revision']}&page=1&clearance=12"
        )
        target_block = next(child for child in measured_page["children"] if child["element"] == "p#target")
        assert target_block["bbox"][2] > 0
        measured_text = get_json(
            f"{base}/artifacts/slides/space?revision={slides_state['revision']}&page=1&clearance=0"
            f"&target={target_block['ref']}"
        )
        assert measured_text["kind"] == "text"
        assert measured_text["text"]["line_count"] == 1
        subscript_block = next(child for child in measured_page["children"] if child["element"] == "p#subscript")
        measured_subscript = get_json(
            f"{base}/artifacts/slides/space?revision={slides_state['revision']}&page=1&clearance=0"
            f"&target={subscript_block['ref']}"
        )
        assert measured_subscript["text"]["line_count"] == 3
        mathlike_block = next(child for child in measured_page["children"] if child["element"] == "p#mathlike")
        measured_mathlike = get_json(
            f"{base}/artifacts/slides/space?revision={slides_state['revision']}&page=1&clearance=0"
            f"&target={mathlike_block['ref']}"
        )
        assert measured_mathlike["text"]["line_count"] == 1
        assert measured_text["content_bbox"] is not None
        measured_second_page = get_json(
            f"{base}/artifacts/slides/space?revision={slides_state['revision']}&page=2&clearance=0"
        )
        table_block = next(
            child for child in measured_second_page["children"] if child["element"] == "table#metrics"
        )
        measured_table = get_json(
            f"{base}/artifacts/slides/space?revision={slides_state['revision']}&page=2&clearance=0"
            f"&target={table_block['ref']}"
        )
        assert [(cell["row"], cell["column"]) for cell in measured_table["children"]] == [(1, 1), (1, 2)]
        width_constraints = measured_table["width_constraints"]
        assert width_constraints["current_width"] == pytest.approx(400, abs=1)
        assert width_constraints["min_no_wrap_width"] < width_constraints["current_width"]
        assert width_constraints["reducible_width"] > 0
        assert width_constraints["allowed_width_range"] == [
            width_constraints["min_no_wrap_width"],
            width_constraints["current_width"],
        ]
        assert width_constraints["wrapped_cells"] == []
        assert {cell["ref"] for cell in width_constraints["constraint_cells"]}.issubset(
            {cell["ref"] for cell in measured_table["children"]}
        )
        empty_cell = measured_table["children"][1]
        measured_empty_cell = get_json(
            f"{base}/artifacts/slides/space?revision={slides_state['revision']}&page=2&clearance=0"
            f"&target={empty_cell['ref']}"
        )
        assert measured_empty_cell["content_bbox"] is None
        assert measured_empty_cell["unused_ratio"] == 1.0

        wrapped_table = next(
            child for child in measured_second_page["children"] if child["element"] == "table#wrapped"
        )
        measured_wrapped_table = get_json(
            f"{base}/artifacts/slides/space?revision={slides_state['revision']}&page=2&clearance=0"
            f"&target={wrapped_table['ref']}"
        )
        wrapped_constraints = measured_wrapped_table["width_constraints"]
        assert wrapped_constraints["min_no_wrap_width"] > wrapped_constraints["current_width"]
        assert wrapped_constraints["reducible_width"] == 0
        assert wrapped_constraints["required_expansion"] > 0
        assert wrapped_constraints["allowed_width_range"] is None
        assert wrapped_constraints["wrapped_cells"] == [measured_wrapped_table["children"][0]["ref"]]

        svg_block = next(
            child for child in measured_second_page["children"] if child["element"] == "svg#chart"
        )
        assert svg_block["kind"] == "object"
        measured_svg = get_json(
            f"{base}/artifacts/slides/space?revision={slides_state['revision']}&page=2&clearance=0"
            f"&target={svg_block['ref']}"
        )
        assert measured_svg["children"] == []
        # The drawing occupies a corner of its box, so the rest reads as free space.
        assert measured_svg["content_bbox"] != measured_svg["bbox"]
        assert 0.0 < measured_svg["unused_ratio"] < 1.0
        assert measured_svg["edge_space"]["right"] > 0
        assert measured_svg["edge_space"]["bottom"] > 0

        hidden_table = next(
            child for child in measured_second_page["children"] if child["element"] == "table#hidden"
        )
        measured_hidden_table = get_json(
            f"{base}/artifacts/slides/space?revision={slides_state['revision']}&page=2&clearance=0"
            f"&target={hidden_table['ref']}"
        )
        assert [(cell["row"], cell["column"]) for cell in measured_hidden_table["children"]] == [(1, 1), (1, 3)]
        hidden_constraints = measured_hidden_table["width_constraints"]
        assert hidden_constraints["wrapped_cells"] == []
        assert hidden_constraints["allowed_width_range"] == [
            hidden_constraints["min_no_wrap_width"],
            hidden_constraints["current_width"],
        ]
        column_widths = {
            cell["column"]: cell["min_no_wrap_width"] for cell in hidden_constraints["constraint_cells"]
        }
        assert column_widths[3] > 100

        # Tab out of the compose text has to land on Post, so Enter finishes the comment.
        browser.set_window_rect(x=0, y=0, width=1500, height=1000)
        browser.find_element("css selector", "#artifact-comment-btn").click()
        wait_until(lambda: browser.execute_script(
            'return document.querySelector("#compose-dialog").open === true'))
        assert browser.execute_script('''
          return document.activeElement === document.querySelector("#compose-text");
        ''')
        assert browser.execute_script('''
          const buttons = document.querySelectorAll("#compose-form .dialog-actions button");
          return buttons[0].id === "compose-submit" && buttons[1].id === "compose-cancel";
        ''')
        text_area = browser.find_element("css selector", "#compose-text")
        text_area.send_keys("Posted with the keyboard")
        text_area.send_keys(Keys.TAB)
        assert browser.execute_script(
            'return document.activeElement === document.querySelector("#compose-submit");')
        browser.find_element("css selector", "#compose-submit").send_keys(Keys.ENTER)
        keyboard_comment = wait_until(lambda: next(
            (comment for comment in get_json(f"{base}/artifacts/slides/comments")["comments"]
             if comment["thread"][0]["text"] == "Posted with the keyboard"), None))
        # The rest of the run expects the sidebar to hold only the anchored comment below.
        delete = urllib.request.Request(
            f"{base}/artifacts/slides/comments/{keyboard_comment['id']}", method="DELETE")
        with urllib.request.urlopen(delete, timeout=3):
            pass
        wait_until(lambda: browser.execute_script(
            'return document.querySelectorAll("[data-comment-id]").length === 0'))

        # The Scripts button hides and shows the speaker-script blocks, and the choice
        # survives a reload of the artifact.
        script_visible = ('''
          const doc = document.querySelector("#artifact-frame").contentDocument;
          const block = doc.querySelector("main.pages > .script-block");
          return block !== null && doc.defaultView.getComputedStyle(block).display !== "none";
        ''')
        wait_until(lambda: browser.execute_script('return !document.querySelector("#scripts-btn").disabled'))
        assert browser.execute_script(script_visible)
        browser.find_element("css selector", "#scripts-btn").click()
        wait_until(lambda: not browser.execute_script(script_visible))
        browser.execute_script('document.querySelector("#artifact-frame").contentWindow.location.reload();')
        time.sleep(1.5)
        wait_until(lambda: not browser.execute_script(script_visible))
        browser.find_element("css selector", "#scripts-btn").click()
        wait_until(lambda: browser.execute_script(script_visible))

        # Where the button that starts a comment came out: against the words it belongs to,
        # and against the pane that has to hold all of it.
        measure_selection_button = '''
          const pane = document.querySelector("#artifact-pane").getBoundingClientRect();
          const frame = document.querySelector("#artifact-frame").getBoundingClientRect();
          const words = document.querySelector("#artifact-frame").contentWindow
            .getSelection().getRangeAt(0).getBoundingClientRect();
          const button = document.querySelector("#selection-comment-btn").getBoundingClientRect();
          return {fromLeft: button.left - (frame.left + words.left),
                  belowWords: button.top - (frame.top + words.bottom),
                  wouldOverflow: frame.top + words.bottom + 8 + button.height > pane.bottom - 8,
                  inside: button.left >= pane.left && button.right <= pane.right
                          && button.top >= pane.top && button.bottom <= pane.bottom};
        '''

        # A phone holds a word to select it and sends no mouseup, so the selection alone
        # has to bring the button out; the words were highlighted and nothing appeared.
        browser.execute_script('''
          const frame = document.querySelector("#artifact-frame");
          const doc = frame.contentDocument;
          const view = frame.contentWindow;
          const words = doc.querySelector("#target").firstChild;
          const selection = view.getSelection();
          selection.removeAllRanges();
          const range = doc.createRange();
          range.setStart(words, 0);
          range.setEnd(words, 8);
          selection.addRange(range);          // no mouseup follows, as on a touch screen
        ''')
        wait_until(lambda: browser.execute_script(
            'return !document.querySelector("#selection-comment-btn").classList.contains("hidden")'))
        # It comes out under the words, against their left edge, where the hand that made the
        # selection already is.
        placed = browser.execute_script(measure_selection_button)
        assert abs(placed["fromLeft"]) <= 2
        assert 0 <= placed["belowWords"] <= 12
        assert placed["inside"]

        # At the bottom edge the same placement would hang the button off the pane, so it
        # goes above the words instead and stays whole.
        browser.execute_script('''
          const frame = document.querySelector("#artifact-frame");
          const doc = frame.contentDocument;
          const view = frame.contentWindow;
          const cell = doc.querySelector("#hidden td").firstChild;
          cell.parentElement.scrollIntoView({block: "end"});
          const selection = view.getSelection();
          selection.removeAllRanges();
          const range = doc.createRange();
          range.setStart(cell, 0);
          range.setEnd(cell, 5);
          selection.addRange(range);
          doc.dispatchEvent(new view.MouseEvent("mouseup", {bubbles: true}));
        ''')
        wait_until(lambda: browser.execute_script(
            'return !document.querySelector("#selection-comment-btn").classList.contains("hidden")'))
        edge = browser.execute_script(measure_selection_button)
        assert edge["wouldOverflow"]        # the words really are at the bottom of the pane
        assert edge["inside"]               # and the whole button is still on it
        assert edge["belowWords"] < 0       # because it went above them

        browser.execute_script(
            'document.querySelector("#artifact-frame").contentWindow.getSelection().removeAllRanges();')

        # A drag across a formula leaves Firefox in cell selection, one range per cell,
        # because KaTeX draws stacked parts as an inline table. The button used to want
        # exactly one range and stayed hidden; the reader had selected something either way.
        split_selection = browser.execute_script('''
          const frame = document.querySelector("#artifact-frame");
          const doc = frame.contentDocument;
          const view = frame.contentWindow;
          const words = doc.querySelector("#target").firstChild;
          const selection = view.getSelection();
          selection.removeAllRanges();
          for (const [from, to] of [[0, 3], [5, 8]]) {
            const piece = doc.createRange();
            piece.setStart(words, from);
            piece.setEnd(words, to);
            selection.addRange(piece);
          }
          doc.dispatchEvent(new view.MouseEvent("mouseup", {bubbles: true}));
          return selection.rangeCount;
        ''')
        assert split_selection == 2  # Gecko keeps both, which is what a cell drag leaves
        wait_until(lambda: browser.execute_script(
            'return !document.querySelector("#selection-comment-btn").classList.contains("hidden")'))

        # Released on the edge between two inline boxes, which a rendered formula is full
        # of, the drag leaves the element as the boundary and the offset counting its
        # children. The reader sees the selection highlighted either way.
        element_boundary = browser.execute_script('''
          const frame = document.querySelector("#artifact-frame");
          const doc = frame.contentDocument;
          const view = frame.contentWindow;
          const line = doc.querySelector("#subscript");
          const selection = view.getSelection();
          selection.removeAllRanges();
          const range = doc.createRange();
          range.setStart(line, 0);           // the element, not a text node
          range.setEnd(line.lastChild, 4);
          selection.addRange(range);
          doc.dispatchEvent(new view.MouseEvent("mouseup", {bubbles: true}));
          const found = selection.getRangeAt(0);
          return {start: found.startContainer.nodeName, quote: selection.toString().slice(0, 20)};
        ''')
        assert element_boundary["start"] == "P"  # an element boundary, as the drag leaves it
        assert element_boundary["quote"].strip()
        wait_until(lambda: browser.execute_script(
            'return !document.querySelector("#selection-comment-btn").classList.contains("hidden")'))
        wait_until(lambda: browser.execute_script(
            'return !document.querySelector("#selection-comment-btn").classList.contains("hidden")'))
        browser.execute_script(
            'document.querySelector("#artifact-frame").contentWindow.getSelection().removeAllRanges();')

        # The context stored around a selection keeps blocks apart: the cell "Used" carries
        # the heading before it in its prefix, and without the break they read as one word.
        browser.execute_script('''
          const frame = document.querySelector("#artifact-frame");
          const doc = frame.contentDocument;
          const view = frame.contentWindow;
          const cell = doc.querySelector("#metrics td").firstChild;
          const selection = view.getSelection();
          selection.removeAllRanges();
          const range = doc.createRange();
          range.setStart(cell, 0);
          range.setEnd(cell, 4);
          selection.addRange(range);
          doc.dispatchEvent(new view.MouseEvent("mouseup", {bubbles: true}));
        ''')
        wait_until(lambda: browser.execute_script(
            'return !document.querySelector("#selection-comment-btn").classList.contains("hidden")'))
        browser.find_element("css selector", "#selection-comment-btn").click()
        wait_until(lambda: browser.execute_script(
            'return document.querySelector("#compose-dialog").open === true'))
        browser.find_element("css selector", "#compose-text").send_keys("Separator check")
        browser.find_element("css selector", "#compose-submit").click()
        separated = wait_until(lambda: next(
            (comment for comment in get_json(f"{base}/artifacts/slides/comments")["comments"]
             if comment["thread"][0]["text"] == "Separator check"), None))
        stored = get_json(f"{base}/artifacts/slides/comments/{separated['id']}")
        assert stored["anchor"]["quote"] == "Used"
        assert "\n" in stored["anchor"]["prefix"]
        assert stored["anchor"]["prefix"].split("\n")[-1] == ""  # the cell starts its own block
        delete = urllib.request.Request(
            f"{base}/artifacts/slides/comments/{separated['id']}", method="DELETE")
        with urllib.request.urlopen(delete, timeout=3):
            pass
        wait_until(lambda: browser.execute_script(
            'return document.querySelectorAll(".comment-card").length === 0'))

        anchor = browser.execute_script('''
          const frame = document.querySelector("#artifact-frame");
          const doc = frame.contentDocument;
          const node = doc.querySelector("#target").firstChild;
          const path = [];
          for (let current = node; current !== doc.body; current = current.parentNode) {
            path.push(Array.prototype.indexOf.call(current.parentNode.childNodes, current));
          }
          path.reverse();
          return {path, text: node.nodeValue};
        ''')
        comment = post_json(f"{base}/artifacts/slides/comments", {
            "anchor": {
                "kind": "text",
                "quote": anchor["text"],
                "prefix": "",
                "suffix": "",
                "start": {"path": anchor["path"], "offset": 0},
                "end": {"path": anchor["path"], "offset": len(anchor["text"])},
                "artifact_digest": slides_state["artifact_digest"],
            },
            "text": "Keep this attached",
        })
        wait_until(lambda: browser.execute_script(
            'return document.querySelectorAll(".comment-card").length === 1'))
        wait_until(lambda: browser.execute_script('''
          return document.querySelector("#artifact-frame").contentDocument
            .querySelectorAll(".html-mcp-highlight").length > 0;
        '''))

        browser.execute_script(f'''
          document.querySelector("[data-comment-id=\\"{comment["id"]}\\"] .comment-summary").click();
          const card = document.querySelector("[data-comment-id=\\"{comment["id"]}\\"]");
          Array.from(card.querySelectorAll("button")).find((button) => button.textContent === "Reply").click();
          const input = document.querySelector("[data-comment-id=\\"{comment["id"]}\\"] .comment-form-input");
          input.value = "Preserved draft";
          input.dispatchEvent(new Event("input", {{bubbles: true}}));
          input.focus();
        ''')

        slides.write_text(slides_html("Before Selected sentence. After"), encoding="utf-8")
        wait_until(lambda: get_json(f"{base}/state")["artifacts"]["slides"]["revision"] > slides_state["revision"])
        wait_until(lambda: browser.execute_script('''
          return document.querySelector("#artifact-frame").contentDocument
            .querySelectorAll(".html-mcp-highlight").length > 0;
        '''))
        assert not browser.execute_script(
            f'return document.querySelector("[data-comment-id=\\"{comment["id"]}\\"]").classList.contains("unattached")')
        assert browser.execute_script(f'''
          const input = document.querySelector("[data-comment-id=\\"{comment["id"]}\\"] .comment-form-input");
          return input?.value === "Preserved draft" && document.activeElement === input;
        ''')

        browser.find_element("css selector", "#fullscreen-btn").click()
        wait_until(lambda: browser.execute_script('return document.fullscreenElement !== null'))
        wait_until(lambda: browser.execute_script(
            'return document.querySelector("#presentation-page").textContent === "1 / 2"'))
        assert browser.execute_script('''
          const frame = document.querySelector("#artifact-frame");
          const layer = frame.contentDocument.querySelector(".html-mcp-highlight-layer");
          return layer !== null && frame.contentWindow.getComputedStyle(layer).display === "none";
        ''')
        browser.execute_script('''
          const frame = document.querySelector("#artifact-frame");
          frame.contentDocument.dispatchEvent(new frame.contentWindow.WheelEvent("wheel", {
            deltaY: 20, bubbles: true, cancelable: true
          }));
        ''')
        wait_until(lambda: browser.execute_script(
            'return document.querySelector("#presentation-page").textContent === "2 / 2"'))
        browser.execute_script('document.exitFullscreen(); return true;')
        wait_until(lambda: browser.execute_script('return document.fullscreenElement === null'))

        slides.write_text(problem_html(), encoding="utf-8")
        changed_revision = wait_until(
            lambda: get_json(f"{base}/state")["artifacts"]["slides"]["revision"] > slides_state["revision"] + 1
            and get_json(f"{base}/state")["artifacts"]["slides"]["revision"])
        errors = wait_until(lambda: (
            get_json(f"{base}/state")["artifacts"]["slides"]["layout_check"]["errors"]
            if get_json(f"{base}/state")["artifacts"]["slides"]["layout_check"]["checked_revision"] == changed_revision
            else None
        ))
        assert any("overflows its content area" in error for error in errors)
        # The page that spills is measured for room, so the answer to an overflow can be a
        # move rather than a cut.
        assert "1" in get_json(f"{base}/state")["artifacts"]["slides"]["layout_check"]["room"]
        # The block is named by what the slide shows. KaTeX's hidden MathML copy holds the
        # TeX source, and taking it along named a bullet after markup its writer cannot find.
        tail_error = next(error for error in errors if "wastes its last line" in error)
        assert "overline" not in tail_error
        assert "A deliberately long" in tail_error
        # The error itself says which block and by how much, so the fix needs no
        # drill-down first and no second round to learn the amount.
        assert re.search(r"on a \d+px tail", tail_error)
        assert re.search(r"\[p1:\d+(\.\d+)*\]$", tail_error)
        cut_error = next(error for error in errors if "svg#cut>" in error)
        assert re.search(r"\[p1:\d+(\.\d+)*\]$", cut_error)
        assert any("overlaps its sibling" in error for error in errors)
        assert any("div#near-second" in error for error in errors)
        assert not any("This second paragraph" in error for error in errors)
        assert not any("p#dipped" in error or "A line that ends" in error for error in errors)
        assert any("svg#cut> draws outside its viewBox and is cut off (bottom by 10)" in error
                   for error in errors)
        assert not any("svg#quiet" in error for error in errors)
        assert any("svg#idle> reserves space it does not draw in (right 51%" in error
                   for error in errors)
        banded = next(error for error in errors if "svg#banded" in error)
        assert "reserves space it does not draw in" in banded
        assert "left 44%" in banded and "right 44%" in banded
        assert not any("svg#cut> reserves" in error for error in errors)
        collisions = [error for error in errors if "prints two labels over each other" in error]
        assert len(collisions) == 1
        assert "after routing with a commercia" in collisions[0]
        assert "extracted from the real path" in collisions[0]

        # The page is zoomed to fit the pane, so a narrower window must not change
        # which layout problems are reported.
        wide_scale = browser.execute_script(
            'return document.querySelector("#artifact-frame").contentDocument'
            '.documentElement.style.getPropertyValue("--html-mcp-page-scale");')
        browser.set_window_rect(x=0, y=0, width=700, height=900)
        wait_until(lambda: browser.execute_script(
            'return document.querySelector("#artifact-frame").contentDocument'
            '.documentElement.style.getPropertyValue("--html-mcp-page-scale");') != wide_scale)
        slides.write_text(problem_html(), encoding="utf-8")
        narrow_revision = wait_until(
            lambda: get_json(f"{base}/state")["artifacts"]["slides"]["revision"] > changed_revision
            and get_json(f"{base}/state")["artifacts"]["slides"]["revision"])
        narrow_errors = wait_until(lambda: (
            get_json(f"{base}/state")["artifacts"]["slides"]["layout_check"]["errors"]
            if get_json(f"{base}/state")["artifacts"]["slides"]["layout_check"]["checked_revision"] == narrow_revision
            else None
        ))
        # Zoomed text wraps at slightly different line heights, so the overflow amount
        # moves by a few pixels; the set of reported problems is what must hold.
        def without_amounts(messages: list[str]) -> list[str]:
            return sorted(re.sub(r"\d+px", "Npx", message) for message in messages)

        assert without_amounts(narrow_errors) == without_amounts(errors)
        assert any("div#near-second" in error for error in narrow_errors)
        assert not any("This second paragraph" in error for error in narrow_errors)
        browser.set_window_rect(x=0, y=0, width=1400, height=1000)
        assert browser.execute_script('return document.querySelector("#print-btn").disabled === false')
        wait_until(lambda: browser.execute_script(
            f'return document.querySelector("[data-comment-id=\\"{comment["id"]}\\"] .stale-pill") !== null'))

        assert browser.execute_script('return document.title') == "slides.html"
        browser.find_element("css selector", '.artifact-tab:nth-child(2)').click()
        wait_until(lambda: browser.execute_script(
            'return document.querySelector("#main-file").textContent === "report.html"'))
        assert browser.execute_script('return document.title') == "report.html"
        browser.find_element("css selector", "#fullscreen-btn").click()
        wait_until(lambda: browser.execute_script('return document.fullscreenElement !== null'))
        assert browser.execute_script('''
          const root = document.querySelector("#artifact-frame").contentDocument.documentElement;
          return !root.hasAttribute("data-html-mcp-presentation");
        ''')
        browser.execute_script('document.querySelector("#artifact-frame").contentWindow.scrollTo(0, 1000)')
        assert wait_until(lambda: browser.execute_script(
            'return document.querySelector("#artifact-frame").contentWindow.scrollY > 0'))
        browser.execute_script('document.exitFullscreen(); return true;')
        wait_until(lambda: browser.execute_script('return document.fullscreenElement === null'))

        browser.find_element("css selector", '.artifact-tab:nth-child(1)').click()
        wait_until(lambda: browser.execute_script(
            'return document.querySelectorAll("[data-comment-id]").length === 1'))

        browser.execute_script(f'''
          const card = Array.from(document.querySelectorAll("[data-comment-id]"))
            .find((node) => node.dataset.commentId === "{comment["id"]}");
          if (card.querySelector(".thread-entry") === null) card.querySelector(".comment-summary").click();
        ''')
        wait_until(lambda: browser.execute_script(
            f'return document.querySelector("[data-comment-id=\\"{comment["id"]}\\"] .thread-meta .link") !== null'))
        browser.execute_script(f'''
          const findCard = () => Array.from(document.querySelectorAll("[data-comment-id]"))
            .find((node) => node.dataset.commentId === "{comment["id"]}");
          findCard().querySelector(".thread-meta .link").click();
          // The click re-renders the card, so the editor is looked up on the new node.
          const card = findCard();
          const input = card.querySelector(".entry-edit-input");
          input.value = "Edited in the browser";
          input.dispatchEvent(new Event("input", {{bubbles: true}}));
          Array.from(card.querySelectorAll("button")).find((button) => button.textContent === "Save").click();
        ''')
        wait_until(lambda: get_json(f"{base}/artifacts/slides/comments/{comment['id']}")
                   ["thread"][0]["text"] == "Edited in the browser")
        assert len(get_json(f"{base}/artifacts/slides/comments/{comment['id']}")["thread"]) == 1
        browser.execute_script(f'''
          const findCard = () => Array.from(document.querySelectorAll("[data-comment-id]"))
            .find((node) => node.dataset.commentId === "{comment["id"]}");
          const resolveButton = (card) => Array.from(card.querySelectorAll("button"))
            .find((button) => button.textContent === "Resolve");
          let card = findCard();
          if (resolveButton(card) === undefined) {{
            card.querySelector(".comment-summary").click();
            card = findCard();
          }}
          resolveButton(card).click();
        ''')
        wait_until(lambda: get_json(f"{base}/artifacts/slides/comments/{comment['id']}")["status"] == "resolved")
        assert len(get_json(f"{base}/artifacts/slides/comments/{comment['id']}")["thread"]) == 1


        config_path.write_text(yaml.safe_dump({
            "artifacts": {
                "slides": {"label": "Updated Slides", "layout": "slides", "main": "slides.html"},
                "report": {"label": "Updated Report", "layout": "report", "main": "report.html"},
            },
            "watch": ["*.html"],
            "port": port,
        }, sort_keys=False), encoding="utf-8")
        wait_until(lambda: browser.execute_script('''
          return Array.from(document.querySelectorAll(".artifact-tab"))
            .map((tab) => tab.textContent).join("|") === "Updated Slides|Updated Report";
        '''))

        # Resolve all closes the whole open queue at once, which is how the reviewer signs
        # off a batch the agent answered and deliberately left open. The first press asks
        # in the label and changes nothing; the second one closes them.
        browser.find_element("css selector", '.artifact-tab:nth-child(1)').click()
        wait_until(lambda: browser.execute_script(
            'return document.querySelector("#main-file").textContent === "slides.html"'))
        for note in ("First of the batch", "Second of the batch"):
            post_json(f"{base}/artifacts/slides/comments",
                      {"anchor": {"kind": "artifact"}, "text": note})
        still_open = get_json(f"{base}/artifacts/slides/comments?status=open")["comments"]
        assert len(still_open) == 2
        asking = f"Resolve {len(still_open)}?"
        browser.find_element("css selector", "#resolve-open-btn").click()
        wait_until(lambda: browser.execute_script(
            'return document.querySelector("#resolve-open-btn").textContent') == asking)
        assert get_json(f"{base}/artifacts/slides/comments?status=open")["comments"] == still_open
        browser.find_element("css selector", "#resolve-open-btn").click()
        wait_until(lambda: not get_json(f"{base}/artifacts/slides/comments?status=open")["comments"])
        closed = get_json(f"{base}/artifacts/slides/comments/{still_open[0]['id']}")
        assert closed["status"] == "resolved"
        assert closed["thread"][-1]["author"] == "human"   # the reviewer closed it, not the agent
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


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_display_math_matches_its_paragraph(tmp_path: Path) -> None:
    """KaTeX enlarges maths to 1.21em. That suits inline maths in a line of text, but a
    display equation standing alone then overpowers the body, so it takes the paragraph's
    size. KaTeX's own stylesheet is written after the skeleton, so the rule only holds if
    the skeleton's selector outweighs it."""
    from html_mcp_web.slides import build

    content = tmp_path / "content.html"
    content.write_text(
        '<!doctype html>\n<meta charset="utf-8">\n<title>Math</title>\n'
        '<body data-author="A" data-meta="B">\n'
        '<section data-title="Math"><p>Inline $a^2$ here.</p><p>$$b^2 + c^2$$</p></section>\n'
        "</body>\n", encoding="utf-8")
    html = tmp_path / "slides.html"
    build(content, html, Path(__file__).resolve().parents[1] / "templates" / "neutral-slides")

    profile = tempfile.mkdtemp(prefix="html_mcp_math_")
    marionette_port = available_port()
    (Path(profile) / "user.js").write_text(
        f'user_pref("marionette.port", {marionette_port});\n', encoding="utf-8")
    browser_process = None
    browser = None
    try:
        browser_process = subprocess.Popen(
            ["firefox", "-marionette", "-headless", "-no-remote", "-profile", profile, "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        browser = marionette.Marionette(host="127.0.0.1", port=marionette_port, startup_timeout=30)
        browser.start_session()
        browser.navigate(html.as_uri())
        wait_until(lambda: browser.execute_script(
            "return !!document.querySelector('.katex-display > .katex')"))
        sizes = browser.execute_script("""
const page = document.querySelectorAll('section.page')[1];
const size = (el) => parseFloat(getComputedStyle(el).fontSize);
return {paragraph: size(page.querySelector('p')),
        inline: size(page.querySelector('p .katex')),
        display: size(page.querySelector('.katex-display > .katex'))};
""")
        assert abs(sizes["display"] - sizes["paragraph"]) < 0.5
        assert sizes["inline"] > sizes["paragraph"] + 1  # inline keeps KaTeX's enlargement
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


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_a_narrow_screen_puts_the_comments_under_the_artifact(tmp_path: Path) -> None:
    """Side by side, a phone left the artifact 150px of a 450px screen and pushed the row of
    controls past the right edge, the control that hides the comments among them. A phone is
    long rather than wide, so the comments belong under the artifact."""
    slides = tmp_path / "slides.html"
    slides.write_text(slides_html(), encoding="utf-8")
    port = available_port()
    config_path = tmp_path / ".html-mcp-web.yaml"
    config_path.write_text(yaml.safe_dump({
        "artifacts": {"slides": {"label": "Slides", "layout": "slides", "main": "slides.html"}},
        "watch": ["*.html"],
        "port": port,
    }, sort_keys=False), encoding="utf-8")

    shared = SharedProjectServer(load_config(config_path))
    profile = tempfile.mkdtemp(prefix="html_mcp_phone_")
    marionette_port = available_port()
    (Path(profile) / "user.js").write_text(
        f'user_pref("marionette.port", {marionette_port});\n', encoding="utf-8")
    browser_process = None
    browser = None
    try:
        shared.ensure()
        browser_process = subprocess.Popen(
            ["firefox", "-marionette", "-headless", "-no-remote", "-profile", profile,
             "-width", "420", "-height", "800", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        browser = marionette.Marionette(host="127.0.0.1", port=marionette_port, startup_timeout=30)
        browser.start_session()
        browser.set_window_rect(width=420, height=800)
        browser.navigate(f"http://127.0.0.1:{port}")
        wait_until(lambda: browser.execute_script(
            'return document.querySelector("#artifact-status")?.textContent === "ready"'))
        measured = browser.execute_script('''
          const pane = document.querySelector("#artifact-pane").getBoundingClientRect();
          const toggle = document.querySelector("#sidebar-toggle-btn").getBoundingClientRect();
          const bar = document.querySelector(".topbar");
          return {width: window.innerWidth, height: window.innerHeight,
                  paneWidth: pane.width, paneBottom: pane.bottom,
                  toggleRight: toggle.right, barOverflow: bar.scrollWidth - bar.clientWidth,
                  collapsed: document.querySelector(".layout").classList.contains("sidebar-collapsed")};
        ''')
        assert measured["paneWidth"] >= measured["width"] - 2   # the artifact has the screen
        assert measured["toggleRight"] <= measured["width"]     # and the control is reachable
        assert measured["barOverflow"] <= 1                     # nothing runs off the row
        assert measured["collapsed"]                            # comments wait to be asked for

        browser.find_element("css selector", "#sidebar-toggle-btn").click()
        opened = browser.execute_script('''
          const pane = document.querySelector("#artifact-pane").getBoundingClientRect();
          const side = document.querySelector("#sidebar").getBoundingClientRect();
          return {paneWidth: pane.width, paneBottom: pane.bottom,
                  sideTop: side.top, sideWidth: side.width, sideHeight: side.height};
        ''')
        assert opened["sideHeight"] > 50                        # the comments are on screen
        assert opened["sideTop"] >= opened["paneBottom"] - 2    # under the artifact, not over it
        assert opened["paneWidth"] >= measured["width"] - 2     # which keeps the whole width

        # The bar along the top of the comments drags the split, so either side can be given
        # the screen without the other going away.
        grip = browser.find_element("css selector", "#sidebar-grip")
        box = browser.execute_script(
            'const r = document.querySelector("#sidebar-grip").getBoundingClientRect();'
            'return {x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2)};')
        drag = browser.actions.sequence("pointer", "mouse", {"pointerType": "mouse"})
        drag.pointer_move(box["x"], box["y"]).pointer_down()
        for step in range(1, 5):
            drag.pointer_move(box["x"], box["y"] - 30 * step, duration=30)
        drag.pointer_up().perform()
        dragged = browser.execute_script('''
          const pane = document.querySelector("#artifact-pane").getBoundingClientRect();
          const side = document.querySelector("#sidebar").getBoundingClientRect();
          return {paneHeight: pane.height, sideHeight: side.height};
        ''')
        assert dragged["sideHeight"] > opened["sideHeight"] + 40   # dragged up, so it grew
        assert dragged["paneHeight"] > 80                          # and the artifact is still there
        # The height is written once the drag ends, not on every move it passes through.
        kept = browser.execute_script(
            'return {stored: Number(localStorage.getItem("htmlMcpPanelHeight")),'
            ' height: document.querySelector("#sidebar").getBoundingClientRect().height};')
        assert abs(kept["stored"] - kept["height"]) <= 2

        # A tablet held upright has width to spare and still reads better with the comments
        # below, so the split follows the shape of the screen rather than its width.
        browser.set_window_rect(width=820, height=1200)
        wait_until(lambda: browser.execute_script("return window.innerWidth > 700"))
        upright = browser.execute_script('''
          const pane = document.querySelector("#artifact-pane").getBoundingClientRect();
          const side = document.querySelector("#sidebar").getBoundingClientRect();
          return {width: window.innerWidth, paneWidth: pane.width, paneBottom: pane.bottom,
                  sideTop: side.top, sideWidth: side.width};
        ''')
        assert upright["paneWidth"] >= upright["width"] - 2
        assert upright["sideTop"] >= upright["paneBottom"] - 2

        # A phone that enlarges text on its own doubled the labels inside the drawings while
        # the drawings kept their size, which put the numbers off the wires they name. The
        # page is drawn at one size and asks to keep it, down to the text in an svg.
        adjust = browser.execute_script('''
          const doc = document.querySelector("#artifact-frame").contentDocument;
          const label = doc.querySelector("svg#chart text");
          const read = (el) => getComputedStyle(el).getPropertyValue("-webkit-text-size-adjust");
          return {root: read(doc.documentElement), label: label ? read(label) : null};
        ''')
        assert adjust["root"] == "none"
        assert adjust["label"] == "none"
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


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_space_is_measured_with_no_review_ui_open(tmp_path: Path) -> None:
    """A headless session has nobody's browser on the page, and every measurement 409'd
    until someone opened the UI. The server runs the check itself: the same page scripts,
    in a browser of its own."""
    slides = tmp_path / "slides.html"
    slides.write_text(slides_html(), encoding="utf-8")
    port = available_port()
    config_path = tmp_path / ".html-mcp-web.yaml"
    config_path.write_text(yaml.safe_dump({
        "artifacts": {"slides": {"label": "Slides", "layout": "slides", "main": "slides.html"}},
        "watch": ["*.html"],
        "port": port,
    }, sort_keys=False), encoding="utf-8")
    shared = SharedProjectServer(load_config(config_path))
    try:
        shared.ensure()
        base = f"http://127.0.0.1:{port}"
        state = get_json(f"{base}/state")["artifacts"]["slides"]
        assert state["layout_check"]["checked_revision"] is None   # nobody has looked yet
        with urllib.request.urlopen(f"{base}/artifacts/slides/space?page=1&clearance=0", timeout=75) as reply:
            measured = json.loads(reply.read().decode("utf-8"))
        assert measured["revision"] == state["revision"]
        assert measured["children"]                    # the page's blocks were measured
        checked = get_json(f"{base}/state")["artifacts"]["slides"]["layout_check"]
        assert checked["checked_revision"] == state["revision"]   # the check really ran
        assert checked["errors"] == []                            # and this deck is clean
    finally:
        shared.stop()


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_a_built_deck_keeps_its_page_size_when_opened_as_a_file(tmp_path: Path) -> None:
    """Nothing in the file stated the page size: the viewer imposed it. Opened on its own
    a page was a plain block, taking the window's width while its height stayed with its
    content, so the slide came out stretched sideways. The deck now carries its size, and
    a window too narrow for it shrinks the page whole rather than squashing it."""
    from html_mcp_web.slides import build

    content = tmp_path / "content.html"
    content.write_text(
        '<!doctype html><meta charset="utf-8"><title>Deck</title>'
        '<body data-author="A" data-meta="B">'
        '<section data-title="One"><p>Only page.</p></section></body>', encoding="utf-8")
    html = tmp_path / "slides.html"
    build(content, html, Path(__file__).resolve().parents[1] / "templates" / "neutral-slides")

    profile = tempfile.mkdtemp(prefix="html_mcp_standalone_")
    marionette_port = available_port()
    (Path(profile) / "user.js").write_text(
        f'user_pref("marionette.port", {marionette_port});\n', encoding="utf-8")
    browser_process = None
    browser = None
    try:
        browser_process = subprocess.Popen(
            ["firefox", "-marionette", "-headless", "-no-remote", "-profile", profile,
             "-width", "1400", "-height", "900", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        browser = marionette.Marionette(host="127.0.0.1", port=marionette_port, startup_timeout=30)
        browser.start_session()
        browser.set_window_rect(width=1400, height=900)
        browser.navigate(html.as_uri())
        wait_until(lambda: browser.execute_script(
            "return !!document.querySelector('section.page')"))
        measure = """
const box = document.querySelector('section.page').getBoundingClientRect();
return [Math.round(box.width), Math.round(box.height)];
"""
        assert browser.execute_script(measure) == [1280, 720]

        # Narrower than the page: the whole slide shrinks, keeping its shape.
        browser.set_window_rect(width=900, height=900)
        narrow = wait_until(lambda: (
            browser.execute_script(measure)
            if browser.execute_script(measure)[0] < 1280 else None))
        assert narrow[0] <= 900
        assert abs(narrow[0] / narrow[1] - 1280 / 720) < 0.01
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


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_a_body_image_keeps_its_proportions(tmp_path: Path) -> None:
    """The body is a column flex box, and its default stretch handed an image with no
    stated width the whole column while max-height cut only the height: a 4:3 figure came
    out at 4:1. An image wider than the column is held inside it instead."""
    from PIL import Image

    from html_mcp_web.slides import build

    (tmp_path / "fig").mkdir()
    Image.new("RGB", (400, 300), "#3366aa").save(tmp_path / "fig" / "small.png")
    Image.new("RGB", (2400, 600), "#aa3333").save(tmp_path / "fig" / "huge.png")
    content = tmp_path / "content.html"
    content.write_text(
        '<!doctype html><meta charset="utf-8"><title>Deck</title>'
        '<body data-author="A" data-meta="B">'
        '<section data-title="Figures"><p class="lead">Two figures.</p>'
        '<img id="small" src="fig/small.png" style="max-height:300px">'
        '<img id="huge" src="fig/huge.png" style="max-height:300px"></section></body>',
        encoding="utf-8")
    html = tmp_path / "slides.html"
    build(content, html, Path(__file__).resolve().parents[1] / "templates" / "neutral-slides")

    profile = tempfile.mkdtemp(prefix="html_mcp_img_")
    marionette_port = available_port()
    (Path(profile) / "user.js").write_text(
        f'user_pref("marionette.port", {marionette_port});\n', encoding="utf-8")
    browser_process = None
    browser = None
    try:
        browser_process = subprocess.Popen(
            ["firefox", "-marionette", "-headless", "-no-remote", "-profile", profile,
             "-width", "1500", "-height", "1000", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        browser = marionette.Marionette(host="127.0.0.1", port=marionette_port, startup_timeout=30)
        browser.start_session()
        browser.set_window_rect(width=1500, height=1000)
        browser.navigate(html.as_uri())
        wait_until(lambda: browser.execute_script(
            "const i = document.querySelector('#small'); return i !== null && i.complete"))
        measured = browser.execute_script("""
const read = (id) => {
  const image = document.querySelector(id);
  const box = image.getBoundingClientRect();
  return {drawn: [Math.round(box.width), Math.round(box.height)],
          source: image.naturalWidth / image.naturalHeight,
          shown: box.width / box.height,
          column: Math.round(image.parentElement.getBoundingClientRect().width)};
};
return {small: read('#small'), huge: read('#huge')};
""")
        for name in ("small", "huge"):
            one = measured[name]
            assert abs(one["shown"] - one["source"]) < 0.02, name   # proportions survive
            assert one["drawn"][0] <= one["column"], name           # and stay in the column
        assert measured["small"]["drawn"] == [400, 300]             # small enough to sit as it is
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


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_a_selection_inside_an_svg_is_marked_where_its_letters_are(tmp_path: Path) -> None:
    """A Range inside an svg does not report the characters it holds: nine letters of a
    label gave the whole element's box, and a selection starting mid-label gave an empty
    rect. The highlight then covered the whole label and the comment button sat away from
    what was grabbed, which is what a finger on a pad hits every time."""
    slides = tmp_path / "slides.html"
    slides.write_text(slides_html(), encoding="utf-8")
    port = available_port()
    config_path = tmp_path / ".html-mcp-web.yaml"
    config_path.write_text(yaml.safe_dump({
        "artifacts": {"slides": {"label": "Slides", "layout": "slides", "main": "slides.html"}},
        "watch": ["*.html"],
        "port": port,
    }, sort_keys=False), encoding="utf-8")
    shared = SharedProjectServer(load_config(config_path))
    profile = tempfile.mkdtemp(prefix="html_mcp_svgsel_")
    marionette_port = available_port()
    (Path(profile) / "user.js").write_text(
        f'user_pref("marionette.port", {marionette_port});\n', encoding="utf-8")
    browser_process = None
    browser = None
    try:
        shared.ensure()
        browser_process = subprocess.Popen(
            ["firefox", "-marionette", "-headless", "-no-remote", "-profile", profile,
             "-width", "1400", "-height", "1000", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        browser = marionette.Marionette(host="127.0.0.1", port=marionette_port, startup_timeout=30)
        browser.start_session()
        browser.set_window_rect(width=1400, height=1000)
        browser.navigate(f"http://127.0.0.1:{port}")
        wait_until(lambda: browser.execute_script(
            'return document.querySelector("#artifact-status")?.textContent === "ready"'))
        wait_until(lambda: browser.execute_script(
            'const d = document.querySelector("#artifact-frame").contentDocument;'
            'return d !== null && d.querySelector("#svg-words") !== null'))

        # Grab five letters from the middle of the label, the way a long press does.
        measured = browser.execute_script('''
          const frame = document.querySelector("#artifact-frame");
          const doc = frame.contentDocument;
          const view = frame.contentWindow;
          const label = doc.querySelector("#svg-words");
          const selection = view.getSelection();
          selection.removeAllRanges();
          const range = doc.createRange();
          range.setStart(label.firstChild, 5);
          range.setEnd(label.firstChild, 10);
          selection.addRange(range);
          doc.dispatchEvent(new view.MouseEvent("mouseup", {bubbles: true}));
          const ctm = label.getScreenCTM();
          const first = label.getExtentOfChar(5);
          const last = label.getExtentOfChar(9);
          const at = (x, y) => [ctm.a * x + ctm.c * y + ctm.e, ctm.b * x + ctm.d * y + ctm.f];
          const topLeft = at(first.x, first.y);
          const bottomRight = at(last.x + last.width, last.y + last.height);
          const whole = label.getBoundingClientRect();
          return {letters: [topLeft[0], topLeft[1], bottomRight[0] - topLeft[0], bottomRight[1] - topLeft[1]],
                  whole: [whole.left, whole.top, whole.width, whole.height],
                  frame: (() => { const r = frame.getBoundingClientRect(); return [r.left, r.top]; })()};
        ''')
        letters = measured["letters"]
        assert letters[2] < measured["whole"][2] / 2   # the grab is a fraction of the label

        # The highlight covers those letters, not the label.
        wait_until(lambda: browser.execute_script(
            'const d = document.querySelector("#artifact-frame").contentDocument;'
            'return d.querySelectorAll(".html-mcp-highlight").length === 0'))
        wait_until(lambda: browser.execute_script(
            'return !document.querySelector("#selection-comment-btn").classList.contains("hidden")'))
        browser.find_element("css selector", "#selection-comment-btn").click()
        wait_until(lambda: browser.execute_script(
            'return document.querySelector("#compose-dialog").open === true'))
        browser.find_element("css selector", "#compose-text").send_keys("Inside the svg")
        browser.find_element("css selector", "#compose-submit").click()
        wait_until(lambda: browser.execute_script(
            'const d = document.querySelector("#artifact-frame").contentDocument;'
            'return d.querySelectorAll(".html-mcp-highlight").length > 0'))
        mark = browser.execute_script('''
          const frame = document.querySelector("#artifact-frame");
          const box = frame.contentDocument.querySelector(".html-mcp-highlight").getBoundingClientRect();
          const r = frame.getBoundingClientRect();
          return [box.left - r.left, box.top - r.top, box.width, box.height];
        ''')
        letters_in_frame = [letters[0] - measured["frame"][0], letters[1] - measured["frame"][1],
                            letters[2], letters[3]]
        for drawn, truth in zip(mark, letters_in_frame):
            assert abs(drawn - truth) <= 3, (mark, letters_in_frame)
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
