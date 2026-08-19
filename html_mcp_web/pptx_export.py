"""Turn a built slide deck into an editable pptx with firefox marionette and python-pptx.

Every block of a body page becomes its own shape at the position it has in the html
(a 1280x720 px page is 12192000x6858000 EMU, 9525 EMU per px):
  - text blocks without KaTeX (p, headings, li, table-free inline text) -> text boxes
  - ul / ol                                                             -> bulleted / numbered text boxes
  - <img>                                                               -> the image file
  - tables without KaTeX                                                -> pptx tables
  - a div that paints a background or border                            -> a rounded panel, then its content
  - inline <svg> (self-contained)                                       -> real vector, with a screenshot fallback
  - KaTeX, canvas, anything else                                        -> a 3x screenshot of that element
Pages without a body box (cover, contents, divider) are full-page screenshots, unless
the skin's pptx template supplies them.

Skin configuration lives in skin.json under "pptx":
  template     pptx file beside skin.json whose layouts carry the chrome (title bar, footer,
               logos); without it, the chrome is rebuilt from the page's own DOM
  layout       name of the template layout that body pages use; default is the first
               layout with a title placeholder
  keep_slides  how many leading template slides stand in for the deck's first pages
               (typically cover and contents); default 0
  cover        which paragraph of which shape on the template's first slide receives the
               deck's title, subtitle, and author: {"title": "Shape name:0", ...}
  fonts        the deck face, embedded so the pptx renders the same on a machine that
               lacks it: {"family": "Noto Sans KR", "regular": "fonts/X-Regular.ttf",
               "bold": ..., "italic": ..., "boldItalic": ...}, paths beside skin.json.
               Static TrueType (glyf) files whose fsType permits embedding; PowerPoint
               ignores CFF/OTF and variable fonts. Every run is set in family.
  font         typeface for every run when nothing is embedded; default Arial

Requires firefox, marionette_driver, python-pptx, and fontTools when fonts are embedded.
"""
import base64
import copy
import io
import json
import re
import shutil
import struct
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

EMU_PER_PX = 9525
DPR = 3
PAGE_WIDTH_PX = 1280
PAGE_HEIGHT_PX = 720
PT_PER_PX = 0.75
DEFAULT_FONT = "Arial"
MONO_FONT = "Consolas"
BULLETS = ["•", "◦", "▪"]

JS_SETUP = """
const st = document.createElement('style');
st.textContent = 'section.page{width:%dpx !important;height:%dpx !important;margin:0 auto !important;'
  + 'box-shadow:none !important;border-radius:0 !important}.script-block{display:none !important}';
document.head.appendChild(st);
""" % (PAGE_WIDTH_PX, PAGE_HEIGHT_PX)

JS_READY = ("return document.readyState === 'complete' && "
            "Array.from(document.images).every(im => im.complete)")

JS_PAGES = "return document.querySelectorAll('section.page').length;"

JS_COVER = """
const cover = document.querySelector('section.page.cover');
if (!cover) return null;
const text = (sel) => { const e = cover.querySelector(sel); return e ? e.textContent.trim() : ''; };
return {title: text('h1'), sub: text('.sub'), who: text('.who')};
"""

