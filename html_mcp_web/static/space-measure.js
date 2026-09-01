function rounded(value) {
  return Math.round(value * 100) / 100;
}

function roundedUp(value) {
  return Math.ceil(value * 100) / 100;
}

function roundedDown(value) {
  return Math.floor(value * 100) / 100;
}

function localBox(rect, pageRect, scale) {
  return [
    rounded((rect.left - pageRect.left) / scale),
    rounded((rect.top - pageRect.top) / scale),
    rounded(rect.width / scale),
    rounded(rect.height / scale),
  ];
}

function visible(element, win) {
  if (["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"].includes(element.tagName)) return false;
  if (element.classList.contains("html-mcp-highlight-layer")) return false;
  const style = win.getComputedStyle(element);
  if (style.display === "none" || style.visibility === "hidden") return false;
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function elementName(element) {
  const id = element.id ? `#${element.id}` : "";
  const classes = Array.from(element.classList)
    .filter((name) => !name.startsWith("html-mcp-"))
    .map((name) => `.${name}`)
    .join("");
  return `${element.tagName.toLowerCase()}${id}${classes}`;
}

export function elementRef(page, pageNumber, element) {
  const path = [];
  for (let current = element; current !== page; current = current.parentElement) {
    if (current.parentElement === null) throw new Error("measured element is outside its page");
    path.push(Array.prototype.indexOf.call(current.parentElement.children, current));
  }
  return `p${pageNumber}:${path.reverse().join(".")}`;
}

// A rect belongs to the current line when a third of its own height overlaps that line's
// core. Comparing tops against the line's bottom instead let a subscript, which dips
// below the baseline, stretch the line downward until the next line's rects fell inside
// it, and two lines counted as one. Stacked lines never overlap by a third of a glyph
// run, while the lower limit of a big operator ($\int_0^1$) reaches only 45% into the
// body text band, so half was too strict.
export function sameLine(line, rect) {
  const overlap = Math.min(line.coreBottom, rect.bottom) - Math.max(line.coreTop, rect.top);
  return overlap > Math.min(rect.height, line.coreBottom - line.coreTop) / 3;
}

// Rects come sorted by top, so a superscript arrives before the body text of its line;
// the core is the tallest rect seen so far, which is the body text once it arrives, and
// a subscript below the baseline still overlaps it. Rects shorter than 0.4em are not
// glyph runs (KaTeX vlist rows, fraction rules, accents, the hidden MathML box); one of
// them sitting just under the body text started a phantom second line.
export function groupLines(rects, fontSize) {
  const ordered = rects.filter((rect) => rect.width > 0 && rect.height >= fontSize * 0.4)
    .sort((a, b) => a.top - b.top || a.left - b.left);
  const lines = [];
  for (const rect of ordered) {
    const line = lines[lines.length - 1];
    if (line && sameLine(line, rect)) {
      line.left = Math.min(line.left, rect.left);
      line.top = Math.min(line.top, rect.top);
      line.right = Math.max(line.right, rect.right);
      line.bottom = Math.max(line.bottom, rect.bottom);
      if (rect.height > line.coreBottom - line.coreTop) {
        line.coreTop = rect.top;
        line.coreBottom = rect.bottom;
      }
    } else {
      lines.push({ left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom,
                   coreTop: rect.top, coreBottom: rect.bottom });
    }
  }
  return lines;
}

function mergeLines(rects, fontSize) {
  return groupLines(rects, fontSize).map((line) => ({
    left: line.left,
    top: line.top,
    width: line.right - line.left,
    height: line.bottom - line.top,
  }));
}

function textLines(element, includeDescendants, doc) {
  const rects = [];
  const range = doc.createRange();
  const fontSize = parseFloat(doc.defaultView.getComputedStyle(element).fontSize) || 16;
  if (includeDescendants) {
    if (element.textContent.trim() === "") return [];
    range.selectNodeContents(element);
    return mergeLines(Array.from(range.getClientRects()), fontSize);
  }
  for (const node of element.childNodes) {
    if (node.nodeType !== doc.defaultView.Node.TEXT_NODE || node.nodeValue.trim() === "") continue;
    range.selectNode(node);
    rects.push(...range.getClientRects());
  }
  return mergeLines(rects, fontSize);
}

// SVG tag names keep their XML case, so comparisons run on the uppercased name.
const OBJECT_TAGS = ["IMG", "SVG", "CANVAS", "VIDEO"];

function childElements(element, win) {
  const tag = element.tagName.toUpperCase();
  // Objects are atomic content: their internals (SVG shapes, fallback content)
  // are not layout space an author can reclaim.
  if (OBJECT_TAGS.includes(tag)) return [];
  if (tag === "TABLE") {
    return Array.from(element.querySelectorAll("th, td")).filter((child) => visible(child, win));
  }
  return Array.from(element.children).filter((child) => visible(child, win));
}

// An object reports one box, so an SVG whose drawing sits in a corner looks fully
// used. The union of its rendered shapes, clipped to the viewport that hides the
// rest, is the part of the box the drawing actually occupies.
function drawnExtent(element, win) {
  if (element.tagName.toUpperCase() !== "SVG") return null;
  const viewport = element.getBoundingClientRect();
  const boxes = [];
  for (const shape of element.querySelectorAll("*")) {
    if (typeof shape.getBBox !== "function") continue;
    // Definitions are painted through their references, so their own box is not area
    // the drawing occupies.
    if (shape.closest("defs, symbol, clipPath, mask, pattern, marker") !== null) continue;
    const style = win.getComputedStyle(shape);
    if (style.display === "none" || style.visibility === "hidden") continue;
    const rect = shape.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    const left = Math.max(rect.left, viewport.left);
    const top = Math.max(rect.top, viewport.top);
    const right = Math.min(rect.right, viewport.right);
    const bottom = Math.min(rect.bottom, viewport.bottom);
    if (right > left && bottom > top) boxes.push({ left, top, right, bottom });
  }
  if (boxes.length === 0) return null;
  const left = Math.min(...boxes.map((box) => box.left));
  const top = Math.min(...boxes.map((box) => box.top));
  const right = Math.max(...boxes.map((box) => box.right));
  const bottom = Math.max(...boxes.map((box) => box.bottom));
  return { left, top, width: right - left, height: bottom - top };
}

function nodeKind(element, children) {
  const tag = element.tagName.toUpperCase();
  if (tag === "TABLE") return "table";
  if (["TH", "TD"].includes(tag)) return "cell";
  if (OBJECT_TAGS.includes(tag)) return "object";
  if (children.length === 0 && element.textContent.trim() !== "") return "text";
  return "group";
}

function pageChildren(page, win) {
  const result = [];
  for (const child of page.children) {
    if (!visible(child, win)) continue;
    if (child.hasAttribute("data-layout-guard")) {
      result.push(...Array.from(child.children).filter((nested) => visible(nested, win)));
    } else {
      result.push(child);
    }
  }
  return result;
}

function noWrapCellWidth(cell, doc, scale) {
  const style = doc.defaultView.getComputedStyle(cell);
  const lines = textLines(cell, true, doc);
  const textWidth = lines.length === 0 ? 0 : Math.max(...lines.map((line) => line.width));
  return roundedUp(
    textWidth / scale
    + (parseFloat(style.paddingLeft) || 0)
    + (parseFloat(style.paddingRight) || 0)
    + (parseFloat(style.borderLeftWidth) || 0)
    + (parseFloat(style.borderRightWidth) || 0)
  );
}

function measureTableWidth(table, cellRefs, nodes, doc, scale) {
  const clone = table.cloneNode(true);
  clone.style.setProperty("position", "absolute", "important");
  clone.style.setProperty("visibility", "hidden", "important");
  clone.style.setProperty("pointer-events", "none", "important");
  clone.style.setProperty("left", "-100000px", "important");
  clone.style.setProperty("top", "0", "important");
  clone.style.setProperty("width", "max-content", "important");
  clone.style.setProperty("min-width", "0", "important");
  clone.style.setProperty("max-width", "none", "important");
  clone.style.setProperty("table-layout", "auto", "important");

  // cellRefs only covers visible cells, while the clone keeps every cell, so
  // refs are aligned through the original cell list before hidden cells drop out.
  let visibleIndex = 0;
  const cloneCellRefs = Array.from(table.querySelectorAll("th, td"))
    .map((cell) => (visible(cell, doc.defaultView) ? cellRefs[visibleIndex++] : undefined));
  const cloneCells = Array.from(clone.querySelectorAll("th, td"));
  for (const cell of cloneCells) {
    cell.style.setProperty("width", "auto", "important");
    cell.style.setProperty("min-width", "0", "important");
    cell.style.setProperty("max-width", "none", "important");
    for (const element of [cell, ...cell.querySelectorAll("*")]) {
      element.style.setProperty("white-space", "nowrap", "important");
      element.style.setProperty("word-break", "normal", "important");
      element.style.setProperty("overflow-wrap", "normal", "important");
      element.style.setProperty("hyphens", "none", "important");
    }
  }

  table.parentElement.appendChild(clone);
  try {
    const currentWidthRaw = table.getBoundingClientRect().width / scale;
    const minNoWrapWidthRaw = clone.getBoundingClientRect().width / scale;
    const currentWidth = rounded(currentWidthRaw);
    const minNoWrapWidth = roundedUp(minNoWrapWidthRaw);
    const wrappedCells = [];
    const cellWidths = [];
    for (const [index, cell] of cloneCells.entries()) {
      const ref = cloneCellRefs[index];
      if (ref === undefined) continue;
      const authoredLineCount = textLines(cell, true, doc).length;
      if (nodes[ref].lines.length > authoredLineCount) wrappedCells.push(ref);
      cellWidths.push({
        ref,
        row: nodes[ref].row,
        column: nodes[ref].column,
        colspan: Math.max(1, cell.colSpan),
        min_no_wrap_width: noWrapCellWidth(cell, doc, scale),
      });
    }

    const constraintCells = [];
    const singleColumnCells = cellWidths.filter((cell) => cell.colspan === 1);
    for (const column of new Set(singleColumnCells.map((cell) => cell.column))) {
      const candidates = singleColumnCells.filter((cell) => cell.column === column);
      const requiredWidth = Math.max(...candidates.map((cell) => cell.min_no_wrap_width));
      constraintCells.push(...candidates.filter((cell) => cell.min_no_wrap_width === requiredWidth));
    }
    constraintCells.push(...cellWidths.filter((cell) => cell.colspan > 1));

    const reducibleWidth = roundedDown(Math.max(0, currentWidthRaw - minNoWrapWidthRaw));
    const requiredExpansion = roundedUp(Math.max(0, minNoWrapWidthRaw - currentWidthRaw));
    const canShrink = wrappedCells.length === 0 && minNoWrapWidth <= currentWidth;
    return {
      current_width: currentWidth,
      min_no_wrap_width: minNoWrapWidth,
      reducible_width: reducibleWidth,
      reducible_ratio: currentWidth > 0 ? roundedDown(reducibleWidth / currentWidth) : 0,
      required_expansion: requiredExpansion,
      allowed_width_range: canShrink ? [minNoWrapWidth, currentWidth] : null,
      wrapped_cells: wrappedCells,
      constraint_cells: constraintCells,
    };
  } finally {
    clone.remove();
  }
}

export function measureArtifactSpace(doc) {
  const win = doc.defaultView;
  const pages = Array.from(doc.querySelectorAll("body > main.pages > section.page"));
  return pages.map((page, pageIndex) => {
    const number = pageIndex + 1;
    const pageRect = page.getBoundingClientRect();
    const scale = page.offsetWidth > 0 ? pageRect.width / page.offsetWidth : 1;
    const nodes = {};
    const visit = (element) => {
      const ref = elementRef(page, number, element);
      if (nodes[ref] !== undefined) return ref;
      const children = childElements(element, win);
      const kind = nodeKind(element, children);
      const style = win.getComputedStyle(element);
      // A block whose children are all inline (bold runs, code, rendered math) is one
      // paragraph: its lines run through those children, so they are counted together.
      // A block holding other blocks keeps to its own text, or its lines would restate
      // its children's.
      const inlineChildrenOnly = kind === "group" && children.length > 0
        && children.every((child) => /^inline/.test(win.getComputedStyle(child).display));
      const includeDescendants = kind === "text" || kind === "cell" || inlineChildrenOnly;
      const lines = textLines(element, includeDescendants, doc)
        .map((rect) => localBox(rect, pageRect, scale));
      const node = {
        kind,
        element: elementName(element),
        bbox: localBox(element.getBoundingClientRect(), pageRect, scale),
        padding: [style.paddingTop, style.paddingRight, style.paddingBottom, style.paddingLeft]
          .map((value) => rounded(parseFloat(value) || 0)),
        children: [],
        lines,
        overflow: element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1,
      };
      if (kind === "cell") {
        node.row = element.parentElement.rowIndex + 1;
        node.column = element.cellIndex + 1;
      }
      if (kind === "object") {
        const drawn = drawnExtent(element, win);
        if (drawn !== null) node.content_bbox = localBox(drawn, pageRect, scale);
      }
      nodes[ref] = node;
      node.children = children.map(visit);
      if (kind === "table") {
        node.width_constraints = measureTableWidth(element, node.children, nodes, doc, scale);
      }
      return ref;
    };
    return {
      number,
      bbox: [0, 0, rounded(page.offsetWidth), rounded(page.offsetHeight)],
      children: pageChildren(page, win).map(visit),
      nodes,
    };
  });
}
