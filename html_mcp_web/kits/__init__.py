"""Artifact Kits: what every template builds a document from, whatever its layout.

A template decides where things sit on its page and nothing else. What a component is
(components.css), the code face, math, citations, the HTML of a figure's foreignObject,
wrapped svg labels and the document's language come from here, so the same content gives
the same result in a deck and in a report. A template calls prepare_body on each part of
its content, document_assets on the whole of it, and reads COMPONENTS before its own sheet.
"""

from __future__ import annotations

import base64
import html
import io
import re
from pathlib import Path

from ..template_content import ContentParser, Element

HERE = Path(__file__).parent
# What a component is, in the part that holds whatever page it sits on.
COMPONENTS = HERE / "components.css"
KATEX = HERE / "vendor" / "katex"
MONO = HERE / "vendor" / "noto-sans-mono"
# The faces a document in a CJK language sets its own script in, by language: the
# family's serif and sans, each a regular and a bold file. Only Korean is shipped.
CJK_FACES = {"ko": HERE / "vendor" / "noto-cjk-kr"}
CJK_FILES = (("Kit Serif CJK", "NotoSerifCJKkr"), ("Kit Sans CJK", "NotoSansCJKkr"))
GENERIC_FAMILIES = ("serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui")
# Breaks a <text data-wrap> or <text data-fit> label into lines with the document's font.
# The lines are chosen by TeX's algorithm, which comes with its own hyphenation patterns.
WRAP = HERE / "wrap.js"
# Sets a <text data-center> label or a <foreignObject data-center>'s HTML with the middle
# of its letters at the point the content gives.
CENTER = HERE / "center.js"
COLUMNS = HERE / "columns.js"
TEX_LINEBREAK = HERE / "vendor" / "tex-linebreak"


def inline_woff2(css: str, fonts_dir: Path) -> str:
    """Replace url(fonts/NAME.woff2) references with the file's data URI.

    A document then carries its own type: the same text wraps the same way on every machine
    that opens it, and the layout check, which runs on the review server's fonts, judges
    what the reader will actually see. Only woff2 is embedded; every browser this targets
    reads it, and the woff/ttf fallbacks some stylesheets list alongside are dropped.
    """
    def inline_font(match: re.Match) -> str:
        data = base64.b64encode((fonts_dir / match.group(1)).read_bytes()).decode()
        return f'url(data:font/woff2;base64,{data})'

    css = re.sub(r"url\((?:['\"])?fonts/([^)'\"]+\.woff2)(?:['\"])?\)", inline_font, css)
    return re.sub(r',\s*url\((?:[\'"])?fonts/[^)\'"]+\.(?:woff|ttf)(?:[\'"])?\)\s*format\("(?:woff|truetype)"\)', "", css)


# Delimiters auto-render recognises; a document that uses none of them gets no math bundle.
MATH_MARKERS = re.compile(r"\$[^$]|\\\(|\\\[")
MATH_SPANS = re.compile(r"(?<!\\)\$\$.+?(?<!\\)\$\$|(?<!\\)\$[^$]+?(?<!\\)\$|\\\(.+?\\\)|\\\[.+?\\\]", re.S)


def has_math(html_text: str) -> bool:
    return MATH_MARKERS.search(html_text) is not None


def check_svg_math(body_html: str) -> None:
    # The renderer puts HTML in place of a formula, and an svg <text> draws no HTML, so a
    # formula written there vanished without a trace. Inside the svg a <foreignObject>
    # holds HTML, and a formula in it renders like one in the body.
    if "<svg" not in body_html or not has_math(body_html):
        return
    body = ContentParser()
    body.feed(body_html)
    body.close()

    def visit(element: Element, in_svg: bool) -> None:
        for child in element.children:
            if not isinstance(child, Element) or child.tag == "foreignobject":
                continue
            if in_svg and child.tag == "text":
                found = MATH_SPANS.search(child.text())
                if found is not None:
                    raise ValueError(f'the formula "{found.group(0)}" in an svg <text> is not drawn; '
                                     "put it in a <foreignObject> inside the svg")
            visit(child, in_svg or child.tag == "svg")

    visit(body.root, False)