# Walk a page's DOM into a flat list of shapes. Containers descend; a container that
# paints something becomes a panel first so its content sits on it.
JS_EXTRACT = r"""
const idx = arguments[0];
const withChrome = arguments[1];
const page = document.querySelectorAll('section.page')[idx];
const pr = page.getBoundingClientRect();
const cs = (el) => getComputedStyle(el);
const rel = (r) => [r.left - pr.left, r.top - pr.top, r.width, r.height];
const BLOCKISH = /^(block|flex|grid|table|list-item|flow-root)$/;
const painted = (s) => (s.backgroundColor !== 'rgba(0, 0, 0, 0)' && s.backgroundColor !== 'transparent')
  || (parseFloat(s.borderTopWidth) > 0 && s.borderTopStyle !== 'none')
  || (parseFloat(s.borderLeftWidth) > 0 && s.borderLeftStyle !== 'none')
  || (parseFloat(s.borderBottomWidth) > 0 && s.borderBottomStyle !== 'none')
  || (parseFloat(s.borderRightWidth) > 0 && s.borderRightStyle !== 'none');
const items = [];
let counter = 0;
for (const stale of page.querySelectorAll('[data-pptx-index]')) stale.removeAttribute('data-pptx-index');
const mark = (el) => { el.setAttribute('data-pptx-index', String(counter)); return counter++; };

const runsOf = (node, out, base) => {
  for (const n of node.childNodes) {
    if (n.nodeType === 3) {
      const t = n.textContent.replace(/\s+/g, ' ');
      if (t.trim() === '' && out.length === 0) continue;
      if (t !== '') out.push(Object.assign({}, base, {text: t}));
    } else if (n.nodeType === 1) {
      const tg = n.tagName.toLowerCase();
      if (tg === 'br') { out.push(Object.assign({}, base, {text: '\v'})); continue; }
      if (tg === 'ul' || tg === 'ol') continue;
      const s = cs(n);
      if (s.display === 'none') continue;
      const mono = /mono/i.test(s.fontFamily) || tg === 'code' || base.mono;
      const chipBg = (tg === 'code' && s.backgroundColor !== 'rgba(0, 0, 0, 0)' && s.backgroundColor !== 'transparent')
        ? s.backgroundColor : base.chip;
      const b = Object.assign({}, base, {
        bold: (parseInt(s.fontWeight) >= 600) || base.bold,
        italic: s.fontStyle === 'italic' || base.italic,
        color: s.color, size: parseFloat(s.fontSize), mono,
        spacing: s.letterSpacing === 'normal' ? 0 : (parseFloat(s.letterSpacing) || 0),
        chip: chipBg,
        link: tg === 'a' ? n.getAttribute('href') : base.link,
        sup: tg === 'sup' || base.sup, sub: tg === 'sub' || base.sub,
      });
      runsOf(n, out, b);
    }
  }
};
const paraOf = (el, level, marginTop) => {
  const s = cs(el);
  const runs = [];
  runsOf(el, runs, {bold: parseInt(s.fontWeight) >= 600, italic: s.fontStyle === 'italic',
                    color: s.color, size: parseFloat(s.fontSize), mono: /mono/i.test(s.fontFamily),
                    spacing: s.letterSpacing === 'normal' ? 0 : (parseFloat(s.letterSpacing) || 0), chip: null,
                    link: null, sup: false, sub: false});
  while (runs.length && runs[0].text.trim() === '' && runs[0].text !== '\v') runs.shift();
  while (runs.length && runs[runs.length - 1].text.trim() === '' && runs[runs.length - 1].text !== '\v') runs.pop();
  return {level, runs, size: parseFloat(s.fontSize),
          lh: parseFloat(s.lineHeight) / parseFloat(s.fontSize) || 1.2,
          align: s.textAlign, marginTop: marginTop || 0};
};
const listParas = (list, level, out) => {
  for (const li of list.children) {
    if (li.tagName.toLowerCase() !== 'li') continue;
    out.push(paraOf(li, level, parseFloat(cs(li).marginTop) || 0));
    for (const sub of li.children) {
      const t = sub.tagName.toLowerCase();
      if (t === 'ul' || t === 'ol') listParas(sub, level + 1, out);
    }
  }
};
// Positioned children (a footer's page number and label) keep their own boxes too.
const hasBlockChild = (el) => Array.from(el.children).some((ch) => {
  const c = cs(ch); return BLOCKISH.test(c.display) || c.position === 'absolute' || c.position === 'fixed';
});

const emit = (el) => {
  const tag = el.tagName.toLowerCase();
  if (tag === 'aside' || tag === 'script' || tag === 'style') return;
  const s = cs(el);
  if (s.display === 'none' || s.visibility === 'hidden') return;
  const r = el.getBoundingClientRect();
  if (r.width === 0 || r.height === 0) return;
  const rect = rel(r);
  const hasKatex = !!el.querySelector('.katex') || el.classList.contains('katex');
  const container = hasBlockChild(el);
  if (tag === 'img') { items.push({kind: 'img', rect, src: el.getAttribute('src'), i: mark(el)}); return; }
  // A block that holds math (a paragraph, a list, a table) is shot whole; a container
  // that merely has math somewhere inside descends so the rest stays editable.
  const leafBlock = !container || tag === 'table' || tag === 'ul' || tag === 'ol';
  if (tag === 'svg' || tag === 'canvas' || tag === 'video' || (hasKatex && leafBlock)) {
    // A self-contained inline <svg> (styles on its own tags, no external CSS) travels as
    // real vector so it stays sharp; the screenshot still rides along as the fallback for
    // viewers older than PowerPoint 2016. KaTeX is HTML, not one svg, so it stays raster.
    const item = {kind: 'shot', rect, i: mark(el)};
    if (tag === 'svg') item.svg = new XMLSerializer().serializeToString(el);
    items.push(item); return;
  }
  if (tag === 'table') {
    const rows = [];
    for (const tr of el.querySelectorAll('tr')) {
      const cells = [];
      for (const td of tr.children) {
        const s2 = cs(td);
        cells.push({rect: rel(td.getBoundingClientRect()), header: td.tagName.toLowerCase() === 'th',
                    align: s2.textAlign, bg: s2.backgroundColor, para: paraOf(td, 0, 0),
                    borderBottom: [s2.borderBottomColor, parseFloat(s2.borderBottomWidth) || 0, s2.borderBottomStyle],
                    borderTop: [s2.borderTopColor, parseFloat(s2.borderTopWidth) || 0, s2.borderTopStyle]});
      }
      if (cells.length) rows.push(cells);
    }
    items.push({kind: 'table', rect, rows, i: mark(el)});
    return;
  }
  if (tag === 'ul' || tag === 'ol') {
    const paras = [];
    listParas(el, 0, paras);
    items.push({kind: 'text', rect, paras, list: tag, padLeft: parseFloat(s.paddingLeft) || 0, i: mark(el)});
    return;
  }
  if (painted(s)) {
    const side = (name) => [s['border' + name + 'Color'], s['border' + name + 'Style'] === 'none' ? 0 : (parseFloat(s['border' + name + 'Width']) || 0)];
    items.push({kind: 'panel', rect, bg: s.backgroundColor, radius: parseFloat(s.borderTopLeftRadius) || 0,
                borders: {top: side('Top'), right: side('Right'), bottom: side('Bottom'), left: side('Left')}, i: mark(el)});
    if (!container) {
      const para = paraOf(el, 0, 0);
      if (para.runs.length) items.push({kind: 'text', rect: [rect[0] + (parseFloat(s.paddingLeft) || 0), rect[1] + (parseFloat(s.paddingTop) || 0),
        rect[2] - (parseFloat(s.paddingLeft) || 0) - (parseFloat(s.paddingRight) || 0), rect[3] - (parseFloat(s.paddingTop) || 0) - (parseFloat(s.paddingBottom) || 0)],
        paras: [para], list: null, i: mark(el)});
      return;
    }
  }
  if (container) { for (const ch of el.children) emit(ch); return; }
  const para = paraOf(el, 0, 0);
  if (para.runs.length) items.push({kind: 'text', rect, paras: [para], list: null, i: mark(el)});
};

const body = page.querySelector('.body');
const title = (page.querySelector('.tbar h2') || {}).textContent || '';
if (withChrome) {
  for (const ch of page.children) {
    if (ch === body || ch.classList.contains('script-block')) continue;
    emit(ch);
  }
}
if (body) for (const ch of body.children) emit(ch);
return {title: title.trim(), hasBody: !!body, items};
"""

