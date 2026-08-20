import re
import shutil
from pathlib import Path

import pytest

pytest.importorskip("marionette_driver.marionette")
pptx = pytest.importorskip("pptx")

from html_mcp_web.pptx_export import export_pptx  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
NEUTRAL = REPO / "templates" / "neutral-slides"

CONTENT = '''<!doctype html>
<meta charset="utf-8">
<title>Export Deck</title>
<body data-author="Export Author" data-meta="Lab|Today" data-sub="Subtitle line">
<section data-layout="contents" data-title="Contents"><ol><li>Numbers</li></ol></section>
<section data-title="Numbers">
  <p class="lead">Lead sentence with <b>bold</b> and <code>code</code>.</p>
  <ul class="notes"><li>First point<ul><li>Nested point</li></ul></li><li>Second point</li></ul>
  <ol><li>Step one</li><li>Step two</li></ol>
  <table><thead><tr><th>Name</th><th>Value</th></tr></thead>
    <tbody><tr><td>alpha</td><td>1</td></tr><tr><td>beta</td><td>2</td></tr></tbody></table>
  <div class="card"><h3>Card title</h3><p>Card body text.</p></div>
  <p>Math stays a picture: $x^2$</p>
  <img src="fig/box.png" alt="">
</section>
</body>
'''


def deck(tmp_path: Path) -> Path:
    from html_mcp_web.slides import build
    from PIL import Image

    (tmp_path / "fig").mkdir()
    Image.new("RGB", (120, 60), "#3366aa").save(tmp_path / "fig" / "box.png")
    content = tmp_path / "content.html"
    content.write_text(CONTENT, encoding="utf-8")
    output = tmp_path / "slides.html"
    build(content, output, NEUTRAL)
    return output


def shapes_by_kind(slide) -> dict[str, list]:
    kinds: dict[str, list] = {}
    for shape in slide.shapes:
        kinds.setdefault(str(shape.shape_type).split(" ")[0], []).append(shape)
    return kinds


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_export_bakes_chrome_into_background_and_keeps_body_editable(tmp_path: Path) -> None:
    html = deck(tmp_path)
    out = tmp_path / "out" / "deck.pptx"
    result = export_pptx(html.as_uri(), out, tmp_path, None)
    assert result["path"] == str(out)
    assert result["slides"] == 3
    prs = pptx.Presentation(str(out))
    assert (prs.slide_width, prs.slide_height) == (12192000, 6858000)
    # A full-bleed page (cover, contents) is a locked background screenshot the mouse cannot
    # grab, with its words overlaid as editable text boxes so decorations stay in the picture
    # while the text stays real.
    from pptx.oxml.ns import qn as _qn
    for slide in list(prs.slides)[:2]:
        blip = slide._element.find(_qn("p:cSld")).find(_qn("p:bg"))
        assert blip is not None and blip.find(f".//{_qn('a:blip')}") is not None
        assert list(shapes_by_kind(slide)) == ["TEXT_BOX"]
    cover_texts = [s.text_frame.text for s in prs.slides[0].shapes]
    assert "Export Deck" in cover_texts and "Export Author" in cover_texts
    body = prs.slides[2]
    # The chrome (title bar, footer, page number, corner logos) bakes into a locked
    # background the mouse cannot grab; only the body's own blocks stay editable over it.
    body_bg = body._element.find(_qn("p:cSld")).find(_qn("p:bg"))
    assert body_bg is not None and body_bg.find(f".//{_qn('a:blip')}") is not None
    kinds = shapes_by_kind(body)
    texts = [shape.text_frame.text for shape in kinds["TEXT_BOX"]]
    assert "Numbers" not in texts  # the title bar baked into the background, not a text box
    assert "3 / 3" not in texts    # the footer page number baked in too
    lead = next(shape for shape in kinds["TEXT_BOX"] if shape.text_frame.text.startswith("Lead sentence"))
    runs = lead.text_frame.paragraphs[0].runs
    assert [run.text for run in runs] == ["Lead sentence with ", "bold", " and ", "code", "."]
    assert runs[1].font.bold is True
    assert runs[3].font.name == "Consolas"
    assert runs[0].font.name == "Arial"
    bullets = next(shape for shape in kinds["TEXT_BOX"] if shape.text_frame.text.startswith("First point"))
    assert [p.text for p in bullets.text_frame.paragraphs] == ["First point", "Nested point", "Second point"]
    steps = next(shape for shape in kinds["TEXT_BOX"] if shape.text_frame.text.startswith("Step one"))
    assert "buAutoNum" in steps.text_frame.paragraphs[0]._p.xml
    assert len(kinds["TABLE"]) == 1
    table = kinds["TABLE"][0].table
    assert table.cell(0, 0).text == "Name" and table.cell(2, 1).text == "2"
    # The table carries no style-drawn grid; only the per-cell borders from the DOM show.
    from pptx.oxml.ns import qn
    assert kinds["TABLE"][0]._element.xpath(".//a:tableStyleId")[0].text == "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"
    # Borders come before the fill in tcPr; PowerPoint drops borders placed after it.
    header_cell = table.cell(0, 0)._tc
    tc_pr = header_cell.find(qn("a:tcPr"))
    order = [child.tag for child in tc_pr]
    fill_index = next(i for i, tag in enumerate(order) if tag.endswith("}noFill") or tag.endswith("}solidFill"))
    assert order.index(qn("a:lnB")) < fill_index
    assert tc_pr.find(qn("a:lnB")).find(qn("a:solidFill")) is not None  # a visible line, not noFill
    # The <code> chip's background becomes a run highlight, and the header's letter-spacing
    # becomes run tracking (spc).
    body_xml = body._element.xml
    assert "a:highlight" in body_xml
    assert re.search(r'spc="\d+"', body_xml)
    assert 'kern="0"' in body_xml  # kerning on, so Latin reads as tight as on the page
    # The card is a panel (its accent rule) followed by its own text; math and the image are pictures.
    assert "Card title" in texts and "Card body text." in texts
    assert len(kinds["PICTURE"]) == 2
    assert kinds["AUTO_SHAPE"]  # the card's accent rule; the chrome bars are baked, not shapes


