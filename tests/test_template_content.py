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


def test_a_row_starting_under_a_spanned_cell_marks_its_column(tmp_path: Path) -> None:
    """The first column is aligned by :first-child, so a row whose first column is
    spanned from above names its first cell's real column for the style to use. Rows in
    the header count their own spans, and a span stops at its row group."""
    content = tmp_path / "content.html"
    content.write_text('''<title>T</title><body data-author="A" data-meta="B">
<section data-title="Table"><table>
<thead><tr><th rowspan="2">Design</th><th rowspan="2">STA</th><th colspan="2">Time</th></tr>
<tr><th>init</th><th>sum</th></tr></thead>
<tbody><tr><td rowspan="2">aes</td><td>custom</td><td>31</td><td>818</td></tr>
<tr><td>OpenSTA</td><td>22</td><td>1510</td></tr>
<tr><td colspan="2">all</td><td>53</td><td>2328</td></tr></tbody>
</table></section></body>''', encoding="utf-8")
    body = parse_template_content(content).sections[0].body_html
    assert '<tr><th>init</th>' not in body and '<tr><th data-column="3">init</th>' in body
    assert '<tr><td data-column="2">OpenSTA</td>' in body
    assert '<tr><td rowspan="2">aes</td>' in body and '<tr><td colspan="2">all</td>' in body
    assert body.count("data-column") == 2
    content.write_text(content.read_text(encoding="utf-8").replace('rowspan="2">aes', 'rowspan="two">aes'),
                       encoding="utf-8")
    with pytest.raises(ValueError, match='rowspan is a whole number, not "two"'):
        parse_template_content(content)


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


def test_a_formula_in_a_figure_goes_in_a_foreign_object(tmp_path: Path) -> None:
    """The renderer puts HTML in place of a formula and an svg <text> draws none, so a
    formula there vanished. It stops the build, naming the formula; one in a
    <foreignObject> builds, and a lone dollar in a label is no formula."""
    from html_mcp_web.slides.build import build

    content = tmp_path / "content.html"
    deck = ('<title>Deck</title><body data-author="R" data-meta="Lab"><section data-title="Figure">'
            '<svg viewBox="0 0 300 100"><text x="4" y="20">{label}</text>'
            '<foreignObject x="4" y="40" width="200" height="40"><div>$C_{{tot}}$</div></foreignObject>'
            '</svg></section></body>')
    content.write_text(deck.format(label="cost in $ per unit"), encoding="utf-8")
    build(content, tmp_path / "slides.html", REPO / "templates" / "neutral-slides")
    built = (tmp_path / "slides.html").read_text(encoding="utf-8")
    assert "<div>$C_{tot}$</div></foreignobject>" in built and "renderMathInElement" in built
    content.write_text(deck.format(label=r"total $C = \sum C_i$"), encoding="utf-8")
    with pytest.raises(ValueError, match=r'the formula "\$C = \\sum C_i\$" in an svg <text> is not drawn'):
        build(content, tmp_path / "slides.html", REPO / "templates" / "neutral-slides")


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


@pytest.mark.parametrize("opening", ["", '<p class="lead">Opening.</p>'])
def test_takeaway_is_outside_the_spread_and_uses_skin_lead_style(tmp_path: Path, opening: str) -> None:
    from html_mcp_web.slides import build
    from lxml import html

    content = tmp_path / "content.html"
    content.write_text(f'''<title>Deck</title><body data-author="R" data-meta="Date">
<section data-title="Result">{opening}<div><p>Evidence.</p></div>
<p id="conclusion" class="takeaway"><strong>Result</strong> &amp; meaning.</p>
<!-- A source note after the last block. --></section></body>''', encoding="utf-8")
    output = tmp_path / "slides.html"
    build(content, output, REPO / "templates" / "neutral-slides")
    body = html.fromstring(output.read_text()).find('.//div[@class="body"]')
    closing = body[-1]
    assert closing.tag == "p" and closing.attrib["id"] == "conclusion"
    assert closing.attrib["class"] == "lead takeaway"
    assert closing.text_content() == "Result & meaning."
    rest = body.find('div[@class="rest"]')
    assert not rest.xpath('.//*[@id="conclusion"]')
    assert "Evidence." in rest.text_content()