# Marks restart at 0 on every page, so the lookup stays inside the page being exported;
# a document-wide search returned an earlier page's element and its picture was
# stretched into this page's box.
JS_ELEMENT = """
const page = document.querySelectorAll('section.page')[arguments[0]];
const el = page.querySelector('[data-pptx-index="' + arguments[1] + '"]');
el.scrollIntoView({block: 'center'});
return el;
"""


def _px(value: float):
    from pptx.util import Emu
    return Emu(int(round(value * EMU_PER_PX)))


def _rgb(css: str | None):
    from pptx.dml.color import RGBColor
    match = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)", css or "")
    if not match or (match[4] is not None and float(match[4]) == 0):
        return None
    return RGBColor(int(match[1]), int(match[2]), int(match[3]))


def _set_font(run, name: str) -> None:
    from pptx.oxml.ns import qn
    run.font.name = name
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        element = rPr.find(qn(tag))
        if element is None:
            element = rPr.makeelement(qn(tag), {})
            rPr.append(element)
        element.set("typeface", name)


def _clear_bullet(pPr) -> None:
    from pptx.oxml.ns import qn
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum", "a:buFont"):
        for element in pPr.findall(qn(tag)):
            pPr.remove(element)


def _set_list_marker(p_xml, level: int, pad_left: float, ordered: bool, font: str) -> None:
    from pptx.oxml.ns import qn
    pPr = p_xml.get_or_add_pPr()
    indent_px = pad_left + 18 * level
    pPr.set("marL", str(int(indent_px * EMU_PER_PX)))
    pPr.set("indent", str(int(-14 * EMU_PER_PX)))
    _clear_bullet(pPr)
    pPr.append(pPr.makeelement(qn("a:buFont"), {"typeface": font}))
    if ordered:
        pPr.append(pPr.makeelement(qn("a:buAutoNum"), {"type": "arabicPeriod"}))
    else:
        pPr.append(pPr.makeelement(qn("a:buChar"), {"char": BULLETS[min(level, 2)]}))


def _no_marker(p_xml) -> None:
    from pptx.oxml.ns import qn
    pPr = p_xml.get_or_add_pPr()
    pPr.set("marL", "0")
    pPr.set("indent", "0")
    _clear_bullet(pPr)
    pPr.append(pPr.makeelement(qn("a:buNone"), {}))


def _set_run_highlight(run, color) -> None:
    """A `<code>` chip's background becomes the run's highlight, the only inline background
    a pptx run has. It goes right after the fill so the rPr child order stays valid."""
    from pptx.oxml.ns import qn
    rPr = run._r.get_or_add_rPr()
    for existing in rPr.findall(qn("a:highlight")):
        rPr.remove(existing)
    highlight = rPr.makeelement(qn("a:highlight"), {})
    srgb = highlight.makeelement(qn("a:srgbClr"), {"val": str(color)})
    highlight.append(srgb)
    fill = rPr.find(qn("a:solidFill"))
    if fill is not None:
        fill.addnext(highlight)
    else:
        rPr.insert(0, highlight)