def check_svg_center(body_html: str) -> None:
    # data-center moves a label by the extent of its letters in its own font, read as one
    # run: a tspan set in another style, or lines broken by data-wrap or data-fit, would
    # be measured as letters they are not.
    if "data-center" not in body_html:
        return
    body = ContentParser()
    body.feed(body_html)
    body.close()
    for element in descendants(body.root):
        if "data-center" not in element.attributes:
            continue
        value = element.attributes["data-center"] or ""
        if element.tag not in ("text", "foreignobject") or value not in ("", "x", "y"):
            raise ValueError(f'data-center="{value}" on a <{element.tag}>: it is written on an svg <text> '
                             'or <foreignObject>, bare or as "x" or "y"')
        if element.tag != "text":
            continue
        if any(isinstance(child, Element) for child in element.children):
            raise ValueError(f'the label "{element.text().strip()}" with data-center holds markup; '
                             "a centred label is plain text in one style")
        if "data-wrap" in element.attributes or "data-fit" in element.attributes:
            raise ValueError(f'the label "{element.text().strip()}" has data-center with data-wrap or data-fit; '
                             "a centred label is one line")


def descendants(element: Element) -> list[Element]:
    found = []
    for child in element.children:
        if isinstance(child, Element):
            found.append(child)
            found.extend(descendants(child))
    return found


def lift_svg_html(body_html: str) -> str:
    # A figure's HTML, such as a formula, is written in a <foreignObject> of its svg. On a
    # scaled page Safari drew that HTML away from its place while the rest of the page
    # stood right, so the builder lifts it into a layer over the svg, which the document's
    # script places and scales to the viewBox. An unfilled rect marked data-html-slot
    # keeps its place in the drawing, so the drawing's extent stays what it was, and the
    # layout check takes it for no box a label sits on.
    if "<foreignobject" not in body_html.lower():
        return body_html
    body = ContentParser()
    body.feed(body_html)
    body.close()

    def number(element: Element, name: str, default: str | None = None) -> float:
        value = element.attributes.get(name, default)
        if value is None or not re.fullmatch(r"-?\d*\.?\d+", value.strip()):
            raise ValueError(f'a <foreignObject> needs a number for {name}, not "{value}"')
        return float(value)

    def lift(svg: Element) -> Element:
        if any(isinstance(inner, Element) and inner.tag == "foreignobject"
               for child in svg.children if isinstance(child, Element) for inner in descendants(child)):
            raise ValueError("a <foreignObject> sits directly in its <svg>, not inside a group")
        if svg.attributes.get("preserveaspectratio", "xMidYMid meet").strip() not in ("xMidYMid", "xMidYMid meet"):
            raise ValueError("an <svg> holding a <foreignObject> keeps the default preserveAspectRatio")
        view = svg.attributes.get("viewbox", "").replace(",", " ").split()
        if len(view) != 4:
            raise ValueError("an <svg> holding a <foreignObject> needs a viewBox")
        left, top, width, height = (float(value) for value in view)
        boxes = []
        for index, child in enumerate(svg.children):
            if not isinstance(child, Element) or child.tag != "foreignobject":
                continue
            x, y = number(child, "x", "0"), number(child, "y", "0")
            w, h = number(child, "width"), number(child, "height")
            svg.children[index] = Element("rect", {"x": f"{x:g}", "y": f"{y:g}", "width": f"{w:g}",
                                                   "height": f"{h:g}", "fill": "none", "data-html-slot": ""})
            box = {"class": "svg-html-box", "style":
                   f"left: {x - left:g}px; top: {y - top:g}px; width: {w:g}px; height: {h:g}px"}
            if "data-center" in child.attributes:
                box["data-center"] = child.attributes["data-center"] or ""
            boxes.append(Element("div", box, child.children))
        layer = Element("div", {"class": "svg-html-layer", "data-viewbox": f"{width:g} {height:g}",
                                "style": f"width: {width:g}px; height: {height:g}px"}, boxes)
        return Element("div", {"class": "svg-html"}, [svg, layer])

    def visit(element: Element, in_paragraph: bool) -> None:
        for index, child in enumerate(element.children):
            if not isinstance(child, Element):
                continue
            if child.tag == "svg":
                if any(isinstance(inner, Element) and inner.tag == "foreignobject" for inner in descendants(child)):
                    if in_paragraph:
                        raise ValueError("a figure holding a <foreignObject> stands outside a <p>")
                    element.children[index] = lift(child)
                continue
            visit(child, in_paragraph or child.tag == "p")

    visit(body.root, False)
    return body.root.inner_html()


