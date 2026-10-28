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


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_the_text_runs_on_across_columns_and_pages_whole(tmp_path: Path) -> None:
    """The flow is poured into two columns a page: nothing runs past the foot of a column,
    a paragraph cut at a foot goes on at the head of the next column with not a letter lost
    or doubled, and a figure moves whole."""
    content = tmp_path / "content.html"
    content.write_text(content_html(), encoding="utf-8")
    report = tmp_path / "report.html"
    subprocess.run([sys.executable, str(BUILDER), str(content), str(report)], check=True,
                   capture_output=True, env={"PYTHONPATH": str(REPO), "PATH": "/usr/bin:/bin"})

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
        result = browser.execute_script("""
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
    finally:
        process.kill()

    assert result["pages"] >= 3
    assert all(count == 2 for count in result["columns"])
    assert result["overflow"] == []
    assert result["split"] > 0
    expected = [f"{SENTENCE * 3}"] + [f"{index} {SENTENCE * 5}" for index in range(1, 23)] * 2
    assert [text.strip() for text in result["texts"]] == [text.strip() for text in expected]
    assert result["figures"] == [True]
    assert result["items"] >= 3
    assert result["flowLeft"] == 0