DEJAVU = Path("/usr/share/fonts/truetype/dejavu")


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
@pytest.mark.skipif(not (DEJAVU / "DejaVuSans.ttf").is_file(), reason="a static TrueType face is required")
def test_export_embeds_the_skin_face(tmp_path: Path) -> None:
    import json
    import re
    import zipfile

    pytest.importorskip("fontTools")
    html = deck(tmp_path)
    skin = tmp_path / "skin"
    (skin / "fonts").mkdir(parents=True)
    shutil.copy(DEJAVU / "DejaVuSans.ttf", skin / "fonts" / "Sans.ttf")
    shutil.copy(DEJAVU / "DejaVuSans-Bold.ttf", skin / "fonts" / "Sans-Bold.ttf")
    (skin / "skin.css").write_text("", encoding="utf-8")
    (skin / "skin.json").write_text(json.dumps({"pptx": {"fonts": {
        "family": "DejaVu Sans", "regular": "fonts/Sans.ttf", "bold": "fonts/Sans-Bold.ttf"}}}), encoding="utf-8")
    out = tmp_path / "deck.pptx"
    result = export_pptx(html.as_uri(), out, tmp_path, skin)
    assert result["font"] == "DejaVu Sans" and result["embedded_faces"] == ["bold", "regular"]
    with zipfile.ZipFile(out) as archive:
        names = archive.namelist()
        assert "ppt/fonts/font1.fntdata" in names and "ppt/fonts/font2.fntdata" in names
        assert archive.read("ppt/fonts/font1.fntdata")[8:12] == b"\x02\x00\x02\x00"  # EOT 0x00020002
        presentation = archive.read("ppt/presentation.xml").decode("utf-8")
        assert 'Extension="fntdata"' in archive.read("[Content_Types].xml").decode("utf-8")
        assert 'embedTrueTypeFonts="1"' in re.search(r"<p:presentation\b[^>]*>", presentation).group(0)
        assert re.search(r'<p:embeddedFont><p:font typeface="DejaVu Sans"[^>]*/><p:regular r:id="rId\d+"/><p:bold r:id="rId\d+"/></p:embeddedFont>', presentation)
    prs = pptx.Presentation(str(out))  # the archive still opens as a presentation
    lead = next(shape for shape in prs.slides[2].shapes if shape.has_text_frame and shape.text_frame.text.startswith("Lead"))
    assert lead.text_frame.paragraphs[0].runs[0].font.name == "DejaVu Sans"


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_export_route_writes_inside_the_project(tmp_path: Path) -> None:
    import json
    import socket
    import urllib.error
    import urllib.request

    import yaml

    from html_mcp_web.config import load_config
    from html_mcp_web.project_server import SharedProjectServer

    deck(tmp_path)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = int(listener.getsockname()[1])
    config_path = tmp_path / ".html-mcp-web.yaml"
    config_path.write_text(yaml.safe_dump({
        "artifacts": {"slides": {"label": "Slides", "layout": "slides", "main": "slides.html"}},
        "port": port,
    }, sort_keys=False), encoding="utf-8")
    shared = SharedProjectServer(load_config(config_path))
    try:
        shared.ensure()
        base = f"http://127.0.0.1:{port}/artifacts/slides/export/pptx"

        def post(payload: dict) -> dict:
            request = urllib.request.Request(base, data=json.dumps(payload).encode("utf-8"),
                                             headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))

        result = post({"out": "export/deck.pptx"})
        assert result["path"] == str(tmp_path / "export" / "deck.pptx")
        assert (tmp_path / "export" / "deck.pptx").is_file()
        assert [page["screenshot"] for page in result["pages"]] == [True, True, True]
        with pytest.raises(urllib.error.HTTPError) as error:
            post({"out": "../outside.pptx"})
        assert error.value.code == 400
        # The topbar button fetches this: the file is built at export/<artifact>.pptx and served.
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/artifacts/slides/download/pptx", timeout=120) as response:
            assert response.headers["Content-Disposition"] == 'attachment; filename="slides.pptx"'
            body = response.read()
        assert body[:2] == b"PK" and (tmp_path / "export" / "slides.pptx").read_bytes() == body
    finally:
        shared.stop()


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_each_page_screenshots_its_own_element(tmp_path: Path) -> None:
    """Marks restart on every page; a document-wide lookup once shot page 1's math into page 2."""
    from html_mcp_web.slides import build

    content = tmp_path / "content.html"
    content.write_text('''<!doctype html>
<meta charset="utf-8">
<title>Two Math Pages</title>
<body data-author="A" data-meta="B">
<section data-title="First"><p>Short $a$</p></section>
<section data-title="Second"><p>A much longer paragraph carrying $b^2 + c^2$ so its picture is wider than the first</p></section>
</body>
''', encoding="utf-8")
    html = tmp_path / "slides.html"
    build(content, html, NEUTRAL)
    out = tmp_path / "deck.pptx"
    export_pptx(html.as_uri(), out, tmp_path, None)
    prs = pptx.Presentation(str(out))
    first = shapes_by_kind(prs.slides[1])["PICTURE"][0]
    second = shapes_by_kind(prs.slides[2])["PICTURE"][0]
    assert first.image.blob != second.image.blob
    # Both blocks span the body width; the picture is the block shot at 3x.
    assert first.image.size[0] == second.image.size[0] == round(first.width / 9525 * 3)


