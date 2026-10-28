import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

marionette = pytest.importorskip("marionette_driver.marionette")

REPO = Path(__file__).resolve().parents[1]
BUILDER = REPO / "templates" / "neutral-report" / "build.py"

SENTENCE = ("The router scores every block of keys against the query and keeps the few it "
            "needs, and attention reads only those, so the cost follows the context. ")


def content_html() -> str:
    paragraphs = "\n".join(f"<p>{index} {SENTENCE * 5}</p>" for index in range(1, 23))
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Long Text</title>
<body data-author="Author" data-meta="Place">
<section data-title="Abstract" data-abstract><p>{SENTENCE * 3}</p></section>
<section data-title="Method">
{paragraphs}
<figure><svg viewBox="0 0 240 200" width="240" height="200"><rect width="240" height="200" fill="#ccc"/></svg><figcaption>A tall drawing.</figcaption></figure>
<ul><li>{SENTENCE}</li><li>{SENTENCE}</li><li>{SENTENCE}</li></ul>
{paragraphs}
</section>
</body>
"""


def run_in_report(tmp_path: Path, html: str, script: str, skin: Path | None = None) -> dict:
    """Build html with the neutral report skin, or with skin, open it in Firefox once its
    fonts are in, and return what script returns."""
    content = tmp_path / "content.html"
    content.write_text(html, encoding="utf-8")
    report = tmp_path / "report.html"
    command = ([sys.executable, str(BUILDER), str(content), str(report)] if skin is None else
               [sys.executable, "-c", "import sys; from pathlib import Path; from html_mcp_web.report import build; "
                "build(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))", str(content), str(report), str(skin)])
    # The PATH of the run, where the Firefox the tests use is found, since the build sets the
    # pages in Firefox.
    subprocess.run(command, check=True, capture_output=True, env={"PYTHONPATH": str(REPO), "PATH": os.environ["PATH"]})

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    profile = tempfile.mkdtemp(prefix="report_test_")
    Path(profile, "user.js").write_text(f'user_pref("marionette.port", {port});\n', encoding="utf-8")
    process = subprocess.Popen(["firefox", "-marionette", "-headless", "-no-remote", "-profile", profile,
                                "-width", "1200", "-height", "900", "about:blank"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        browser = marionette.Marionette(host="127.0.0.1", port=port, startup_timeout=60)
        browser.start_session()
        browser.navigate(report.as_uri())
        for _ in range(50):
            if browser.execute_script("return document.fonts.status === 'loaded'"):
                break
            time.sleep(0.2)
        time.sleep(0.5)
        return browser.execute_script(script)
    finally:
        process.kill()


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_the_text_runs_on_across_columns_and_pages_whole(tmp_path: Path) -> None:
    """The flow is poured into two columns a page: nothing runs past the foot of a column,
    a paragraph cut at a foot goes on at the head of the next column with not a letter lost
    or doubled, and a figure moves whole."""
    result = run_in_report(tmp_path, content_html(), """