def _fill_paragraph(p, para: dict[str, Any], font: str, bold_all: bool = False) -> None:
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Pt
    # Fixed line pitch in points: a percentage is taken against PowerPoint's own single
    # spacing, which is not the browser's, and the lines drift apart.
    p.line_spacing = Pt(para["lh"] * para["size"] * PT_PER_PX)
    p.space_before = Pt(para["marginTop"] * PT_PER_PX) if para["marginTop"] else Pt(0)
    p.space_after = Pt(0)
    p.alignment = {"center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}.get(para["align"], PP_ALIGN.LEFT)
    if not para["runs"]:
        run = p.add_run()
        run.text = ""
        run.font.size = Pt(para["size"] * PT_PER_PX)
        _set_font(run, font)
        return
    for piece in para["runs"]:
        if piece["text"] == "\v":
            p.add_line_break()
            continue
        run = p.add_run()
        run.text = piece["text"]
        _set_font(run, MONO_FONT if piece["mono"] else font)
        size = piece["size"] * PT_PER_PX
        if piece["sup"] or piece["sub"]:
            size *= 0.75
            run._r.get_or_add_rPr().set("baseline", "30000" if piece["sup"] else "-25000")
        run.font.size = Pt(size)
        # Kern at every size, the way the browser does; PowerPoint otherwise leaves small
        # text unkerned and the Latin words read looser than on the page.
        run._r.get_or_add_rPr().set("kern", "0")
        run.font.bold = bool(piece["bold"]) or bold_all
        run.font.italic = bool(piece["italic"])
        color = _rgb(piece["color"])
        if color is not None:
            run.font.color.rgb = color
        # Tracking: the run's spc is in 1/100 pt, from the DOM's px letter-spacing.
        spacing = piece.get("spacing") or 0
        if spacing:
            run._r.get_or_add_rPr().set("spc", str(int(round(spacing * PT_PER_PX * 100))))
        chip = _rgb(piece.get("chip")) if piece.get("chip") else None
        if chip is not None:
            _set_run_highlight(run, chip)
        if piece["link"]:
            run.hyperlink.address = piece["link"]


def _add_text(slide, item: dict[str, Any], font: str) -> None:
    from pptx.enum.text import MSO_ANCHOR
    from pptx.oxml.ns import qn
    x, y, w, h = item["rect"]
    box = slide.shapes.add_textbox(_px(x), _px(y), _px(w + 6), _px(h))
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
    frame.vertical_anchor = MSO_ANCHOR.TOP
    bodyPr = frame._txBody.find(qn("a:bodyPr"))
    for element in list(bodyPr):
        if element.tag in (qn("a:spAutoFit"), qn("a:normAutofit")):
            bodyPr.remove(element)
    for index, para in enumerate(item["paras"]):
        p = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        if item["list"]:
            _set_list_marker(p._p, para["level"], item["padLeft"], item["list"] == "ol", font)
        else:
            _no_marker(p._p)
        _fill_paragraph(p, para, font)


def _set_cell_borders(cell, top, bottom) -> None:
    """top/bottom: (css color, width px, style) from the DOM; left/right are never drawn."""
    from pptx.oxml.ns import qn
    tcPr = cell._tc.get_or_add_tcPr()
    for tag, spec in (("a:lnL", None), ("a:lnR", None), ("a:lnT", top), ("a:lnB", bottom)):
        for element in tcPr.findall(qn(tag)):
            tcPr.remove(element)
        line = tcPr.makeelement(qn(tag), {})
        color = _rgb(spec[0]) if spec and spec[1] > 0 and spec[2] != "none" else None
        if color is None:
            line.set("w", "0")
            line.append(line.makeelement(qn("a:noFill"), {}))
        else:
            line.set("w", str(int(spec[1] * 12700)))
            fill = line.makeelement(qn("a:solidFill"), {})
            fill.append(fill.makeelement(qn("a:srgbClr"), {"val": str(color)}))
            line.append(fill)
        tcPr.append(line)


def _add_table(slide, item: dict[str, Any], font: str) -> None:
    from pptx.enum.text import MSO_ANCHOR
    from pptx.oxml.ns import qn
    from pptx.util import Emu
    rows = item["rows"]
    n_rows, n_cols = len(rows), max(len(row) for row in rows)
    x, y, w, h = item["rect"]
    graphic = slide.shapes.add_table(n_rows, n_cols, _px(x), _px(y), _px(w), _px(h))
    table = graphic.table
    tblPr = table._tbl.tblPr
    tblPr.set("firstRow", "0")
    tblPr.set("bandRow", "0")
    style = tblPr.find(qn("a:tableStyleId"))
    if style is not None:
        # No Style, No Grid: the style adds nothing, so the per-cell borders read from the
        # DOM are the only lines. The Table Grid style drew a full grid over them in PowerPoint.
        style.text = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"
    widest = max(rows, key=len)
    for col in range(n_cols):
        table.columns[col].width = _px(widest[col]["rect"][2])
    for row_index, cells in enumerate(rows):
        table.rows[row_index].height = _px(cells[0]["rect"][3])
        for col in range(n_cols):
            cell = table.cell(row_index, col)
            cell.margin_left = cell.margin_right = Emu(int(6 * EMU_PER_PX))
            cell.margin_top = cell.margin_bottom = Emu(int(4 * EMU_PER_PX))
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            if col >= len(cells):
                # Borders go in before the fill: the schema orders lnL/R/T/B ahead of the
                # fill, and PowerPoint drops borders that come after it (LibreOffice tolerates them).
                _set_cell_borders(cell, None, None)
                cell.fill.background()
                continue
            source = cells[col]
            _set_cell_borders(cell, source["borderTop"], source["borderBottom"])
            background = _rgb(source["bg"])
            if background is None:
                cell.fill.background()
            else:
                cell.fill.solid()
                cell.fill.fore_color.rgb = background
            frame = cell.text_frame
            frame.word_wrap = True
            _fill_paragraph(frame.paragraphs[0], source["para"], font, bold_all=source["header"])


def _add_panel(slide, item: dict[str, Any]) -> None:
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Pt
    x, y, w, h = item["rect"]
    borders = item["borders"]
    sides = {name: (_rgb(color), width) for name, (color, width) in borders.items()}
    drawn = {name: value for name, value in sides.items() if value[0] is not None and value[1] > 0}
    uniform = len(drawn) == 4 and len({value for value in drawn.values()}) == 1
    background = _rgb(item["bg"])
    if background is not None or uniform:
        kind = MSO_SHAPE.ROUNDED_RECTANGLE if item["radius"] > 0 else MSO_SHAPE.RECTANGLE
        shape = slide.shapes.add_shape(kind, _px(x), _px(y), _px(w), _px(h))
        if item["radius"] > 0:
            shape.adjustments[0] = min(0.5, item["radius"] / min(w, h))
        shape.shadow.inherit = False
        if background is None:
            shape.fill.background()
        else:
            shape.fill.solid()
            shape.fill.fore_color.rgb = background
        if uniform:
            color, width = next(iter(drawn.values()))
            shape.line.color.rgb = color
            shape.line.width = Pt(width * PT_PER_PX)
        else:
            shape.line.fill.background()
    if uniform:
        return
    # Partial borders (a rule under a header row, an accent bar on the left) are drawn as
    # thin rectangles on the sides that have them.
    for name, (color, width) in drawn.items():
        if name == "top":
            box = (x, y, w, width)
        elif name == "bottom":
            box = (x, y + h - width, w, width)
        elif name == "left":
            box = (x, y, width, h)
        else:
            box = (x + w - width, y, width, h)
        rule = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, _px(box[0]), _px(box[1]), _px(box[2]), _px(box[3]))
        rule.shadow.inherit = False
        rule.fill.solid()
        rule.fill.fore_color.rgb = color
        rule.line.fill.background()


