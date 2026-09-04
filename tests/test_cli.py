import subprocess
import sys
from pathlib import Path

import pytest

from html_mcp_web.cli import main

REPO = Path(__file__).resolve().parents[1]
# The template shims import the engine from this checkout, whichever package is installed.
BUILD_ENV = {"PYTHONPATH": str(REPO), "PATH": "/usr/bin:/bin"}



def test_init_creates_documented_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--layout", "slides", "--main", "brief.html", "--port", "9010"]) == 0
    text = (tmp_path / ".html-mcp-web.yaml").read_text(encoding="utf-8")
    assert "artifacts:" in text
    assert "  slides:" in text
    assert "    layout: slides" in text
    assert "    main: brief.html" in text
    assert "port: 9010" in text


def test_init_declares_template_pair(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--layout", "slides", "--main", "slides.html", "--template", "neutral-slides"]) == 1
    assert "together" in capsys.readouterr().err
    assert not (tmp_path / ".html-mcp-web.yaml").exists()
    assert main(["init", "--layout", "slides", "--main", "slides.html",
                 "--template", "neutral-slides", "--content", "content.html"]) == 0
    text = (tmp_path / ".html-mcp-web.yaml").read_text(encoding="utf-8")
    assert "    template: neutral-slides" in text
    assert "    content: content.html" in text


def test_config_changes_port(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--layout", "report"]) == 0
    assert main(["config", "port", "9020"]) == 0
    assert "port: 9020" in (tmp_path / ".html-mcp-web.yaml").read_text(encoding="utf-8")


def test_init_requires_layout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        main(["init"])


def test_mcp_command_starts_without_project_config(tmp_path: Path, monkeypatch) -> None:
    from html_mcp_web import mcp_server

    starts = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mcp_server, "main", lambda start_dir: starts.append(start_dir))

    assert main(["mcp"]) == 0
    assert starts == [tmp_path]


def test_neutral_slides_build_guarded_pages_and_speaker_scripts(tmp_path: Path) -> None:
    content = tmp_path / "content.html"
    slides = tmp_path / "slides.html"
    content.write_text(
        """<!doctype html>
<meta charset="utf-8">
<title>Review</title>
<body data-author="Researcher" data-meta="Laboratory|University">
<aside class="script"><p>Cover greeting.</p></aside>
<section data-title="Results">
  <p class="lead">Measured result.</p>
  <aside class="script"><p>Result explanation.</p></aside>
</section>
</body>
""",
        encoding="utf-8",
    )
    builder = Path(__file__).parents[1] / "templates" / "neutral-slides" / "build.py"

    result = subprocess.run(
        [sys.executable, str(builder), str(content), str(slides)],
        capture_output=True,
        text=True,
        check=True,
        env=BUILD_ENV,
    )

    output = slides.read_text(encoding="utf-8")
    assert "cover + 1 slides, 2 scripts" in result.stdout
    assert output.count('data-layout-guard') == 1
    assert output.count('class="script-block"') == 2
    assert '<section class="page cover">' in output
    # Each script rides in the flow right after the page it belongs to, inside main.pages,
    # so nothing has to compute where it goes.
    assert output.index('class="script-block"') < output.index("</main>")
    before_each_script = output.split('<div class="script-block">')[:-1]
    assert all(chunk.rstrip().endswith("</section>") for chunk in before_each_script)


def test_neutral_report_builds_a4_cover_and_guarded_pages(tmp_path: Path) -> None:
    content = tmp_path / "content.html"
    report = tmp_path / "report.html"
    content.write_text(
        """<!doctype html>
<meta charset="utf-8">
<title>Experiment Report</title>
<body data-author="Research Team" data-meta="Evaluation|13 August 2026">
<section data-title="Executive Summary">
  <p class="lead">Measured evidence from the current evaluation.</p>
</section>
<section data-title="Results">
  <table><tbody><tr><td>Alpha</td><td>18.4%</td></tr></tbody></table>
</section>
</body>
""",
        encoding="utf-8",
    )
    builder = Path(__file__).parents[1] / "templates" / "neutral-report" / "build.py"

    result = subprocess.run(
        [sys.executable, str(builder), str(content), str(report)],
        capture_output=True,
        text=True,
        check=True,
        env=BUILD_ENV,
    )

    output = report.read_text(encoding="utf-8")
    assert "cover + 2 report pages" in result.stdout
    assert output.count('<section class="page') == 3
    assert output.count("data-layout-guard") == 2
    assert "Evaluation<br>" in output
    assert "3 / 3" in output
    # A hundredth of a pixel between the letters, as the slide engine carries: it keeps
    # Safari off the measuring path that opens a gap before an inline box of another size.
    assert "letter-spacing: 0.01px;" in output