const pages = Array.from(document.querySelectorAll('main.pages > section.page'));
const overflow = [];
for (const column of document.querySelectorAll('.column')) {
  const foot = column.getBoundingClientRect().bottom + 0.5;
  for (const child of column.children) {
    if (child.getBoundingClientRect().bottom > foot && column.children.length > 1) overflow.push(child.textContent.slice(0, 30));
  }
}
const paragraphs = Array.from(document.querySelectorAll('.column > p'));
const joined = [];
for (const p of paragraphs) {
  // A word cut at a foot carries a hyphen on its first part, which is not in the text.
  if (p.classList.contains('cont')) joined[joined.length - 1] = joined[joined.length - 1].replace(/\\u2010$/, '') + p.textContent;
  else joined.push(p.textContent);
}
return {
  pages: pages.length,
  columns: pages.map((page) => page.querySelectorAll('.column').length),
  overflow,
  split: document.querySelectorAll('p.split').length,
  texts: joined,
  figures: Array.from(document.querySelectorAll('.column > figure')).map((f) => f.querySelector('svg') !== null && f.querySelector('figcaption') !== null),
  items: document.querySelectorAll('.column li').length,
  flowLeft: document.getElementById('report-flow').children.length,
};""")

    assert result["pages"] >= 3
    assert all(count == 2 for count in result["columns"])
    assert result["overflow"] == []
    assert result["split"] > 0
    expected = [f"{SENTENCE * 3}"] + [f"{index} {SENTENCE * 5}" for index in range(1, 23)] * 2
    assert [text.strip() for text in result["texts"]] == [text.strip() for text in expected]
    assert result["figures"] == [True]
    assert result["items"] >= 3
    assert result["flowLeft"] == 0


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_tables_share_their_width_and_wide_figures_leave_room(tmp_path: Path) -> None:
    """A first row of th becomes the table's head. A column of short labels keeps each
    label on one line beside a column of longer text. Wide figures waiting for a
    page stack at its top only to 0.7 of it, and no column overflows."""
    work = ["teacher data, NLL selection, math proxy", "anchor KL, layer selection, combination, efficiency",
            "proxy dev, reference tools, held-out checks"]
    rows = "".join(f"<tr><td>{role}</td><td>TODO {n}-{n + 4}</td><td>{text}</td></tr>"
                   for role, n, text in zip("ABC", (1, 6, 11), work))
    wide = "".join(f'<figure class="wide"><svg viewBox="0 0 500 300" width="500" height="300">'
                   f'<rect width="500" height="300" fill="#ccc"/></svg><figcaption>Wide {n}.</figcaption></figure>'
                   for n in range(3))
    table = f"<figure><table><tr><th>Role</th><th>Part 1</th><th>Part 2</th></tr>{rows}</table><figcaption>Work.</figcaption></figure>"
    # Korean text breaks only between words, the case in which the browser left the short
    # column too narrow for its labels.
    html = content_html().replace("<ul>", table + wide + "<ul>", 1).replace("<body ", '<body data-lang="ko" ', 1)
    result = run_in_report(tmp_path, html, """
const table = document.querySelector('.column table');
const overflow = [];
for (const column of document.querySelectorAll('.column')) {
  const foot = column.getBoundingClientRect().bottom + 0.5;
  for (const child of column.children) {
    if (child.getBoundingClientRect().bottom > foot && column.children.length > 1) overflow.push(child.textContent.slice(0, 30));
  }
}
const line = parseFloat(getComputedStyle(table).lineHeight);
return {
  head: table.tHead !== null && table.tHead.rows.length === 1,
  labels: Array.from(table.tBodies[0].rows).map((row) => {
    const range = document.createRange();
    range.selectNodeContents(row.cells[1]);
    return range.getBoundingClientRect().height < line * 1.5;
  }),
  tops: Array.from(document.querySelectorAll('.page')).map((page) => [
    page.querySelectorAll('.page-top figure.wide').length,
    page.querySelector('.page-top').offsetHeight / page.querySelector('.page-body').offsetHeight,
  ]).filter(([count]) => count > 0),
  overflow,
};""")
    assert result["head"]
    assert result["labels"] == [True, True, True]
    assert sum(count for count, _ in result["tops"]) == 3
    assert len(result["tops"]) >= 2
    assert all(count == 1 or share <= 0.7 for count, share in result["tops"])
    assert result["overflow"] == []


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_korean_text_with_english_words_is_cut_inside_its_column(tmp_path: Path) -> None:
    """In a Korean document the English words are marked as English, and a box of one
    starts lower on its line than the Hangul around it. A paragraph cut at a column's foot
    is still cut below the last line that fits, so nothing runs past the foot and no letter
    is lost or doubled."""
    # Most words are English with a Korean particle, so many lines open with an English box.
    sentence = ("baseline보다 accuracy가 높은 adapter를 layer마다 고르고 retention과 "
                "proxy dev score를 router 없이 checkpoint마다 비교한다. ")
    paragraphs = "\n".join(f"<p>{index} {sentence * 6}</p>" for index in range(1, 25))
    html = content_html().replace("<body ", '<body data-lang="ko" ', 1)
    html = html[:html.index('<section data-title="Method">')] + f'<section data-title="Method">{paragraphs}</section></body>'
    result = run_in_report(tmp_path, html, """