def _add_picture(slide, data: bytes, rect: list[float]):
    x, y, w, h = rect
    return slide.shapes.add_picture(io.BytesIO(data), _px(x), _px(y), _px(w), _px(h))


# PowerPoint 2016+ keeps a picture vector when the blip references an SVG through this
# extension; the blip's own r:embed stays the raster fallback for older viewers.
SVG_EXT_URI = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"
SVG_NS = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _normalize_svg(svg: bytes, width_px: float, height_px: float, font: str) -> bytes:
    """Match the SVG's viewBox aspect to the picture frame so PowerPoint, which fills the
    frame, does not stretch the drawing. The browser letterboxes (preserveAspectRatio meet);
    the viewBox is widened or heightened symmetrically to carry that same empty margin, so
    the drawing keeps its shape and stays centred. The deck font is named on the root so its
    <text> keeps the browser's metrics: an inline <svg> inherits the page font through CSS,
    but a standalone one carries no CSS, and PowerPoint would substitute a wider face and push
    labels over the drawing."""
    from lxml import etree

    root = etree.fromstring(svg)
    if root.get("font-family") is None:
        root.set("font-family", font)
    view_box = root.get("viewBox") or root.get("viewbox")
    if view_box:
        min_x, min_y, vb_w, vb_h = (float(value) for value in view_box.replace(",", " ").split())
        if vb_w > 0 and vb_h > 0 and width_px > 0 and height_px > 0:
            frame = width_px / height_px
            drawing = vb_w / vb_h
            if drawing < frame:
                widened = vb_h * frame
                min_x -= (widened - vb_w) / 2
                vb_w = widened
            elif drawing > frame:
                heightened = vb_w / frame
                min_y -= (heightened - vb_h) / 2
                vb_h = heightened
            root.set("viewBox", f"{min_x:.3f} {min_y:.3f} {vb_w:.3f} {vb_h:.3f}")
    root.attrib.pop("viewbox", None)
    root.set("preserveAspectRatio", "xMidYMid meet")
    root.set("width", f"{width_px:.2f}")
    root.set("height", f"{height_px:.2f}")
    root.attrib.pop("style", None)  # width:100%/max-height would fight the frame size
    return etree.tostring(root)


def _add_svg_picture(slide, png: bytes, svg: bytes, rect: list[float]) -> None:
    from lxml import etree
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    from pptx.opc.package import Part
    from pptx.oxml.ns import qn

    picture = _add_picture(slide, png, rect)
    package = slide.part.package
    part = Part(package.next_partname("/ppt/media/image%d.svg"), "image/svg+xml", package, svg)
    rid = slide.part.relate_to(part, RT.IMAGE)
    blip = picture._element.blipFill.blip
    ext_list = blip.find(qn("a:extLst"))
    if ext_list is None:
        ext_list = etree.SubElement(blip, qn("a:extLst"))
    ext = etree.SubElement(ext_list, qn("a:ext"))
    ext.set("uri", SVG_EXT_URI)
    svg_blip = etree.SubElement(ext, f"{{{SVG_NS}}}svgBlip")
    svg_blip.set(f"{{{R_NS}}}embed", rid)


def _drop_slides_after(prs, keep: int) -> None:
    from pptx.oxml.ns import qn
    sldIdLst = prs.slides._sldIdLst
    for index, sldId in enumerate(list(sldIdLst)):
        if index < keep:
            continue
        prs.part.drop_rel(sldId.get(qn("r:id")))
        sldIdLst.remove(sldId)


