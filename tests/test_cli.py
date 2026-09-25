import subprocess
import sys
from pathlib import Path

import pytest

from html_mcp_web import config as config_module
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


def test_init_and_config_accept_a_named_guideline(tmp_path: Path, monkeypatch) -> None:
    user_config = tmp_path / "user-config"
    for name in ("first", "second"):
        path = user_config / "guidelines" / name / "GUIDELINE.md"
        path.parent.mkdir(parents=True)
        path.write_text(f"# {name}\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "USER_CONFIG_DIR", user_config)
    monkeypatch.chdir(tmp_path)

    assert main(["init", "--layout", "slides", "--guideline", "first"]) == 0
    assert "guideline: first" in (tmp_path / ".html-mcp-web.yaml").read_text(encoding="utf-8")
    assert main(["config", "guideline", "second"]) == 0
    assert "guideline: second" in (tmp_path / ".html-mcp-web.yaml").read_text(encoding="utf-8")


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


def test_mcp_check_names_the_tools_without_serving(tmp_path: Path, monkeypatch, capsys) -> None:
    """A registration is only ever judged by whether a client connects, so a server that
    dies at import is found out after it is registered. --check builds the same server
    the same way and names its tools, from a directory with no project in it."""
    from html_mcp_web.cli import main

    monkeypatch.chdir(tmp_path)
    assert main(["mcp", "--check"]) == 0
    said = capsys.readouterr().out
    assert said.startswith("html-mcp: 6 tools ("), said
    for tool in ("guide", "read_comments", "write_comments", "image", "layout", "listen"):
        assert tool in said


def test_a_missing_mcp_import_is_reported_as_it_failed(monkeypatch, capsys) -> None:
    """An install that had mcp 2.x failed the import with a message naming the rename and
    the pin that fixes it, and the line printed in its place said the package was not
    installed. The error is reported as it failed, so that message reaches the reader."""
    from html_mcp_web import mcp_server

    monkeypatch.setattr(mcp_server, "MISSING_MCP", ImportError(
        "No module named 'mcp.server.fastmcp'. This is mcp 2.x, where FastMCP was renamed"))
    with pytest.raises(SystemExit) as stopped:
        mcp_server._check_dependencies()
    assert stopped.value.code == 1
    said = capsys.readouterr().err
    assert "This is mcp 2.x, where FastMCP was renamed" in said, said
    assert "html-mcp-web[mcp]" in said


@pytest.mark.parametrize("layout, width, height", [("slides", "1280px", "720px"), ("report", "210mm", "297mm")])
def test_init_creates_a_viewable_plain_document(tmp_path, monkeypatch, layout, width, height):
    from html_mcp_web.template_content import ContentParser, Element
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--layout", layout, "--main", "html/brief.html"]) == 0
    text = (tmp_path / "html/brief.html").read_text()
    parser = ContentParser()
    parser.feed(text)
    parser.close()
    html = next(x for x in parser.root.children if isinstance(x, Element) and x.tag == "html")
    body = next(x for x in html.children if isinstance(x, Element) and x.tag == "body")
    children = [x for x in body.children if isinstance(x, Element)]
    assert len(children) == 1 and children[0].tag == "main" and children[0].attributes["class"] == "pages"
    pages = [x for x in children[0].children if isinstance(x, Element)]
    assert len(pages) == 1 and pages[0].tag == "section" and pages[0].attributes["class"] == "page"
    assert width in text and height in text


@pytest.mark.parametrize("layout", ["slides", "report"])
def test_init_builds_missing_template_output(tmp_path, monkeypatch, layout):
    from html_mcp_web.template_content import parse_template_content
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--layout", layout, "--main", "output/main.html",
                 "--template", f"neutral-{layout}", "--content", "source/content.html"]) == 0
    parsed = parse_template_content(tmp_path / "source/content.html")
    assert len(parsed.sections) == 1
    output = (tmp_path / "output/main.html").read_text()
    assert '<main class="pages">' in output
    assert output.count('<section class="page') == 2


def test_init_preserves_existing_sources_and_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main_file = tmp_path / "main.html"
    main_file.write_bytes(b"existing main")
    assert main(["init", "--layout", "slides", "--main", "main.html"]) == 0
    assert main_file.read_bytes() == b"existing main"
    (tmp_path / ".html-mcp-web.yaml").unlink()
    (tmp_path / "content.html").write_bytes(b"existing content")
    assert main(["init", "--layout", "slides", "--main", "main.html",
                 "--template", "neutral-slides", "--content", "content.html"]) == 0
    assert main_file.read_bytes() == b"existing main"
    assert (tmp_path / "content.html").read_bytes() == b"existing content"


def test_init_refuses_to_pair_new_content_with_existing_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.html").write_text("existing main")
    assert main(["init", "--layout", "slides", "--main", "main.html",
                 "--template", "neutral-slides", "--content", "content.html"]) == 1
    assert not (tmp_path / ".html-mcp-web.yaml").exists()
    assert not (tmp_path / "content.html").exists()
    assert (tmp_path / "main.html").read_text() == "existing main"


def test_init_rejects_missing_template_before_creating_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--layout", "slides", "--template", "missing-template",
                 "--content", "content.html"]) == 1
    assert list(tmp_path.iterdir()) == []
