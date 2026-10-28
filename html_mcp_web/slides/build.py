"""Compile a content file into self-contained slides with a skin.

Usage: python -m html_mcp_web.slides <content.html> <slides.html> --skin <dir>

What a component is, and math, citations and figures, come from html_mcp_web.kits, which
a report is built from too; where they sit on a 1280x720 page comes from skeleton.css
and this module. A skin directory
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
import os
import re
import sys
from pathlib import Path

from ..kits import COMPONENTS, check_svg_math, document_assets, inline_woff2, prepare_body
from ..template_content import ContentParser, Element, parse_template_content

HERE = Path(__file__).parent
SKELETON = HERE / "skeleton.css"

# A page is 1280x720 and the file may be opened in a window narrower than that. The
# skeleton scales it by --deck-fit; only the number needs measuring, and only when the
# deck stands on its own: the review viewer marks the document and fits it itself, and
# the pptx export lays the page out at its full size, so both leave the factor at 1.
#
# Every script of the deck also leaves in htmlMcpPageSetup what it does to one page. The
# review viewer puts an edited page in place of the old one rather than loading the deck
# again, and sets the new page up with these. The list being there tells the viewer that
# the deck's scripts all do so.
FIT_SCRIPT = """<script>
window.htmlMcpPageSetup ??= [];
(() => {
  const root = document.documentElement;
  if (root.hasAttribute("data-html-mcp-layout")) return;
  const fit = () => root.style.setProperty(
    "--deck-fit", String(Math.min(1, (root.clientWidth - 24) / 1280)));
  addEventListener("resize", fit);
  fit();
})();
</script>"""

# A contents list with sub-items takes two columns only when one column overflows its
# area, which only the page can tell, in the skin's own type. Two columns for a list
# that fit in one set three items as two and one, the third beside the first and the
# lower half of the page empty. The area is measured again when fonts arrive and when a
# page that was not drawn gets a size; its own size does not change with its columns.
CONTENTS_FIT_SCRIPT = """<script>
(() => {
  const fit = (area) => {
    if (area.clientHeight === 0) return;
    const page = area.closest("section");
    area.classList.remove("columns");
    page.classList.remove("columns");
    if (area.scrollHeight <= area.clientHeight + 1) return;
    area.classList.add("columns");
    page.classList.add("columns");
  };
  const areas = (root) => root.querySelectorAll("[data-contents-fit]");
  const sized = new ResizeObserver((entries) => entries.forEach((entry) => fit(entry.target)));
  const setup = (root) => areas(root).forEach((area) => { fit(area); sized.observe(area); });
  setup(document);
  const all = () => areas(document).forEach(fit);
  document.fonts.ready.then(all);
  document.fonts.addEventListener("loadingdone", all);
  (window.htmlMcpPageSetup ??= []).push(setup);
})();
</script>"""

# A box that spreads its blocks over its height (the body's rest, a column of .two) took a
# notes list as one block: the room collected above and below it, far from the heading it
# belongs to, while its items stayed packed. The room now goes first between the items of
# the lists directly in the box, up to one line each, and only what is left is spread
# around the blocks. Only the page can tell the room, in the skin's own type, so it is
# measured again when fonts arrive, when the box or one of its other blocks changes size,
# and when the page has loaded its pictures.
NOTES_SPREAD_SCRIPT = """<script>
(() => {
  const BOXES = ".body > .rest, .two > div";
  // An item's own gap, as its author set it, which the spread adds to and goes back to.
  const authored = new WeakMap();
  const spread = (box) => {
    const lists = Array.from(box.children).filter((child) => child.matches("ul.notes"));
    const items = lists.map((list) => Array.from(list.children).filter((child) => child.tagName === "LI"));
    for (const item of items.flat()) {
      if (!authored.has(item)) authored.set(item, item.style.marginBottom);
      item.style.marginBottom = authored.get(item);
    }
    const gaps = items.reduce((sum, members) => sum + Math.max(0, members.length - 1), 0);
    if (gaps === 0 || box.offsetHeight === 0) return;
    // Heights in the page's own pixels: an svg has no offsetHeight, so each block is measured
    // as drawn and the scale of the page, the deck's or the viewer's, taken back out.
    const scale = box.getBoundingClientRect().height / box.offsetHeight;
    const style = getComputedStyle(box);
    let used = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
    for (const child of box.children) {
      const own = getComputedStyle(child);
      if (own.display === "none" || own.position === "absolute" || own.position === "fixed") continue;
      used += child.getBoundingClientRect().height / scale + parseFloat(own.marginTop) + parseFloat(own.marginBottom);
    }
    const room = box.clientHeight - used;
    if (room <= 0) return;
    lists.forEach((list, at) => {
      const own = getComputedStyle(list);
      const line = parseFloat(own.lineHeight) || parseFloat(own.fontSize) * 1.2;
      const extra = Math.min(line, room / gaps);
      for (const item of items[at].slice(0, -1)) {
        item.style.marginBottom = `${parseFloat(getComputedStyle(item).marginBottom) + extra}px`;
      }
    });
  };
  const boxes = (root) => Array.from(root.querySelectorAll(BOXES))
    .filter((box) => Array.from(box.children).some((child) => child.matches("ul.notes")));
  // The lists are not watched: their height is what the spread sets.
  const sized = new ResizeObserver((entries) => {
    new Set(entries.map((entry) => entry.target.closest(BOXES) ?? entry.target)).forEach(spread);
  });
  const setup = (root) => boxes(root).forEach((box) => {
    spread(box);
    sized.observe(box);
    Array.from(box.children).filter((child) => !child.matches("ul.notes")).forEach((child) => sized.observe(child));
  });
  setup(document);
  const all = () => boxes(document).forEach(spread);
  document.fonts.ready.then(all);
  document.fonts.addEventListener("loadingdone", all);
  addEventListener("load", all);
  (window.htmlMcpPageSetup ??= []).push(setup);
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
    """A skin image at the slot's width. Scaling and encoding the skin's images was the
    larger part of every build, so each result is kept per source file (path, size, mtime)
    and width under the user's cache directory."""
    import hashlib

    stat = path.stat()
    key = hashlib.sha256(f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{width}".encode("utf-8")).hexdigest()
    cache = Path.home() / ".cache" / "html-mcp-web" / "skin-images" / f"{key}.txt"
    if cache.is_file():
        return cache.read_text(encoding="ascii")
    from PIL import Image

    image = Image.open(path).convert("RGBA")
    image.thumbnail((width, width))
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    # Two builds can run at once, so the entry is written whole and then put in place.
    cache.parent.mkdir(parents=True, exist_ok=True)
    staging = cache.with_name(f"{cache.name}.{os.getpid()}")
    staging.write_text(uri, encoding="ascii")
    staging.replace(cache)
    return uri


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


def contents_list(body_html: str, count: str | None) -> tuple[str, int | None]:
    # A contents item may end in a ul of unnumbered sub-items. Its own text goes into
    # span.entry and the item is marked has-sub, so skeleton.css can set the sub-list
    # under that text beside whatever number the skin draws. Sub-items make a list long,
    # and one with two or more outer items takes two columns when one column overflows,
    # which the page decides. count, from data-columns, names the count instead. Returns
    # the list and its column count, None when the page decides. The numbers come from a
    # CSS counter, which an ol's start attribute does not move, so a list continued on a
    # second contents page with start="3" has its counter set to begin there.
    body = ContentParser()
    body.feed(body_html)
    body.close()
    for listing in body.root.children:
        if not isinstance(listing, Element) or listing.tag != "ol" or "start" not in listing.attributes:
            continue
        start = listing.attributes["start"].strip()
        if not re.fullmatch(r"[1-9]\d*", start):
            raise ValueError(f'a contents <ol start> is a whole number from 1, not "{start}"')
        style = listing.attributes.get("style", "").strip().rstrip(";")
        listing.attributes["style"] = (f"{style}; " if style else "") + f"counter-reset: item {int(start) - 1}"
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
    columns = None if nested and len(items) > 1 else 1
    if count is not None:
        if not re.fullmatch(r"[1-9]", count.strip()):
            raise ValueError(f'a contents data-columns is a whole number from 1 to 9, not "{count.strip()}"')
        columns = int(count)
    if columns is None or columns > 1:
        # In a column the skin's one-line item would wrap piece by piece, so the text of
        # every item becomes one span.entry beside its number.
        for item in items:
            if all(item is not other for other in nested):
                item.children = [Element("span", {"class": "entry"}, item.children)]
    return body.root.inner_html(), columns


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
        check_svg_math(section.body_html)
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
                fit = ""
                if columns is None:
                    style.append("--contents-columns: 2")
                    fit = " data-contents-fit"
                elif columns > 1:
                    classes.append("columns")
                    style.append(f"--contents-columns: {columns}")
                    kind = "contents columns"
                styled = f' style="{"; ".join(style)}"' if style else ""
                inner = f'''      <div class="{" ".join(classes)}" data-layout-guard{fit}{styled}>
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
                cap_class = "cap numbered" if number else "cap"
                inner = f'''      <div class="wide" data-layout-guard>
        <div class="{cap_class}">{number_html}
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
        content_html, cited = prepare_body(section.body_html, content.references, numbers)
        # Comments before the lead, such as the skeleton's note on it, do not hide it.
        lead = re.match(r'\s*(?:<!--.*?-->\s*)*<p class="lead">.*?</p>', content_html, re.S)
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
    assets = document_assets(body_html)
    notes = NOTES_SPREAD_SCRIPT if re.search(r'<ul class="[^"]*\bnotes\b', body_html) else ""
    document = f'''<!doctype html>
<html lang="{content.lang}">
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
  </style>{assets[0]}
</head>
<body>
  <main class="pages">

{body_html}

  </main>{assets[1]}{CONTENTS_FIT_SCRIPT if "data-contents-fit" in body_html else ""}{notes}
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
