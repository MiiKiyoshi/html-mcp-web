from pathlib import Path

import pytest

from html_mcp_web.template_content import parse_template_content

REPO = Path(__file__).resolve().parents[1]
# The template shims import the engine from this checkout, whichever package is installed.
BUILD_ENV = {"PYTHONPATH": str(REPO), "PATH": "/usr/bin:/bin"}



def test_nested_section_markup_stays_inside_page_body(tmp_path: Path) -> None:
    content_file = tmp_path / "content.html"
    content_file.write_text('''<!doctype html>
<title>Nested content</title>
<body data-author="Researcher" data-meta="Lab|Date">
  <aside class="script"><p>Cover script.</p></aside>
  <section data-title="Page">
    <div><section class="card"><p>Nested section.</p></section></div>
    <aside class="script"><p>Page script.</p></aside>
  </section>
</body>
''', encoding="utf-8")

    content = parse_template_content(content_file)

    assert content.author == "Researcher"
    assert content.metadata == ["Lab", "Date"]
    assert content.cover_script_html == "<p>Cover script.</p>"
    assert content.sections[0].title == "Page"
    assert '<section class="card"><p>Nested section.</p></section>' in content.sections[0].body_html
    assert "Page script" not in content.sections[0].body_html
    assert content.sections[0].script_html == "<p>Page script.</p>"


def test_page_kinds_carry_their_own_attributes(tmp_path: Path) -> None:
    content_file = tmp_path / "content.html"
    content_file.write_text('''<!doctype html>
<title>Deck</title>
<body data-author="Researcher" data-meta="Lab" data-sub="Second cover line">
  <section data-layout="contents" data-title="Contents"><ol><li>One</li></ol></section>
  <section data-layout="divider" data-no="01"><p class="label">Part</p></section>
  <section data-title="Body"><p>Text.</p></section>
</body>
''', encoding="utf-8")

    content = parse_template_content(content_file)

    assert content.subtitle == "Second cover line"
    assert [section.layout for section in content.sections] == ["contents", "divider", "body"]
    assert content.sections[1].title == ""
    assert content.sections[1].attributes["data-no"] == "01"
    assert content.sections[2].layout == "body"


def test_a_titled_page_still_requires_its_title(tmp_path: Path) -> None:
    content_file = tmp_path / "content.html"
    content_file.write_text(
        '<title>Deck</title><body data-author="R" data-meta="Lab"><section><p>Text.</p></section></body>',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="data-title"):
        parse_template_content(content_file)


def test_shipped_slide_template_builds_every_page_kind(tmp_path: Path) -> None:
    import subprocess
    import sys

    template = Path(__file__).resolve().parent.parent / "templates" / "neutral-slides"
    output = tmp_path / "slides.html"
    subprocess.run(
        [sys.executable, str(template / "build.py"), str(template / "content.html"), str(output)],
        check=True, capture_output=True, env=BUILD_ENV,
    )

    built = output.read_text(encoding="utf-8")
    assert '<div class="sub">' in built
    assert 'class="page contents"' in built
    assert 'class="page divider"' in built
    # The opening summary stays under the title; the blocks that share the remaining
    # height sit inside .rest.
    body = built.split('<div class="body" data-layout-guard>')[1].split("</div>\n      <footer")[0]
    assert body.index('<p class="lead">') < body.index('<div class="rest">')
    assert '<div class="grid3">' in body.split('<div class="rest">')[1]
    assert built.count("data-layout-guard") == len(
        parse_template_content(template / "content.html").sections
    )
    # No math in the sample deck, so the KaTeX bundle stays out and the file stays small.
    # The skeleton names .katex-display to size display equations, so the bundle's own
    # markers are what tell it apart from that one selector.
    assert "renderMathInElement" not in built
    assert "KaTeX_Main" not in built
    # No wrapped svg label either, so the wrap script stays out too.
    assert "getSubStringLength" not in built
    assert output.stat().st_size < 100_000


def test_math_deck_carries_katex_offline(tmp_path: Path) -> None:
    from html_mcp_web.slides import build

    content = tmp_path / "content.html"
    content.write_text('''<!doctype html>
<title>Math</title>
<body data-author="R" data-meta="Lab">
<section data-title="Formula"><p>Ratio $\\frac{a}{b}$ and $$\\sum_i x_i$$</p></section>
</body>
''', encoding="utf-8")
    output = tmp_path / "slides.html"
    build(content, output, Path(__file__).resolve().parent.parent / "templates" / "neutral-slides")

    built = output.read_text(encoding="utf-8")
    assert "renderMathInElement(document.body" in built
    # Every font the stylesheet names is embedded; nothing points outside the file.
    assert built.count("data:font/woff2;base64,") == 20
    assert "url(fonts/" not in built
    assert "https://" not in built.split("<style>", 1)[1].split("</style>", 1)[0]
    # The renderer runs at the end of the body, so it has finished before load fires
    # and a print snapshot sees rendered math.
    assert built.index("renderMathInElement") > built.index("</main>")


