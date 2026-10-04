"""Compile a content file into self-contained slides with a skin.

Usage: python -m html_mcp_web.slides <content.html> <slides.html> --skin <dir>

Components come from components.css, which a report is built from too; where they sit
on a 1280x720 page comes from skeleton.css, wrap.js and this module. A skin directory
supplies:

    skin.css     variable overrides and chrome styling (required)
    skin.json    chrome slots and footer labels (optional)
    assets/      images the slots refer to (optional)

skin.json keys, all optional:

    "font_links":   list of <link> or <style> tags to add to <head>
    "footer_label": text at the right of the footer bar on body pages
    "cover_footer_label": text at the right of the cover's footer bar
    "chrome": {slot: image} where image is a filename under assets/ and slot is one of
        cover_band_left      image over the cover band's left area
        cover_band_right     image in the cover band's right area
        cover_band_ornament  image at the cover band's top right
        cover_bottom_left    images stacked at the cover's bottom left (list allowed)
        tbar_logo            image at the right of the title bar
        page_bottom_left     images stacked at a body page's bottom left (list allowed)
        full_bottom_left     same, on full-bleed pages (defaults to page_bottom_left)
        full_art             image filling a full-bleed page behind its content

Images are embedded as data URIs so the output opens anywhere.
"""

import argparse
import base64
import io
import json
import re
import sys
from pathlib import Path

from ..template_content import ContentParser, Element, parse_template_content

HERE = Path(__file__).parent
SKELETON = HERE / "skeleton.css"
# What a component is, which a report is built from too; the skeleton says where it sits
# on a 1280x720 page.
COMPONENTS = HERE.parent / "components.css"
# Breaks a <text data-wrap> or <text data-fit> label into lines with the skin's font, in
# the deck; a deck with no such label carries none of it. The lines are chosen by TeX's
# algorithm, which comes with its own hyphenation patterns.
WRAP = HERE / "wrap.js"
TEX_LINEBREAK = HERE / "vendor" / "tex-linebreak"

# A page is 1280x720 and the file may be opened in a window narrower than that. The
# skeleton scales it by --deck-fit; only the number needs measuring, and only when the
# deck stands on its own: the review viewer marks the document and fits it itself, and
# the pptx export lays the page out at its full size, so both leave the factor at 1.
FIT_SCRIPT = """<script>
(() => {
  const root = document.documentElement;
  if (root.hasAttribute("data-html-mcp-layout")) return;
  const fit = () => root.style.setProperty(
    "--deck-fit", String(Math.min(1, (root.clientWidth - 24) / 1280)));
  addEventListener("resize", fit);
  fit();
})();
</script>"""

# Widths the embedded images are downscaled to; a slot only needs what its box shows.
SLOT_WIDTHS = {
    "cover_band_left": 500,
    "cover_band_right": 500,
    "cover_band_ornament": 300,
    "cover_bottom_left": 300,
    "tbar_logo": 340,
    "page_bottom_left": 300,
    "full_bottom_left": 300,
    "full_art": 1280,
}


def data_uri(path: Path, width: int) -> str:
    from PIL import Image

    image = Image.open(path).convert("RGBA")
    image.thumbnail((width, width))
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def inline_woff2(css: str, fonts_dir: Path) -> str:
    """Replace url(fonts/NAME.woff2) references with the file's data URI.

    A deck then carries its own type: the same text wraps the same way on every machine
    that opens it, and the layout check, which runs on the review server's fonts, judges
    what the reader will actually see. Only woff2 is embedded; every browser this targets
    reads it, and the woff/ttf fallbacks some stylesheets list alongside are dropped.
    """
    def inline_font(match: re.Match) -> str:
        data = base64.b64encode((fonts_dir / match.group(1)).read_bytes()).decode()
        return f'url(data:font/woff2;base64,{data})'

    css = re.sub(r"url\((?:['\"])?fonts/([^)'\"]+\.woff2)(?:['\"])?\)", inline_font, css)
    return re.sub(r',\s*url\((?:[\'"])?fonts/[^)\'"]+\.(?:woff|ttf)(?:[\'"])?\)\s*format\("(?:woff|truetype)"\)', "", css)


class Skin:
    def __init__(self, directory: Path):
        self.directory = directory
        self.css = inline_woff2((directory / "skin.css").read_text(encoding="utf-8"), directory / "fonts")
        config_path = directory / "skin.json"
        self.config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
        self._images: dict[str, str] = {}

    def label(self, key: str) -> str:
        return self.config.get(key, "")

    def head_extra(self) -> str:
        return "\n".join(self.config.get("font_links", []))

    def slot(self, name: str) -> list[str]:
        """Data URIs for the images a slot holds; empty when the skin leaves it unfilled."""
        chrome = self.config.get("chrome", {})
        if name not in chrome:
            if name == "full_bottom_left" and "page_bottom_left" in chrome:
                return self.slot("page_bottom_left")
            return []
        names = chrome[name]
        if isinstance(names, str):
            names = [names]
        uris = []
        for image_name in names:
            if image_name not in self._images:
                self._images[image_name] = data_uri(self.directory / "assets" / image_name, SLOT_WIDTHS[name])
            uris.append(self._images[image_name])
        return uris