def _set_cover_texts(slide, mapping: dict[str, str], texts: dict[str, str]) -> None:
    """mapping: {"title": "Shape name:paragraph index", ...}; the paragraph keeps its first
    run's formatting and loses the rest. A mapped field the deck leaves empty (a deck with
    no subtitle) clears its paragraph, so the template's placeholder text does not show."""
    for key, target in mapping.items():
        if key not in texts:
            continue
        name, _, index_text = target.rpartition(":")
        index = int(index_text)
        shape = next((s for s in slide.shapes if s.name == name), None)
        if shape is None or not shape.has_text_frame:
            raise ValueError(f"pptx cover shape {name!r} was not found on the template's first slide")
        paragraphs = shape.text_frame.paragraphs
        if index >= len(paragraphs):
            continue
        paragraph = paragraphs[index]
        if not paragraph.runs:
            paragraph.add_run()
        paragraph.runs[0].text = texts[key]
        for run in paragraph.runs[1:]:
            run.text = ""


def _unify_typeface(element_tree, font: str) -> None:
    from pptx.oxml.ns import qn
    for element in element_tree.iter():
        if element.tag in (qn("a:latin"), qn("a:ea"), qn("a:cs")) and element.get("typeface") not in (None, "+mj-lt", "+mn-lt", "+mj-ea", "+mn-ea"):
            element.set("typeface", font)


def _replace_total_count(prs, total: int) -> None:
    for layout in prs.slide_layouts:
        for shape in layout.shapes:
            if shape.has_text_frame and re.fullmatch(r"/\s*\d+", shape.text_frame.text.strip()):
                for paragraph in shape.text_frame.paragraphs:
                    for run in paragraph.runs:
                        run.text = re.sub(r"\d+", str(total), run.text)


def _body_layout(prs, name: str | None):
    if name is not None:
        layout = next((layout for layout in prs.slide_layouts if layout.name == name), None)
        if layout is None:
            raise ValueError(f"pptx layout {name!r} is not in the template; layouts: {[l.name for l in prs.slide_layouts]}")
        return layout
    for layout in prs.slide_layouts:
        if any(ph.placeholder_format.type == 1 for ph in layout.placeholders):
            return layout
    return prs.slide_layouts[0]


def _new_slide(prs, layout, title: str | None, with_number: bool):
    """A slide on the layout with only its title (when given) and, when the layout's chrome
    is used, its slide number placeholder, which PowerPoint shows only when copied onto the slide."""
    slide = prs.slides.add_slide(layout)
    for placeholder in list(slide.placeholders):
        kind = placeholder.placeholder_format.type
        if kind == 1 and title is not None:
            placeholder.text = title
            continue
        placeholder._element.getparent().remove(placeholder._element)
    if with_number:
        for placeholder in layout.placeholders:
            if placeholder.placeholder_format.type == 13:
                slide.shapes._spTree.append(copy.deepcopy(placeholder._element))
    return slide


REL_FONT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
FACE_KINDS = ("regular", "bold", "italic", "boldItalic")


def _embed_unicodes() -> set[int]:
    keep = set(range(0x20, 0x7F)) | set(range(0xA0, 0x100)) | set(range(0x370, 0x400))
    keep |= set(range(0x2000, 0x2070)) | set(range(0x2190, 0x2300))
    keep |= set(range(0x2460, 0x2500)) | set(range(0x25A0, 0x2600)) | set(range(0x3000, 0x3040))
    keep |= set(range(0x3130, 0x3190))  # Hangul compatibility Jamo
    keep |= set(range(0xAC00, 0xD7A4))  # every Hangul syllable
    keep |= set(range(0xFF00, 0xFF60))
    return keep


def _subset_ttf(path: Path) -> bytes:
    from fontTools import subset
    from fontTools.ttLib import TTFont
    font = TTFont(str(path))
    if "glyf" not in font:
        raise ValueError(f"{path}: not a TrueType-outline font (CFF); PowerPoint cannot embed it")
    if "fvar" in font:
        raise ValueError(f"{path}: variable font; a static instance is needed")
    if font["OS/2"].fsType & 0x0002:
        raise ValueError(f"{path}: fsType forbids embedding")
    options = subset.Options()
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.notdef_outline = True
    options.glyph_names = False
    options.hinting = True
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=_embed_unicodes())
    subsetter.subset(font)
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer.getvalue()