def cite_references(body_html: str, references: dict[str, str], numbers: dict[str, int]) -> tuple[str, list[str]]:
    # A <cite> names one or more references by key, separated by commas, and becomes
    # their numbers in brackets. A reference takes its number where the document first
    # cites it, so numbers holds the numbering so far. Returns the content and the keys
    # this part cites, in number order. Inside an svg the numbers are a tspan: an HTML
    # span there ends the drawing where it stands when the browser reads the page.
    if "<cite" not in body_html:
        return body_html, []
    body = ContentParser()
    body.feed(body_html)
    body.close()
    cited: list[str] = []

    def visit(element: Element, in_svg: bool) -> None:
        for index, child in enumerate(element.children):
            if not isinstance(child, Element):
                continue
            if child.tag != "cite":
                visit(child, in_svg or child.tag == "svg")
                continue
            keys = [key.strip() for key in child.text().split(",")]
            for key in keys:
                if key not in references:
                    raise ValueError(f'<cite> names "{key}", which ol.references does not define')
                numbers.setdefault(key, len(numbers) + 1)
                if key not in cited:
                    cited.append(key)
            label = ", ".join(str(numbers[key]) for key in keys)
            element.children[index] = Element("tspan" if in_svg else "span", {"class": "cite"}, [f"[{label}]"])

    visit(body.root, False)
    return body.root.inner_html(), sorted(cited, key=numbers.__getitem__)


# Hangul syllables and jamo, kana, CJK ideographs and their punctuation and full-width forms.
CJK = "\u1100-\u11ff\u3000-\u303f\u3040-\u30ff\u3130-\u318f\u4e00-\u9fff\uac00-\ud7a3\uff00-\uffef"
# A run of everything else between spaces: Latin words, numbers with their points, slashes
# and hyphens, brackets and punctuation, entities included.
OTHER_RUN = re.compile(r"(?:&#?\w+;|[^\s" + CJK + r"])+")
UNMARKED = {"code", "pre", "svg", "script", "style", "math"}
OPENING = re.compile(r"(?<=[^\s(\[{]{2})(?=\()")


def mark_text(body_html: str, lang: str) -> str:
    # A browser hyphenates by the language of the text, and a Korean document's English
    # words, read as Korean, were never broken: a justified line in a narrow column put its
    # whole slack into a few spaces. In a Korean, Japanese or Chinese document every run
    # outside math and code that is not of those scripts, a Latin word, a number such as
    # 11/24 or 1.5, a bracket or a citation, is marked as English: it breaks as English,
    # and a justified line spreads its slack only around it, never between its letters,
    # which opened "(Figure 1c)" into single characters.
    # An opening parenthesis written against the word before it, as in "SGS-LoRA(Self",
    # gives no break there in Unicode's rules, and with Korean breaking only at spaces the
    # whole run had to stand on one line: a <wbr> before it lets the line end there.
    if lang.split("-")[0] not in {"ko", "ja", "zh"}:
        return body_html
    body = ContentParser()
    body.feed(body_html)
    body.close()

    def english(text: str) -> str:
        return "<wbr>".join(OTHER_RUN.sub(lambda m: f'<span lang="en">{m.group(0)}</span>', part)
                            for part in OPENING.split(text))

    def mark(text: str) -> str:
        pieces, start = [], 0
        for math in MATH_SPANS.finditer(text):
            pieces.append(english(text[start:math.start()]))
            pieces.append(math.group(0))
            start = math.end()
        pieces.append(english(text[start:]))
        return "".join(pieces)

    def visit(element: Element) -> None:
        children: list[Element | str] = []
        run: list[str] = []
        for child in [*element.children, None]:
            if isinstance(child, str) and not child.startswith("<!--"):
                run.append(child)
                continue
            if run:
                children.append(mark("".join(run)))
                run = []
            if isinstance(child, Element):
                if child.tag not in UNMARKED and "lang" not in child.attributes:
                    visit(child)
                children.append(child)
            elif child is not None:
                children.append(child)
        element.children = children

    visit(body.root)
    return body.root.inner_html()