KATEX = HERE / "vendor" / "katex"
# Delimiters auto-render recognises; a deck that uses none of them gets no math bundle.
MATH_MARKERS = re.compile(r"\$[^$]|\\\(|\\\[")


def has_math(html_text: str) -> bool:
    return MATH_MARKERS.search(html_text) is not None


def math_bundle() -> tuple[str, str]:
    """KaTeX for the head and the foot, everything inlined so the file opens offline.

    Fonts go into the stylesheet as data URIs; the woff and ttf fallbacks the upstream
    CSS also lists are dropped, since every browser this targets reads woff2. Rendering
    runs synchronously at the end of the body, before load fires, so a print snapshot
    taken after load already sees the rendered math.
    """
    css = inline_woff2((KATEX / "katex.min.css").read_text(encoding="utf-8"), KATEX / "fonts")
    head = f"\n  <style>\n{css}\n  </style>"
    foot = (
        "\n  <script>" + (KATEX / "katex.min.js").read_text(encoding="utf-8") + "</script>"
        "\n  <script>" + (KATEX / "auto-render.min.js").read_text(encoding="utf-8") + "</script>"
        "\n  <script>renderMathInElement(document.body, {delimiters: ["
        "{left: '$$', right: '$$', display: true}, {left: '\\\\[', right: '\\\\]', display: true}, "
        "{left: '$', right: '$', display: false}, {left: '\\\\(', right: '\\\\)', display: false}], "
        "throwOnError: false});</script>"
    )
    return head, foot


def images(uris: list[str], class_name: str) -> str:
    return "".join(f'<img class="{class_name}" src="{uri}" alt="">' for uri in uris)


def stack(uris: list[str], class_name: str) -> str:
    if not uris:
        return ""
    inner = "".join(f'<img src="{uri}" alt="">' for uri in uris)
    # Chrome stacked in a page corner is marked so the layout check keeps text off it.
    return f'<div class="{class_name}" data-layout-keepout>{inner}</div>'


def label_html(text: str) -> str:
    return f'<span class="bbar-label">{text}</span>' if text else ""


def script_block(script_html: str) -> str:
    # A script rides directly after its page in the flow, so the browser keeps the two
    # together at any window size without a line of positioning code.
    if not script_html:
        return ""
    return f'\n    <div class="script-block">\n      <div class="script-text">{script_html}</div>\n    </div>'


def contents_list(body_html: str, count: str | None) -> tuple[str, int]:
    # A contents item may end in a ul of unnumbered sub-items. Its own text goes into
    # span.entry and the item is marked has-sub, so skeleton.css can set the sub-list
    # under that text beside whatever number the skin draws. Sub-items make a list long
    # and narrow, leaving the right of the page empty, so a list with sub-items under two
    # or more outer items takes two columns. count, from data-columns, overrides that.
    # Returns the list and its column count.
    body = ContentParser()
    body.feed(body_html)
    body.close()
    items = [item for listing in body.root.children if isinstance(listing, Element) and listing.tag == "ol"
             for item in listing.children if isinstance(item, Element)]
    nested = []
    for item in items:
        lists = [index for index, child in enumerate(item.children)
                 if isinstance(child, Element) and child.tag in ("ul", "ol")]
        if not lists:
            continue
        at = lists[0]
        tail = item.children[at + 1:]
        if item.children[at].tag != "ul" or any(not isinstance(child, str) or child.strip() for child in tail):
            raise ValueError("a contents item takes one ul of sub-items after its own text")
        classes = item.attributes["class"].split() if "class" in item.attributes else []
        item.attributes["class"] = " ".join(["has-sub", *classes])
        item.children = [Element("span", {"class": "entry"}, item.children[:at]), item.children[at]]
        nested.append(item)
    columns = 2 if nested and len(items) > 1 else 1
    if count is not None:
        if not re.fullmatch(r"[1-9]", count.strip()):
            raise ValueError(f'a contents data-columns is a whole number from 1 to 9, not "{count.strip()}"')
        columns = int(count)
    if columns > 1:
        # In a column the skin's one-line item would wrap piece by piece, so the text of
        # every item becomes one span.entry beside its number.
        for item in items:
            if all(item is not other for other in nested):
                item.children = [Element("span", {"class": "entry"}, item.children)]
    return body.root.inner_html(), columns