@pytest.mark.skipif(shutil.which("firefox") is None, reason="Firefox is required")
def test_inline_svg_is_embedded_as_vector_math_stays_raster(tmp_path: Path) -> None:
    import re
    import zipfile

    from html_mcp_web.slides import build

    content = tmp_path / "content.html"
    content.write_text('''<!doctype html>
<meta charset="utf-8">
<title>Vector</title>
<body data-author="A" data-meta="B">
<section data-title="Diagram">
  <svg viewBox="0 0 200 100" xmlns="http://www.w3.org/2000/svg"><rect x="10" y="10" width="180" height="80" fill="none" stroke="#333"/></svg>
</section>
<section data-title="Formula"><p>Only math here: $x^2 + y^2$</p></section>
</body>
''', encoding="utf-8")
    html = tmp_path / "slides.html"
    build(content, html, NEUTRAL)
    out = tmp_path / "deck.pptx"
    result = export_pptx(html.as_uri(), out, tmp_path, None)
    diagram = next(p for p in result["pages"] if p["title"] == "Diagram")
    formula = next(p for p in result["pages"] if p["title"] == "Formula")
    assert diagram["vector_svgs"] == 1 and formula["vector_svgs"] == 0
    with zipfile.ZipFile(out) as archive:
        svg_parts = [n for n in archive.namelist() if n.endswith(".svg")]
        assert len(svg_parts) == 1
        # The embedded svg's viewBox aspect is normalized to the picture frame so PowerPoint,
        # which fills the frame, does not stretch the drawing.
        svg_text = archive.read(svg_parts[0]).decode("utf-8")
        vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', svg_text).group(1).split()]
        pic = next(sh for sh in pptx.Presentation(str(out)).slides[1].shapes if sh.shape_type is not None and "PICTURE" in str(sh.shape_type))
        assert abs(vb[2] / vb[3] - pic.width / pic.height) < 0.01
        # The deck font is named on the svg root so PowerPoint keeps the browser's metrics
        # for the labels instead of substituting a wider face.
        assert re.search(r'<svg[^>]*font-family="[^"]+"', svg_text)
        assert "image/svg+xml" in archive.read("[Content_Types].xml").decode("utf-8")
        # The diagram slide's blip carries an svgBlip pointing at the svg part; math does not.
        diagram_xml = archive.read("ppt/slides/slide2.xml").decode("utf-8")
        formula_xml = archive.read("ppt/slides/slide3.xml").decode("utf-8")
        assert "svgBlip" in diagram_xml and "svgBlip" not in formula_xml
        svg_rid = re.search(r'svgBlip[^>]*r:embed="(rId\d+)"', diagram_xml).group(1)
        rels = archive.read("ppt/slides/_rels/slide2.xml.rels").decode("utf-8")
        target = re.search(rf'Id="{svg_rid}"[^>]*Target="([^"]+)"', rels).group(1)
        assert target.endswith(".svg")
        # both slides still carry a raster fallback picture
        assert "<p:pic>" in diagram_xml and "<p:pic>" in formula_xml
    pptx.Presentation(str(out))  # the package still opens