def set_families(body_html: str, families: dict[str, str]) -> str:
    # A family is whatever face the reader's machine has under that name: a figure's
    # monospace label that fit its panel in the layout check's Firefox ran past the
    # panel's border and was cut in a reader's browser, which took a wider face. So every
    # family, in an svg font-family attribute or a style, is set in a face the layout
    # embeds, given in families: the first generic family in the list chooses it, and a
    # list of named faces only, such as matplotlib's mathtext, takes sans-serif. A generic
    # family the layout does not embed stops the build. A presentation attribute takes no
    # var(), so the face goes to the style.
    if "font-family" not in body_html:
        return body_html
    body = ContentParser()
    body.feed(body_html)
    body.close()

    def face(value: str) -> str:
        names = [name.strip().strip("'\"").lower() for name in value.split(",") if name.strip()]
        generic = next((name for name in names if name in GENERIC_FAMILIES), "sans-serif")
        if generic not in families:
            raise ValueError(f'font-family "{value.strip()}": a page sets its text in the faces it embeds, '
                             f"and this layout embeds one for {', '.join(families)}")
        return families[generic]

    for element in descendants(body.root):
        style = element.attributes.get("style") or ""
        style = re.sub(r"font-family\s*:\s*([^;]+)", lambda match: f"font-family: {face(match.group(1))}", style)
        if "font-family" in element.attributes:
            style = f"font-family: {face(element.attributes.pop('font-family'))}" + (f"; {style}" if style else "")
        if style:
            element.attributes["style"] = style
    return body.root.inner_html()


def prepare_body(body_html: str, references: dict[str, str], numbers: dict[str, int],
                 lang: str, families: dict[str, str]) -> tuple[str, list[str]]:
    """One part of the content made ready for any page: its citations numbered, its svg
    formulas checked, its families set in the layout's faces, its figures' HTML lifted
    and, in a CJK document, its English words marked and its parentheses given a break.
    Returns the HTML and the keys it cites."""
    check_svg_math(body_html)
    check_svg_center(body_html)
    body_html = set_families(body_html, families)
    body_html, cited = cite_references(body_html, references, numbers)
    return mark_text(lift_svg_html(body_html), lang), cited


# The layer of a figure's lifted HTML is drawn in the svg's own units, as its
# foreignObject was: it takes the scale and offset the default viewBox fit gives the
# svg inside its box. Both are measured in layout pixels, so a transform scaling the
# whole page, the deck's or the viewer's, applies to the layer once, like the svg. The
# box is measured again when its size changes, which a page that was not drawn gets.
SVG_HTML_SCRIPT = """<script>
(() => {
  const place = (layer) => {
    const holder = layer.parentElement;
    const svg = holder.firstElementChild;
    if (holder.offsetWidth === 0) return;
    const [width, height] = layer.dataset.viewbox.split(" ").map(Number);
    const outer = holder.getBoundingClientRect();
    const zoom = outer.width / holder.offsetWidth;
    const box = svg.getBoundingClientRect();
    const w = box.width / zoom, h = box.height / zoom;
    const k = Math.min(w / width, h / height);
    const x = (box.left - outer.left) / zoom + (w - width * k) / 2;
    const y = (box.top - outer.top) / zoom + (h - height * k) / 2;
    layer.style.transform = `translate(${x}px, ${y}px) scale(${k})`;
  };
  const sized = new ResizeObserver((entries) => entries.forEach((entry) => place(entry.target.lastElementChild)));
  const setup = (root) => root.querySelectorAll(".svg-html-layer").forEach((layer) => { place(layer); sized.observe(layer.parentElement); });
  setup(document);
  (window.htmlMcpPageSetup ??= []).push(setup);
})();
</script>"""


def mono_face(html_text: str) -> str:
    """The code face, embedded when the document sets code. Left to the system, Firefox
    drew code in a Korean document in a CJK face half an em wide per letter while Chrome
    and Safari drew 0.6 em, so the layout check passed lines that ran out of their box on
    the reader's screen. Every browser now draws the one face it measures."""
    if "<pre" not in html_text and "<code" not in html_text and "var(--mono)" not in html_text:
        return ""
    faces = "".join(
        f'@font-face {{ font-family: "Deck Mono"; font-weight: {weight}; '
        f'src: url(fonts/NotoSansMono-{name}.woff2) format("woff2"); }}\n'
        for weight, name in ((400, "Regular"), (700, "Bold")))
    return f"\n  <style>\n{inline_woff2(faces, MONO)}  </style>"