def cite_references(body_html: str, references: dict[str, str], numbers: dict[str, int]) -> tuple[str, list[str]]:
    # A <cite> names one or more references by key, separated by commas, and becomes
    # their numbers in brackets. A reference takes its number where the deck first cites
    # it, so numbers holds the deck's numbering so far. Returns the content and the keys
    # this page cites, in number order.
    if "<cite" not in body_html:
        return body_html, []
    body = ContentParser()
    body.feed(body_html)
    body.close()
    cited: list[str] = []

    def visit(element: Element) -> None:
        for index, child in enumerate(element.children):
            if not isinstance(child, Element):
                continue
            if child.tag != "cite":
                visit(child)
                continue
            keys = [key.strip() for key in child.text().split(",")]
            for key in keys:
                if key not in references:
                    raise ValueError(f'<cite> names "{key}", which ol.references does not define')
                numbers.setdefault(key, len(numbers) + 1)
                if key not in cited:
                    cited.append(key)
            label = ", ".join(str(numbers[key]) for key in keys)
            element.children[index] = Element("span", {"class": "cite"}, [f"[{label}]"])

    visit(body.root)
    return body.root.inner_html(), sorted(cited, key=numbers.__getitem__)


def build(content_path: Path, out_path: Path, skin_dir: Path) -> None:
    content = parse_template_content(content_path)
    skin = Skin(skin_dir)
    # An appendix is opened when a question calls for it, so the pages an audience is
    # told to expect stop before it. The section carrying data-appendix opens it and the
    # rest of the deck belongs to it; those pages count as A1, A2 and so on, since a page
    # after the total ("16 / 15") reads as a mistake and a page with no number at all
    # leaves the speaker no way to say which one to open.
    appendix_at = next((index for index, section in enumerate(content.sections)
                        if "data-appendix" in section.attributes), None)
    page_count = (len(content.sections) if appendix_at is None else appendix_at) + 1
    appendix_count = 0 if appendix_at is None else len(content.sections) - appendix_at
    metadata_html = "<br>\n        ".join(content.metadata)

    subtitle_html = f'<div class="sub">{content.subtitle}</div>' if content.subtitle else ""
    cover_class = "page cover has-sub" if content.subtitle else "page cover"
    cover_footer_label = skin.label("cover_footer_label")
    pages = [f'''    <section class="{cover_class}">
      <div class="band">{images(skin.slot("cover_band_ornament"), "band-ornament")}{images(skin.slot("cover_band_left"), "band-left")}
        <h1>{content.title}</h1>
        {subtitle_html}{images(skin.slot("cover_band_right"), "band-right")}
      </div>
      <div class="who">{content.author}</div>
      <div class="aff">{metadata_html}</div>
      {stack(skin.slot("cover_bottom_left"), "cover-bottom-left")}
      <footer class="bbar"><span class="pageno">1 / {page_count}</span>{label_html(cover_footer_label)}</footer>
    </section>{script_block(content.cover_script_html)}''']

    footer_label = skin.label("footer_label")
    # A citation is numbered on the page that shows it and listed in that page's line.
    numbers: dict[str, int] = {}
    misplaced = "a <cite> belongs in the content of a body page, not in a script or another page kind"
    if "<cite" in content.cover_script_html:
        raise ValueError(misplaced)
    for page_number, section in enumerate(content.sections, 2):
        if "<cite" in section.script_html or (section.layout != "body" and "<cite" in section.body_html):
            raise ValueError(misplaced)
        script = script_block(section.script_html)
        in_appendix = appendix_at is not None and page_number - 2 >= appendix_at
        counted = (f"A{page_number - 2 - appendix_at + 1} / A{appendix_count}" if in_appendix
                   else f"{page_number} / {page_count}")
        pageno = f'<span class="pageno">{counted}</span>'
        if section.layout in ("contents", "divider"):
            footer = f'<footer class="bbar">{pageno}</footer>'
            art = images(skin.slot("full_art"), "full-art")
            bottom = stack(skin.slot("full_bottom_left"), "page-bottom-left")
            kind = section.layout
            if section.layout == "contents":
                heading = f"<h2>{section.title}</h2>\n        <div class=\"rule\"></div>" if section.title else ""
                listing, columns = contents_list(section.body_html, section.attributes.get("data-columns"))
                classes, style = ["wide"], []
                # data-scale sizes the list, numbers and sub-items included, in any skin.
                if "data-scale" in section.attributes:
                    scale = section.attributes["data-scale"].strip()
                    if not re.fullmatch(r"\d*\.?\d+", scale) or float(scale) == 0:
                        raise ValueError(f'a contents data-scale is a positive number such as "0.8", not "{scale}"')
                    classes.append("scaled")
                    style.append(f"--contents-scale: {scale}")
                    listing = f'<div class="list">{listing}</div>'
                if columns > 1:
                    classes.append("columns")
                    style.append(f"--contents-columns: {columns}")
                    kind = "contents columns"
                styled = f' style="{"; ".join(style)}"' if style else ""
                inner = f'''      <div class="{" ".join(classes)}" data-layout-guard{styled}>
        {heading}
{listing}
      </div>'''
            else:
                body_html = section.body_html
                shot = ""
                match = re.search(r'<img class="shot"[^>]*>', body_html)
                if match is not None:
                    shot = f"\n        {match.group(0)}"
                    body_html = body_html.replace(match.group(0), "")
                number = section.attributes.get("data-no", "").strip()
                number_html = f'<span class="no">{number}</span>' if number else ""
                inner = f'''      <div class="wide" data-layout-guard>
        <div class="cap">{number_html}
{body_html.strip()}
        </div>{shot}
      </div>'''
            pages.append(f'''    <section class="page {kind}">
      <div class="page-ground"></div>{art}
{inner}
      {bottom}
      {footer}
    </section>{script}''')
            continue

        # Opening and closing summaries bound the body; only the content between them
        # shares the remaining height. The closing summary uses the skin's lead styling.
        content_html, cited = cite_references(section.body_html, content.references, numbers)
        lead = re.match(r'\s*<p class="lead">.*?</p>', content_html, re.S)
        opening = lead.group(0).strip() if lead is not None else ""
        rest = content_html[lead.end():] if lead is not None else content_html
        body = ContentParser()
        body.feed(rest)
        body.close()
        blocks = [child for child in body.root.children if isinstance(child, Element)]
        takeaways = [child for child in blocks
                     if "class" in child.attributes and "takeaway" in child.attributes["class"].split()]
        takeaway = ""
        if takeaways:
            if len(takeaways) != 1 or takeaways[0] is not blocks[-1] or takeaways[0].tag != "p":
                raise ValueError("a body takeaway must be one final p.takeaway")
            closing = takeaways[0]
            classes = closing.attributes["class"].split()
            if "lead" not in classes:
                classes.insert(0, "lead")
            closing.attributes["class"] = " ".join(classes)
            takeaway = closing.to_html()
            rest = body.root.inner_html({id(closing)})
        refs = ""
        if cited:
            entries = "".join(f"<span>[{numbers[key]}] {content.references[key]}</span>" for key in cited)
            refs = f'\n<p class="refs">{entries}</p>'
        footer = f'<footer class="bbar">{pageno}{label_html(footer_label)}</footer>'
        pages.append(f'''    <section class="page">
      <header class="tbar" data-layout-bar><h2>{section.title}</h2>{images(skin.slot("tbar_logo"), "tbar-logo")}</header>
      <div class="body" data-layout-guard>
{opening}
        <div class="rest">
{rest.strip()}
        </div>
{takeaway}{refs}
      </div>
      {stack(skin.slot("page_bottom_left"), "page-bottom-left")}
      {footer}
    </section>{script}''')

    body_html = chr(10).join(pages)
    math = math_bundle() if has_math(body_html) else ("", "")
    wraps = "data-wrap=" in body_html or "data-fit=" in body_html
    wrap = "".join(
        "\n  <script>" + path.read_text(encoding="utf-8") + "</script>"
        for path in (TEX_LINEBREAK / "lib.js", TEX_LINEBREAK / "hyphens_en-us.js", WRAP)) if wraps else ""
    document = f'''<!doctype html>
<html lang="{skin.label("lang") or "en"}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{content.title}</title>
  {skin.head_extra()}
  <style>
{COMPONENTS.read_text(encoding="utf-8")}
{SKELETON.read_text(encoding="utf-8")}
/* ---- skin: {skin_dir.name} ---- */
{skin.css}
  </style>{math[0]}
</head>
<body>
  <main class="pages">

{body_html}

  </main>{math[1]}{wrap}
{FIT_SCRIPT}
</body>
</html>
'''
    # Two builds run concurrently: the watcher's on a content save, and a by-hand one. A
    # plain write truncates first, so the other build's stat read 0KB off a file that was
    # complete a moment later. The swap is atomic and the report counts what was written,
    # not what a stat happens to catch.
    staging = out_path.with_name(out_path.name + ".building")
    staging.write_text(document, encoding="utf-8")
    staging.replace(out_path)
    scripts = sum(1 for section in content.sections if section.script_html) + bool(content.cover_script_html)
    print(f"{out_path}: cover + {len(content.sections)} slides, {scripts} scripts, "
          f"{len(document.encode('utf-8')) // 1024}KB")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m html_mcp_web.slides", description=__doc__.split("\n\n")[0])
    parser.add_argument("content", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--skin", type=Path, required=True, help="skin directory holding skin.css")
    args = parser.parse_args(argv)
    if not (args.skin / "skin.css").is_file():
        sys.exit(f"skin has no skin.css: {args.skin}")
    build(args.content, args.output, args.skin)


if __name__ == "__main__":
    main()