def _ttf_to_eot(ttf: bytes) -> bytes:
    """Wrap TrueType data in an EOT 0x00020002 header without compression or XOR: the form
    PowerPoint reads from ppt/fonts/*.fntdata."""
    from fontTools.ttLib import TTFont
    font = TTFont(io.BytesIO(ttf))
    os2, head, name = font["OS/2"], font["head"], font["name"]
    family = name.getDebugName(1) or ""
    style = name.getDebugName(2) or ""
    version = name.getDebugName(5) or ""
    full = name.getDebugName(4) or family
    panose = bytes(getattr(os2.panose, f"b{key}") for key in (
        "FamilyType", "SerifStyle", "Weight", "Proportion", "Contrast",
        "StrokeVariation", "ArmStyle", "LetterForm", "Midline", "XHeight"))
    body = struct.pack("<II", 0x00020002, 0) + panose
    body += struct.pack("<BB", 1, 1 if head.macStyle & 2 else 0)
    body += struct.pack("<IHH", os2.usWeightClass, os2.fsType, 0x504C)
    body += struct.pack("<IIII", os2.ulUnicodeRange1, os2.ulUnicodeRange2, os2.ulUnicodeRange3, os2.ulUnicodeRange4)
    body += struct.pack("<II", getattr(os2, "ulCodePageRange1", 0), getattr(os2, "ulCodePageRange2", 0))
    body += struct.pack("<I", head.checkSumAdjustment) + struct.pack("<IIII", 0, 0, 0, 0)
    for text in (family, style, version, full):
        encoded = text.encode("utf-16-le")
        body += struct.pack("<HH", 0, len(encoded)) + encoded
    body += struct.pack("<HHI", 0, 0, 0)  # padding, root string (empty), root string checksum
    body += struct.pack("<I", 0)  # EUDC code page
    body += struct.pack("<HH", 0, 0)  # padding, signature (empty)
    body += struct.pack("<II", 0, 0)  # EUDC flags, EUDC font size
    return struct.pack("<II", 8 + len(body) + len(ttf), len(ttf)) + body + ttf