def test_skin_fonts_are_embedded_like_katex_fonts(tmp_path: Path) -> None:
    from html_mcp_web.slides import build

    skin = tmp_path / "skin"
    (skin / "fonts").mkdir(parents=True)
    # Any bytes will do for the embedding rule; the browser is not asked to read them here.
    (skin / "fonts" / "Body-Regular.woff2").write_bytes(b"wOF2fake-regular")
    (skin / "fonts" / "Body-Bold.woff2").write_bytes(b"wOF2fake-bold")
    (skin / "skin.css").write_text('''
@font-face { font-family: "Body"; font-weight: 400; src: url(fonts/Body-Regular.woff2) format("woff2"); }
@font-face { font-family: "Body"; font-weight: 700; src: url("fonts/Body-Bold.woff2") format("woff2"), url(fonts/Body-Bold.ttf) format("truetype"); }
:root { --font: "Body", sans-serif; }
''', encoding="utf-8")
    content = tmp_path / "content.html"
    content.write_text(
        '<title>Deck</title><body data-author="R" data-meta="Lab"><section data-title="A"><p>Text.</p></section></body>',
        encoding="utf-8",
    )
    output = tmp_path / "slides.html"
    build(content, output, skin)

    built = output.read_text(encoding="utf-8")
    assert built.count("data:font/woff2;base64,") == 2
    assert "url(fonts/" not in built and 'url("fonts/' not in built
    assert "truetype" not in built


def test_shared_metadata_is_required(tmp_path: Path) -> None:
    content_file = tmp_path / "content.html"
    content_file.write_text(
        '<title>Missing metadata</title><body><section data-title="Page"></section></body>',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="data-author and data-meta"):
        parse_template_content(content_file)


def test_a_deck_with_a_wrapped_label_carries_the_wrap_script(tmp_path: Path) -> None:
    from html_mcp_web.slides import build

    content = tmp_path / "content.html"
    content.write_text('''<!doctype html>
<title>Wrap</title>
<body data-author="R" data-meta="Lab">
<section data-title="Figure"><svg viewBox="0 0 200 100"><text x="4" y="20" data-wrap="190">a label</text></svg></section>
</body>
''', encoding="utf-8")
    output = tmp_path / "slides.html"
    build(content, output, Path(__file__).resolve().parent.parent / "templates" / "neutral-slides")

    built = output.read_text(encoding="utf-8")
    # The breaker and the script that drives it run at the end of the body, like the math
    # renderer, so the lines are in place before load fires.
    assert built.index("texLineBreak_lib") > built.index("</main>")
    assert built.index("texLineBreak_hyphens_en-us") > built.index("</main>")

    # A label given a box instead of a width brings them along the same way.
    content.write_text(content.read_text(encoding="utf-8").replace('data-wrap="190"', 'data-fit="190x40"'),
                       encoding="utf-8")
    build(content, output, Path(__file__).resolve().parent.parent / "templates" / "neutral-slides")
    assert "texLineBreak_lib" in output.read_text(encoding="utf-8")


def test_an_appendix_is_counted_apart_from_the_deck(tmp_path: Path) -> None:
    """An appendix is opened when a question calls for it, so the pages the audience is
    told to expect stop before it. Its own pages carry a count of their own, since a page
    numbered past the total reads as a mistake."""
    from html_mcp_web.slides import build

    def deck(marker: str) -> str:
        content = tmp_path / "content.html"
        content.write_text(f'''<!doctype html>
<title>Counted</title>
<body data-author="R" data-meta="Lab">
<section data-title="First"><p>One.</p></section>
<section data-title="Second"><p>Two.</p></section>
<section data-layout="divider" data-no="A"{marker}><p class="label">Appendix</p></section>
<section data-title="Held back"><p>Only if asked.</p></section>
</body>
''', encoding="utf-8")
        output = tmp_path / "slides.html"
        build(content, output, Path(__file__).resolve().parent.parent / "templates" / "neutral-slides")
        return output.read_text(encoding="utf-8")

    import re
    marked = re.findall(r'<span class="pageno">([^<]*)</span>', deck(' data-appendix'))
    # Cover and two pages are what the audience is shown; the divider opens the appendix.
    assert marked == ["1 / 3", "2 / 3", "3 / 3", "A1 / A2", "A2 / A2"], marked

    # The same deck without the marker counts the whole of itself: a divider parts one
    # chapter from the next as often as it opens an appendix, so it changes nothing by
    # itself.
    plain = re.findall(r'<span class="pageno">([^<]*)</span>', deck(""))
    assert plain == ["1 / 5", "2 / 5", "3 / 5", "4 / 5", "5 / 5"], plain