const overflow = [];
for (const column of document.querySelectorAll('.column')) {
  const foot = column.getBoundingClientRect().bottom + 0.5;
  for (const child of column.children) {
    if (child.getBoundingClientRect().bottom > foot) overflow.push(child.textContent.slice(0, 30));
  }
}
const joined = [];
for (const p of document.querySelectorAll('section.page .column > p')) {
  if (p.classList.contains('cont')) joined[joined.length - 1] = joined[joined.length - 1].replace(/\\u2010$/, '') + p.textContent;
  else joined.push(p.textContent);
}
return {overflow, split: document.querySelectorAll('p.split').length, texts: joined,
        english: document.querySelectorAll('.column span[lang="en"]').length};""")
    assert result["overflow"] == []
    assert result["split"] > 0
    assert result["english"] > 0
    expected = [f"{index} {sentence * 6}" for index in range(1, 25)]
    assert [text.strip() for text in result["texts"][1:]] == [text.strip() for text in expected]



FEET = """
const pages = Array.from(document.querySelectorAll('main.pages > section.page'));
const pt = (px) => px * 0.75;
const feet = pages.slice(0, -1).flatMap((page) => Array.from(page.querySelectorAll('.column'))
  .filter((column) => column.lastElementChild !== null)
  .map((column) => [pt(column.getBoundingClientRect().bottom - column.lastElementChild.getBoundingClientRect().bottom),
                    column.dataset.underfull ?? null]));
const last = Array.from(pages[pages.length - 1].querySelectorAll('.column'))
  .map((column) => column.lastElementChild === null ? 0 : pt(column.lastElementChild.getBoundingClientRect().bottom - column.getBoundingClientRect().top));