@pytest.mark.parametrize("content_html", [
    '<p class="takeaway">Conclusion.</p><p>Later body.</p>',
    '<p class="takeaway">One.</p><p class="takeaway">Two.</p>',
    '<div class="takeaway">Conclusion.</div>',
])
def test_takeaway_requires_one_final_paragraph(tmp_path: Path, content_html: str) -> None:
    from html_mcp_web.slides import build

    content = tmp_path / "content.html"
    content.write_text(f'<title>Deck</title><body data-author="R" data-meta="Date">'
                       f'<section data-title="Result">{content_html}</section></body>', encoding="utf-8")
    with pytest.raises(ValueError, match="one final p.takeaway"):
        build(content, tmp_path / "slides.html", REPO / "templates" / "neutral-slides")


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


def test_contents_item_with_a_sub_list_wraps_its_own_text() -> None:
    from html_mcp_web.slides.build import contents_list

    built, columns = contents_list('''<ol>
  <li>Speed
    <ul><li>Direct Wire Model</li><li>Overall</li></ul>
  </li>
  <li><span class="venue">Venue</span>Name<ul><li>Part</li></ul></li>
  <li>Summary</li>
</ol>''', None)

    assert ('<li class="has-sub"><span class="entry">Speed\n    </span>'
            '<ul><li>Direct Wire Model</li><li>Overall</li></ul></li>') in built
    assert '<li class="has-sub"><span class="entry"><span class="venue">Venue</span>Name</span><ul>' in built
    # Sub-items under more than one outer item leave the column count to the page, which
    # may set two, so the text of an item without sub-items becomes one entry too.
    assert columns is None
    assert '<li><span class="entry">Summary</span></li>' in built
    with pytest.raises(ValueError, match="one ul of sub-items"):
        contents_list("<ol><li>Speed<ul><li>Part</li></ul>after</li></ol>", None)
    with pytest.raises(ValueError, match="one ul of sub-items"):
        contents_list("<ol><li>Speed<ol><li>Part</li></ol></li></ol>", None)


def test_contents_columns_are_left_to_the_page_unless_data_columns_names_a_count() -> None:
    from html_mcp_web.slides.build import contents_list

    nested = "<ol><li>One<ul><li>a</li></ul></li><li>Two</li></ol>"
    plain = "<ol><li>One</li><li>Two</li></ol>"
    assert contents_list(nested, None)[1] is None
    assert contents_list(nested, "1") == ('<ol><li class="has-sub"><span class="entry">One</span>'
                                          '<ul><li>a</li></ul></li><li>Two</li></ol>', 1)
    # One outer item has nothing to split, and a plain list stays whole unless asked.
    assert contents_list("<ol><li>One<ul><li>a</li><li>b</li></ul></li></ol>", None)[1] == 1
    assert contents_list(plain, None) == (plain, 1)
    assert contents_list(plain, "2") == ('<ol><li><span class="entry">One</span></li>'
                                         '<li><span class="entry">Two</span></li></ol>', 2)
    for wrong in ("two", "0", "10"):
        with pytest.raises(ValueError, match="data-columns"):
            contents_list(plain, wrong)


def test_contents_data_scale_marks_the_area_and_takes_only_a_positive_number(tmp_path: Path) -> None:
    from html_mcp_web.slides.build import build

    skin = REPO / "templates" / "neutral-slides"
    content = tmp_path / "content.html"
    deck = '''<title>Deck</title><body data-author="R" data-meta="Lab">
<section data-layout="contents" data-scale="{}"><ol><li>One</li></ol></section></body>'''
    content.write_text(deck.format("0.8"), encoding="utf-8")
    build(content, tmp_path / "slides.html", skin)
    built = (tmp_path / "slides.html").read_text(encoding="utf-8")
    assert '<div class="wide scaled" data-layout-guard style="--contents-scale: 0.8">' in built
    # The scaled list sits in a wrapper that takes no height in the flow.
    assert '<div class="list"><ol>' in built
    content.write_text(deck.replace(' data-scale="{}"', ""), encoding="utf-8")
    build(content, tmp_path / "slides.html", skin)
    assert 'class="list"' not in (tmp_path / "slides.html").read_text(encoding="utf-8")
    for wrong in ("small", "0", "-1"):
        content.write_text(deck.format(wrong), encoding="utf-8")
        with pytest.raises(ValueError, match="data-scale"):
            build(content, tmp_path / "slides.html", skin)