def _embedded_face(path: Path) -> bytes:
    """Subsetting a CJK face takes seconds, so the wrapped result is kept per source file
    (path, size, mtime) under the user's cache directory."""
    import hashlib
    stat = path.stat()
    key = hashlib.sha256(f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")).hexdigest()
    cache = Path.home() / ".cache" / "html-mcp-web" / "pptx-fonts" / f"{key}.fntdata"
    if cache.is_file():
        return cache.read_bytes()
    data = _ttf_to_eot(_subset_ttf(path))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return data


def embed_fonts(pptx_path: Path, family: str, faces: dict[str, Path]) -> None:
    """Add subset TrueType faces to a saved pptx as embedded fonts under `family`."""
    with zipfile.ZipFile(pptx_path) as archive:
        items = {name: archive.read(name) for name in archive.namelist()}
    content_types = items["[Content_Types].xml"].decode("utf-8")
    if 'Extension="fntdata"' not in content_types:
        content_types = content_types.replace(
            "</Types>", '<Default Extension="fntdata" ContentType="application/x-fontdata"/></Types>')
    rels = items["ppt/_rels/presentation.xml.rels"].decode("utf-8")
    next_id = max((int(value) for value in re.findall(r'Id="rId(\d+)"', rels)), default=0) + 1
    presentation = items["ppt/presentation.xml"].decode("utf-8")
    face_xml = ""
    part_number = 1
    for kind in (kind for kind in FACE_KINDS if kind in faces):
        # A template may carry embedded fonts of its own; their parts keep their names.
        while f"ppt/fonts/font{part_number}.fntdata" in items:
            part_number += 1
        part = f"ppt/fonts/font{part_number}.fntdata"
        items[part] = _embedded_face(faces[kind])
        rid = f"rId{next_id}"
        next_id += 1
        rels = rels.replace(
            "</Relationships>",
            f'<Relationship Id="{rid}" Type="{REL_FONT}" Target="fonts/font{part_number}.fntdata"/></Relationships>')
        face_xml += f'<p:{kind} r:id="{rid}"/>'
    entry = f'<p:embeddedFont><p:font typeface="{family}" pitchFamily="34" charset="-127"/>{face_xml}</p:embeddedFont>'
    if "<p:embeddedFontLst>" in presentation:
        # Keep the template's own entries; an earlier entry for this family gives way.
        presentation = re.sub(
            rf'<p:embeddedFont><p:font typeface="{re.escape(family)}"[^>]*/>.*?</p:embeddedFont>', "", presentation, flags=re.S)
        presentation = presentation.replace("</p:embeddedFontLst>", entry + "</p:embeddedFontLst>", 1)
    else:
        font_list = f"<p:embeddedFontLst>{entry}</p:embeddedFontLst>"
        # Schema order puts embeddedFontLst right after notesSz.
        anchor = re.search(r"<p:notesSz[^>]*/>", presentation)
        if anchor is None:
            raise ValueError("presentation.xml has no notesSz element")
        presentation = presentation[:anchor.end()] + font_list + presentation[anchor.end():]
    root = re.search(r"<p:presentation\b[^>]*>", presentation).group(0)
    if 'embedTrueTypeFonts="1"' not in root:
        presentation = presentation.replace("<p:presentation ", '<p:presentation embedTrueTypeFonts="1" ', 1)
        root = re.search(r"<p:presentation\b[^>]*>", presentation).group(0)
    if "xmlns:r=" not in root:
        presentation = presentation.replace("<p:presentation ", f'<p:presentation xmlns:r="{NS_R}" ', 1)
    items["[Content_Types].xml"] = content_types.encode("utf-8")
    items["ppt/_rels/presentation.xml.rels"] = rels.encode("utf-8")
    items["ppt/presentation.xml"] = presentation.encode("utf-8")
    with zipfile.ZipFile(pptx_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", items.pop("[Content_Types].xml"))
        for name, data in items.items():
            archive.writestr(name, data)


def load_pptx_config(skin_dir: Path | None) -> dict[str, Any]:
    if skin_dir is None or not (skin_dir / "skin.json").is_file():
        return {}
    config = json.loads((skin_dir / "skin.json").read_text(encoding="utf-8"))
    return dict(config.get("pptx", {}))


def export_pptx(html_url: str, out_path: Path, project_dir: Path, skin_dir: Path | None) -> dict[str, Any]:
    """Callers must not run two of these at once: firefox is driven on the default marionette port."""
    from marionette_driver.marionette import Marionette
    from pptx import Presentation

    if shutil.which("firefox") is None:
        raise FileNotFoundError("firefox is not installed")
    config = load_pptx_config(skin_dir)
    faces: dict[str, Path] = {}
    if "fonts" in config:
        faces = {kind: skin_dir / config["fonts"][kind] for kind in FACE_KINDS if kind in config["fonts"]}
        for kind, path in faces.items():
            if not path.is_file():
                raise FileNotFoundError(f"pptx font {kind!r}: {path} does not exist")
        font = config["fonts"]["family"]
    else:
        font = config.get("font", DEFAULT_FONT)
    keep = int(config.get("keep_slides", 0))
    template = (skin_dir / config["template"]) if "template" in config else None
    if template is not None and not template.is_file():
        raise FileNotFoundError(f"pptx template {template} does not exist")

    profile = tempfile.mkdtemp(prefix="html_mcp_pptx_")
    Path(profile, "user.js").write_text(
        f'user_pref("layout.css.devPixelsPerPx", "{DPR}");\n'
        'user_pref("browser.shell.checkDefaultBrowser", false);\n', encoding="utf-8")
    proc = subprocess.Popen(
        ["firefox", "-marionette", "-headless", "-no-remote", "-profile", profile,
         "-width", "1400", "-height", "900", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        client = Marionette(host="127.0.0.1", port=2828, startup_timeout=60)
        client.start_session()
        client.navigate(html_url)
        client.execute_script(JS_SETUP)
        for _ in range(100):
            if client.execute_script(JS_READY):
                break
            time.sleep(0.2)
        page_count = client.execute_script(JS_PAGES)
        if page_count == 0:
            raise ValueError("the artifact has no section.page")

        if template is not None:
            prs = Presentation(str(template))
            _drop_slides_after(prs, keep)
            if keep > 0 and "cover" in config:
                cover = client.execute_script(JS_COVER)
                if cover is not None:
                    _set_cover_texts(prs.slides[0], config["cover"], cover)
            for slide in list(prs.slides)[:keep]:
                _unify_typeface(slide._element, font)
            _replace_total_count(prs, page_count)
            layout = _body_layout(prs, config.get("layout"))
        else:
            prs = Presentation()
            prs.slide_width = _px(PAGE_WIDTH_PX)
            prs.slide_height = _px(PAGE_HEIGHT_PX)
            keep = 0
            layout = prs.slide_layouts[6]  # blank

        with_chrome = template is None
        report = []
        for index in range(keep, page_count):
            info = client.execute_script(JS_EXTRACT, script_args=[index, with_chrome])
            if not info["hasBody"]:
                slide = _new_slide(prs, layout, None, template is not None)
                shot = client.screenshot(element=client.execute_script(
                    "const p = document.querySelectorAll('section.page')[arguments[0]]; p.scrollIntoView(); return p;",
                    script_args=[index]), format="base64")
                _add_picture(slide, base64.b64decode(shot), [0, 0, PAGE_WIDTH_PX, PAGE_HEIGHT_PX])
                report.append({"page": index + 1, "title": info["title"], "shapes": 1, "screenshot": True})
                continue
            slide = _new_slide(prs, layout, None if with_chrome else info["title"], template is not None)
            for item in info["items"]:
                if item["kind"] == "text":
                    _add_text(slide, item, font)
                elif item["kind"] == "table":
                    _add_table(slide, item, font)
                elif item["kind"] == "panel":
                    _add_panel(slide, item)
                elif item["kind"] == "img":
                    src = item["src"] or ""
                    if src.startswith("data:"):
                        data = base64.b64decode(src.split(",", 1)[1])
                    else:
                        source = (project_dir / src.split("?", 1)[0]).resolve()
                        if not source.is_relative_to(project_dir.resolve()) or not source.is_file():
                            raise FileNotFoundError(f"image {src!r} is not a file inside the project")
                        data = source.read_bytes()
                    _add_picture(slide, data, item["rect"])
                else:
                    element = client.execute_script(JS_ELEMENT, script_args=[index, item["i"]])
                    shot = base64.b64decode(client.screenshot(element=element, format="base64"))
                    if "svg" in item:
                        svg = _normalize_svg(item["svg"].encode("utf-8"), item["rect"][2], item["rect"][3], font)
                        _add_svg_picture(slide, shot, svg, item["rect"])
                    else:
                        _add_picture(slide, shot, item["rect"])
            report.append({"page": index + 1, "title": info["title"], "shapes": len(info["items"]),
                           "screenshot": False, "vector_svgs": sum(1 for item in info["items"] if "svg" in item)})
        client.delete_session()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        prs.save(str(out_path))
        if faces:
            embed_fonts(out_path, font, faces)
        return {"path": str(out_path), "slides": len(prs.slides), "pages": report,
                "font": font, "embedded_faces": sorted(faces)}
    finally:
        proc.terminate()
        shutil.rmtree(profile, ignore_errors=True)