const gaps = [];
for (const p of document.querySelectorAll('.column > p + p')) gaps.push(pt(parseFloat(getComputedStyle(p).marginTop)));
return {pages: pages.length, feet, last, gaps, pitch: pt(parseFloat(getComputedStyle(document.querySelector('.column > p')).lineHeight))};"""


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
@pytest.mark.parametrize("skin", ["neutral", "another"])
@pytest.mark.parametrize("lang", ["en", "ko"])
def test_columns_end_on_their_foot_under_every_skin(tmp_path: Path, skin: str, lang: str) -> None:
    """Every column but those of the last page ends on the foot of the text area, its
    slack spread between paragraphs, heads and figures, or says in data-underfull how far
    it fell short, by less than the two lines a paragraph needs to begin. Paragraphs of a section stand 3pt apart, and up to 4pt more where a column
    spreads its slack. The last page's columns end level. A Korean text takes the pitch that sets 53 lines in a column. All of this is
    the engine's, so a skin that names only its own faces and colours gets it too."""
    other = tmp_path / "skin"
    other.mkdir()
    (other / "skin.css").write_text(":root { --serif: serif; --sans: sans-serif; --accent: #a33; }\n", encoding="utf-8")
    html = content_html().replace("<body ", f'<body data-lang="{lang}" ', 1)
    result = run_in_report(tmp_path, html, FEET, None if skin == "neutral" else other)
    assert result["pages"] >= 3
    for short, underfull in result["feet"]:
        assert short < 0.6 or (underfull is not None and abs(float(underfull) - short) < 0.6), result["feet"]
    # What the gaps cannot take is less than the two lines a paragraph would need to begin.
    assert all(short < 2 * 10.95 for short, _ in result["feet"]), result["feet"]
    assert sum(short < 0.6 for short, _ in result["feet"]) >= len(result["feet"]) / 2, result["feet"]
    # 3pt apart, and up to 4pt more where a column spreads its slack.
    assert result["gaps"] and all(3 - 0.01 <= gap <= 7 + 0.01 for gap in result["gaps"]), result["gaps"]
    pitch = 10.95 if lang == "en" else 10.95 * 1.0755
    assert abs(result["pitch"] - pitch) < 0.01
    first, second = result["last"]
    # A cut leaves no line alone at either side, so the two may end up to three lines apart.
    assert abs(first - second) <= pitch * 3, result["last"]


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_a_korean_line_opens_its_letters_no_further_than_the_cap(tmp_path: Path) -> None:
    """A justified Korean line spreads its slack between letters, but no line opens its
    Hangul past --letter-cap: the rest goes to its word spaces. A number, a bracket and a
    citation stay closed, since the slack goes around them."""
    words = ["가나다라마바사아", "자차카타파하", "거너더러머버서어저처", "고노도로모보소오", "구누두루무부수우주추쿠"]
    sentence = " ".join(words) + " (Figure 1c) 11/24에는 1.5점 "
    paragraphs = "\n".join(f"<p>{sentence * 4}</p>" for _ in range(6))
    html = content_html().replace("<body ", '<body data-lang="ko" ', 1)
    html = html[:html.index('<section data-title="Method">')] + f'<section data-title="Method">{paragraphs}</section></body>'
    result = run_in_report(tmp_path, html, """
const out = {letters: [], others: []};
for (const block of document.querySelectorAll('main.pages .column > p')) {
  const style = getComputedStyle(block);
  const size = parseFloat(style.fontSize);
  const cap = size * parseFloat(style.getPropertyValue('--letter-cap'));
  const probe = document.createElement('span');
  probe.style.cssText = 'position: absolute; visibility: hidden; white-space: nowrap';
  probe.textContent = '가나다라마바사아자차';
  block.append(probe);
  const natural = probe.getBoundingClientRect().width / 10;
  probe.remove();
  const lines = new Map();
  const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const text = walker.currentNode;
    for (let i = 0; i < text.length; i += 1) {
      const range = document.createRange();
      range.setStart(text, i); range.setEnd(text, i + 1);
      const rect = range.getBoundingClientRect();
      if (rect.width === 0) continue;
      if (/[\\uac00-\\ud7a3]/.test(text.data[i])) {
        const key = Math.round(rect.top);
        lines.set(key, [...(lines.get(key) ?? []), rect.width]);
      } else if (/[0-9A-Za-z/.()]/.test(text.data[i]) && /[0-9A-Za-z/.()]/.test(text.data[i + 1] ?? ' ')) {
        const next = document.createRange();
        next.setStart(text, i + 1); next.setEnd(text, i + 2);
        out.others.push((next.getBoundingClientRect().left - rect.right) / size);
      }
    }
  }
  for (const widths of lines.values()) {
    widths.sort((a, b) => a - b);
    out.letters.push((widths[widths.length >> 1] - natural - cap) / size);
  }
}
return out;""")
    assert result["letters"] and max(result["letters"]) < 0.01, sorted(result["letters"])[-5:]
    assert result["others"] and max(result["others"]) < 0.01, max(result["others"])


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_the_set_pages_hold_the_lines_the_pour_made(tmp_path: Path) -> None:
    """The built report holds the pages Firefox poured, line for line: every page keeps
    its lines, each beginning and ending with the same words, so a browser that would
    break or justify them its own way draws the lines the layout check measured."""
    import importlib

    from html_mcp_web.firefox import firefox, wait_loaded

    sentence = ("baseline보다 accuracy가 높은 adapter를 layer마다 고르고 retention과 "
                "proxy dev score를 router 없이 checkpoint마다 비교한다. ")
    paragraphs = "\n".join(f"<p>{index} {sentence * 5} {SENTENCE * 2}</p>" for index in range(1, 16))
    html = content_html().replace("<body ", '<body data-lang="ko" ', 1)
    html = html[:html.index('<section data-title="Method">')] + f'<section data-title="Method">{paragraphs}</section></body>'
    content = tmp_path / "content.html"
    content.write_text(html, encoding="utf-8")
    engine = importlib.import_module("html_mcp_web.report.build")
    skin = REPO / "templates" / "neutral-report"
    engine.build(content, tmp_path / "set.html", skin)
    real = engine.set_pages
    try:
        engine.set_pages = lambda document: document.read_text(encoding="utf-8")
        engine.build(content, tmp_path / "live.html", skin)
    finally:
        engine.set_pages = real
    script = (Path(__file__).with_name("report_lines.js")).read_text(encoding="utf-8")
    lines = {}
    with firefox() as client:
        for name, ready in (("live", 'document.documentElement.hasAttribute("data-poured")'), ("set", "true")):
            client.navigate((tmp_path / f"{name}.html").as_uri())
            wait_loaded(client, ready, tries=150)
            lines[name] = client.execute_script(script)
    assert "data-frozen" in (tmp_path / "set.html").read_text(encoding="utf-8")
    assert len(lines["set"]) >= 2 and lines["set"] == lines["live"]