def test_citations_number_by_first_use_and_list_on_their_page(tmp_path: Path) -> None:
    from html_mcp_web.slides.build import build

    skin = REPO / "templates" / "neutral-slides"
    content = tmp_path / "content.html"
    deck = '''<title>Deck</title><body data-author="R" data-meta="Lab">
<ol class="references">
  <li id="elmore">W. C. Elmore, 1948.</li>
  <li id="obrien">P. R. O'Brien and T. L. Savarino, 1989.</li>
</ol>
<section data-title="One"><p>Effective load <cite>obrien</cite>.</p>{one}</section>
<section data-title="Two"><p>Moment <cite>elmore, obrien</cite>.</p></section>
</body>'''
    content.write_text(deck.format(one=""), encoding="utf-8")
    build(content, tmp_path / "slides.html", skin)
    built = (tmp_path / "slides.html").read_text(encoding="utf-8")
    one, two = built.split('<h2>Two</h2>')
    # Numbers follow the first citation in the deck, and each page lists only its own.
    assert 'Effective load <span class="cite">[1]</span>' in one
    assert '<p class="refs"><span>[1] P. R. O\'Brien and T. L. Savarino, 1989.</span></p>' in one
    assert 'Moment <span class="cite">[2, 1]</span>' in two
    assert ('<p class="refs"><span>[1] P. R. O\'Brien and T. L. Savarino, 1989.</span>'
            '<span>[2] W. C. Elmore, 1948.</span></p>') in two
    for wrong, message in (('<p><cite>missing</cite></p>', "does not define"),
                           ('<aside class="script"><p><cite>elmore</cite></p></aside>', "belongs in the content")):
        content.write_text(deck.format(one=wrong), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            build(content, tmp_path / "slides.html", skin)
    content.write_text(deck.format(one="").replace(
        '<section data-title="Two">', '<section data-layout="contents"><ol><li><cite>elmore</cite></li></ol></section>'
        '<section data-title="Two">'), encoding="utf-8")
    with pytest.raises(ValueError, match="belongs in the content"):
        build(content, tmp_path / "slides.html", skin)


def test_a_citation_inside_an_svg_is_a_tspan_numbered_with_the_rest(tmp_path: Path) -> None:
    """An HTML span inside an svg <text> ends the drawing where the browser reads it, so a
    citation there becomes a tspan. It takes its number in document order with the
    citations around it and is listed on its page like them."""
    from html_mcp_web.slides.build import build

    content = tmp_path / "content.html"
    content.write_text('''<title>Deck</title><body data-author="R" data-meta="Lab">
<ol class="references">
  <li id="elmore">W. C. Elmore, 1948.</li>
  <li id="obrien">P. R. O'Brien and T. L. Savarino, 1989.</li>
</ol>
<section data-title="One"><svg viewBox="0 0 300 40"><text x="4" y="20" data-wrap="290">Shielding <cite>obrien, elmore</cite> holds</text><rect x="0" y="0" width="300" height="40"/></svg>
<p>Moment <cite>elmore</cite>.</p></section>
</body>''', encoding="utf-8")
    build(content, tmp_path / "slides.html", REPO / "templates" / "neutral-slides")
    built = (tmp_path / "slides.html").read_text(encoding="utf-8")
    assert '<text x="4" y="20" data-wrap="290">Shielding <tspan class="cite">[1, 2]</tspan> holds</text>' in built
    assert 'Moment <span class="cite">[2]</span>' in built
    assert ('<p class="refs"><span>[1] P. R. O\'Brien and T. L. Savarino, 1989.</span>'
            '<span>[2] W. C. Elmore, 1948.</span></p>') in built


def test_references_need_an_id_each_and_once(tmp_path: Path) -> None:
    content_file = tmp_path / "content.html"
    deck = '<title>Deck</title><body data-author="R" data-meta="Lab"><ol class="references">{}</ol><section data-title="P"><p>x</p></section></body>'
    content_file.write_text(deck.format('<li id="a">A</li>'), encoding="utf-8")
    assert parse_template_content(content_file).references == {"a": "A"}
    for wrong, message in (('<li>A</li>', "li with an id"), ('<li id="a">A</li><li id="a">B</li>', "defined twice")):
        content_file.write_text(deck.format(wrong), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            parse_template_content(content_file)


def test_the_authoring_skeleton_keeps_its_lead_under_the_title(tmp_path: Path) -> None:
    from html_mcp_web.slides.build import build

    # The skeleton in the authoring guide carries a comment before its lead. Copied as it
    # is, the lead still stays with the title rather than joining the spread content.
    guide = (REPO / "templates" / "README.md").read_text(encoding="utf-8")
    skeleton = guide.split("```html\n", 1)[1].split("```", 1)[0]
    content = tmp_path / "content.html"
    content.write_text(skeleton, encoding="utf-8")
    build(content, tmp_path / "slides.html", REPO / "templates" / "neutral-slides")
    body = (tmp_path / "slides.html").read_text(encoding="utf-8").split('<div class="body" data-layout-guard>')[1]
    assert body.index('<p class="lead">Page introduction.</p>') < body.index('<div class="rest">')
