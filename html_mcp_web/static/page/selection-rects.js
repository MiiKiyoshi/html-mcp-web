// Where the words of a range in the artifact are drawn, and the whole of what a reader dragged
// over. selectionRects(range) gives the boxes on screen of the range's letters, one per line,
// which the comments' marks, the search's marks and the selection's menu are placed by; and
// selectionSpan(selection), the selection as one range.

import { frameDocument, frameWindow } from "./deck-dom.js";

// The whole of what the reader dragged over, as one range. A drag usually leaves one, but KaTeX
// draws a fraction or a subscript as an inline table (.vlist is a table-cell), and a drag that
// crosses those cells puts a browser that selects table cells into cell selection, which leaves
// one range per cell. Taking the outermost boundaries reads that back as the span it looked like.
export function selectionSpan(selection) {
  const Range = frameWindow().Range;
  const span = selection.getRangeAt(0).cloneRange();
  for (let index = 1; index < selection.rangeCount; index += 1) {
    const other = selection.getRangeAt(index);
    if (span.compareBoundaryPoints(Range.START_TO_START, other) > 0) {
      span.setStart(other.startContainer, other.startOffset);
    }
    if (span.compareBoundaryPoints(Range.END_TO_END, other) < 0) {
      span.setEnd(other.endContainer, other.endOffset);
    }
  }
  return span;
}

export function selectionRects(range) {
  return svgSelectionRects(range)
    ?? Array.from(range.getClientRects()).filter((rect) => rect.width > 0 && rect.height > 0);
}

// A Range inside an <svg> does not report the characters it holds. Selecting nine letters of a
// label gave the whole <text> element's box (218px wide where the letters were 143), and
// selecting from the middle gave an empty rect, so a highlight covered the whole label and the
// comment button sat away from what was grabbed. The element numbers its own characters and can
// place each one, which is where the letters actually are. The shapes a touch screen's long press
// and handle drag produce are wider than one text node: element containers and spans across
// tspans, and the first cut of this handled neither, so those fell back to the misplaced native
// box. A character belongs to the selection when the range intersects its node and its offset
// lies inside; the owning <text> indexes every descendant character, so one element places them
// all, line by line.
function svgSelectionRects(range) {
  let ancestor = range.commonAncestorContainer;
  if (ancestor.nodeType === Node.TEXT_NODE) ancestor = ancestor.parentElement;
  if (ancestor === null || ancestor.namespaceURI !== "http://www.w3.org/2000/svg") return null;
  const enclosing = ancestor.closest("text");
  const roots = enclosing !== null ? [enclosing]
    : Array.from(ancestor.querySelectorAll("text")).filter((text) => range.intersectsNode(text));
  if (roots.length === 0) return null;
  const rects = [];
  for (const root of roots) {
    if (typeof root.getExtentOfChar !== "function") return null;
    const unit = extentUnit(root);
    const toScreen = textMapping(root);
    if (unit === null || toScreen === null) return null;
    const walker = frameDocument().createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let base = 0;
    let band = null;
    let node;
    while ((node = walker.nextNode()) !== null) {
      const length = node.nodeValue.length;
      if (range.intersectsNode(node)) {
        const from = range.startContainer === node ? Math.min(range.startOffset, length) : 0;
        const to = range.endContainer === node ? Math.min(range.endOffset, length) : length;
        for (let index = from; index < to; index += 1) {
          let box;
          try {
            box = root.getExtentOfChar(base + index);
          } catch (error) {
            return null;
          }
          let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
          for (const [x, y] of [[box.x, box.y], [box.x + box.width, box.y],
                                [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]]) {
            const [screenX, screenY] = toScreen(x * unit, y * unit);
            left = Math.min(left, screenX); right = Math.max(right, screenX);
            top = Math.min(top, screenY); bottom = Math.max(bottom, screenY);
          }
          // One rect per line: a character on a new tspan line starts a new band rather than
          // stretching the previous one down and across. Lines set tight overlap by a sliver, so
          // joining takes half the character's height, not a mere touch.
          if (band !== null
              && Math.min(bottom, band.bottom) - Math.max(top, band.top) > (bottom - top) / 2) {
            band.left = Math.min(band.left, left);
            band.right = Math.max(band.right, right);
            band.top = Math.min(band.top, top);
            band.bottom = Math.max(band.bottom, bottom);
          } else {
            band = { left, top, right, bottom };
            rects.push(band);
          }
        }
      }
      base += length;
    }
  }
  if (rects.length === 0) return null;
  return rects.map((box) => ({ ...box, width: box.right - box.left, height: box.bottom - box.top }));
}

// Where a point of a text's user space falls on screen. Two boxes of the text are right in every
// engine: its own box in user space (getBBox) and its box on screen (getBoundingClientRect). The
// screen matrix is used where it carries the one onto the other, which keeps a turned label right;
// where it does not, as in Safari, whose matrix leaves out the CSS scale the page is drawn at and
// so put the box further off the more the page was zoomed, the two boxes give the mapping
// themselves.
function textMapping(root) {
  const box = root.getBBox();
  const rect = root.getBoundingClientRect();
  const ctm = root.getScreenCTM();
  if (ctm !== null) {
    const through = (x, y) => [ctm.a * x + ctm.c * y + ctm.e, ctm.b * x + ctm.d * y + ctm.f];
    let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
    for (const [x, y] of [[box.x, box.y], [box.x + box.width, box.y],
                          [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]]) {
      const [screenX, screenY] = through(x, y);
      left = Math.min(left, screenX); right = Math.max(right, screenX);
      top = Math.min(top, screenY); bottom = Math.max(bottom, screenY);
    }
    if (Math.abs(left - rect.left) < 1.5 && Math.abs(top - rect.top) < 1.5
        && Math.abs(right - rect.right) < 1.5 && Math.abs(bottom - rect.bottom) < 1.5) {
      return through;
    }
  }
  if (box.width === 0 || box.height === 0) return null;
  const scaleX = rect.width / box.width;
  const scaleY = rect.height / box.height;
  return (x, y) => [rect.left + (x - box.x) * scaleX, rect.top + (y - box.y) * scaleY];
}

// How many user-space units one unit of a character extent is: the height the extents of all the
// characters span, against the height of the text's own box. Chromium hands the extents back
// divided by the scale the page is drawn at (a label at user-space y 282 on a page scaled by 0.76
// came back at 369); the factor is 1 where they agree.
function extentUnit(root) {
  const total = root.getNumberOfChars();
  const box = root.getBBox();
  if (total === 0 || box.height === 0) return 1;
  let top = Infinity, bottom = -Infinity;
  for (let index = 0; index < total; index += 1) {
    let extent;
    try {
      extent = root.getExtentOfChar(index);
    } catch (error) {
      return null;
    }
    top = Math.min(top, extent.y);
    bottom = Math.max(bottom, extent.y + extent.height);
  }
  return bottom > top ? box.height / (bottom - top) : 1;
}
