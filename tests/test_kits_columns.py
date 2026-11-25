import time
from pathlib import Path

from tests.html_chrome import launch, needs_browser

REPO = Path(__file__).resolve().parents[1]
COLUMNS = REPO / "html_mcp_web" / "kits" / "columns.js"
COMPONENTS = REPO / "html_mcp_web" / "kits" / "components.css"

WORK = ["teacher data, NLL selection, math proxy", "anchor KL, layer selection, combination, efficiency",
        "proxy dev, reference tools, D1-D6, F0"]


def page(with_script: bool) -> str:
    rows = "".join(f"<tr><td>A</td><td>TODO {n}-{n + 4}</td><td>{text}</td></tr>" for n, text in enumerate(WORK))
    script = f"<script>{COLUMNS.read_text(encoding='utf-8')}</script>" if with_script else ""
    return (f"<!doctype html><meta charset='utf-8'><style>{COMPONENTS.read_text(encoding='utf-8')}"
            "table { width: auto; font: 10.67px serif; } td { padding: 0 6px; }</style>"
            f"<div style='width: 320px'><table>{rows}</table></div>{script}")


@needs_browser
def test_a_column_of_short_labels_keeps_them_whole(tmp_path: Path) -> None:
    """Left to the browser, a column of short labels beside a column of longer text
    breaks each label in two. The kit's script keeps them whole and the longer column
    wraps instead, within the same width."""
    browser = launch()
    try:
        results = []
        for with_script in (False, True):
            path = tmp_path / f"page{int(with_script)}.html"
            path.write_text(page(with_script), encoding="utf-8")
            browser.navigate(path.as_uri())
            time.sleep(0.3)
            results.append(browser.execute_script("""
const table = document.querySelector('table');
const lines = (cell) => { const range = document.createRange(); range.selectNodeContents(cell); return range.getClientRects().length; };
return {
  labels: Array.from(table.rows).map((row) => lines(row.cells[1])),
  within: table.offsetWidth <= table.parentElement.offsetWidth,
};"""))
    finally:
        browser.quit()

    bare, fitted = results
    assert bare["labels"] != [1, 1, 1]
    assert fitted["labels"] == [1, 1, 1]
    assert fitted["within"]