def cjk_faces(html_text: str, lang: str) -> str:
    """The CJK faces of a document in a CJK language, subset to the characters it uses and
    embedded, under the names the layouts put after their Latin faces: "Kit Serif CJK" and
    "Kit Sans CJK". Left to the reader's system, Hangul was set in whatever Korean face a
    machine had, the layout check's UnBatang on the server and another on the reader's
    Mac, and the lines broke differently on each, so a short last line the reader saw was
    not there in the check."""
    folder = CJK_FACES.get(lang.split("-")[0])
    if folder is None:
        return ""
    from fontTools import subset
    from fontTools.ttLib import TTFont

    used = {ord(character) for character in html.unescape(html_text)}
    faces = []
    for family, stem in CJK_FILES:
        for weight, name in ((400, "Regular"), (700, "Bold")):
            font = TTFont(folder / f"{stem}-{name}.woff2")
            options = subset.Options()
            options.flavor = "woff2"
            options.layout_features = ["*"]
            subsetter = subset.Subsetter(options)
            subsetter.populate(unicodes=used & set(font.getBestCmap()))
            subsetter.subset(font)
            buffer = io.BytesIO()
            font.save(buffer)
            data = base64.b64encode(buffer.getvalue()).decode("ascii")
            faces.append(f'@font-face {{ font-family: "{family}"; font-weight: {weight}; '
                         f'src: url(data:font/woff2;base64,{data}) format("woff2"); }}\n')
    return "\n  <style>\n" + "".join(faces) + "  </style>"


def math_bundle() -> tuple[str, str]:
    """KaTeX for the head and the foot, everything inlined so the file opens offline.

    Fonts go into the stylesheet as data URIs; the woff and ttf fallbacks the upstream
    CSS also lists are dropped, since every browser this targets reads woff2. Rendering
    runs synchronously at the end of the body, before load fires, so a print snapshot
    taken after load already sees the rendered math.
    """
    css = inline_woff2((KATEX / "katex.min.css").read_text(encoding="utf-8"), KATEX / "fonts")
    # Math against its text is the layout's to size, through --math-scale in components.css.
    head = f"\n  <style>\n{css}\n.katex {{ font-size: var(--math-scale); }}\n  </style>"
    foot = (
        "\n  <script>" + (KATEX / "katex.min.js").read_text(encoding="utf-8") + "</script>"
        "\n  <script>" + (KATEX / "auto-render.min.js").read_text(encoding="utf-8") + "</script>"
        "\n  <script>(() => {\n  const options = {delimiters: ["
        "{left: '$$', right: '$$', display: true}, {left: '\\\\[', right: '\\\\]', display: true}, "
        "{left: '$', right: '$', display: false}, {left: '\\\\(', right: '\\\\)', display: false}], "
        "throwOnError: false};\n  renderMathInElement(document.body, options);\n"
        "  (window.htmlMcpPageSetup ??= []).push((root) => renderMathInElement(root, options));\n})();</script>"
    )
    return head, foot


def document_assets(html_text: str, lang: str) -> tuple[str, str]:
    """What a document carries besides its own markup, for the head and for the end of the
    body: the CJK faces, the code face, KaTeX, the placing of lifted figure HTML, the svg label wrapper,
    the centring of labels and the sharing of a table's width, each only when the document uses it. Every template ends its document with
    the same scripts in the same order, so math and figures come out the same in each."""
    math_head, math_foot = math_bundle() if has_math(html_text) else ("", "")
    wraps = "data-wrap=" in html_text or "data-fit=" in html_text
    wrap = "".join(
        "\n  <script>" + path.read_text(encoding="utf-8") + "</script>"
        for path in (TEX_LINEBREAK / "lib.js", TEX_LINEBREAK / "hyphens_en-us.js", WRAP)) if wraps else ""
    svg_html = SVG_HTML_SCRIPT if "svg-html-layer" in html_text else ""
    center = "\n  <script>" + CENTER.read_text(encoding="utf-8") + "</script>" if "data-center" in html_text else ""
    columns = "\n  <script>" + COLUMNS.read_text(encoding="utf-8") + "</script>" if "<table" in html_text else ""
    return cjk_faces(html_text, lang) + mono_face(html_text) + math_head, math_foot + wrap + svg_html + center + columns
