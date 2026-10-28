import { measureArtifactSpace, groupLines, sameLine, elementRef } from "./space-measure.js";

// Set only in the browser the server opens for its own layout check.
const checkToken = new URLSearchParams(location.search).get("check");

export function createLayoutChecks(dependencies) {
  const {
    $,
    artifactBase,
    artifactPages,
    clear,
    fetchJson,
    frameDocument,
    frameWindow,
    h,
    state,
  } = dependencies;

  function inNormalFlow(element) {
    const style = frameWindow().getComputedStyle(element);
    return style.display !== "none" && style.position !== "fixed" && style.position !== "absolute";
  }
  
  // The words as the slide shows them. KaTeX keeps a MathML copy of every formula for
  // screen readers, holding the TeX source, and textContent runs the two together: a
  // bullet opening with a formula was named "iceff‾\overline{i_{c_{\m…", which does not
  // match anything the writer can find in the source.
  function readableText(element) {
    const copy = element.cloneNode(true);
    for (const hidden of copy.querySelectorAll(".katex-mathml")) hidden.remove();
    return copy.textContent.trim().replace(/\s+/g, " ");
  }

  // The words a line of a block shows: the characters whose boxes sit on it. KaTeX's
  // hidden MathML copy is on no line the reader sees.
  function lineText(block, line) {
    const doc = block.ownerDocument;
    const walker = doc.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    const range = doc.createRange();
    let text = "";
    for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
      if (node.parentElement.closest(".katex-mathml") !== null) continue;
      for (let offset = 0; offset < node.length; offset += 1) {
        range.setStart(node, offset);
        range.setEnd(node, offset + 1);
        const box = range.getBoundingClientRect();
        if (box.height > 0 && sameLine(line, box)) text += node.data[offset];
      }
    }
    return text.trim().replace(/\s+/g, " ");
  }

  // Where the viewBox lands inside the element box, and at what scale. An element box of a
  // different shape from the viewBox does not stretch the drawing: the rendering keeps the
  // viewBox's proportions and sits in the box according to preserveAspectRatio, leaving a
  // band on the two sides that are over-long.
  function placeViewBox(element, view, room) {
    const ratio = element.preserveAspectRatio?.baseVal;
    const align = ratio ? ratio.align : 6;  // xMidYMid, the default
    const slice = ratio ? ratio.meetOrSlice === 2 : false;
    if (align === 1) {  // none: the drawing is stretched, so no band is left
      return { x: 0, y: 0, scale: 1, scaleX: room.width / view.width, scaleY: room.height / view.height };
    }
    const scale = slice
      ? Math.max(room.width / view.width, room.height / view.height)
      : Math.min(room.width / view.width, room.height / view.height);
    const fraction = [0, 0.5, 1];
    const across = fraction[(align - 2) % 3];
    const down = fraction[Math.floor((align - 2) / 3)];
    return {
      x: (room.width - view.width * scale) * across,
      y: (room.height - view.height * scale) * down,
      scale,
      scaleX: scale,
      scaleY: scale,
    };
  }

  function describeElement(element) {
    const name = element.tagName.toLowerCase();
    const id = element.id === "" ? "" : `#${element.id}`;
    const cls = element.classList.length === 0 ? "" : `.${Array.from(element.classList).join(".")}`;
    return `<${name}${id}${cls}>`;
  }
  
  // Maps each layout error text to the element that produced it, so a click on
  // the Problems tab can reveal the spot. Rebuilt on every local layout check;
  // errors checked by another browser fall back to page-number parsing.
  
  // Runs read() with the page zoom lifted and puts it back before returning, so a
  // measurement that the zoom would distort is taken in the artifact's own scale.
  function unzoomed(read) {
    const style = frameDocument().documentElement.style;
    const previous = style.getPropertyValue("--html-mcp-page-scale");
    style.setProperty("--html-mcp-page-scale", "1");
    try {
      return read();
    } finally {
      if (previous === "") style.removeProperty("--html-mcp-page-scale");
      else style.setProperty("--html-mcp-page-scale", previous);
    }
  }

  function safeBBox(element) {
    try {
      return element.getBBox();
    } catch {
      return null;
    }
  }

  // The first words of an svg label, for a message. A label the deck wrapped holds one
  // tspan per line with no whitespace between, so its lines are joined with spaces here.
  function labelWords(text) {
    if (!text.hasAttribute("data-wrap") && !text.hasAttribute("data-fit")) {
      return text.textContent.trim().replace(/\s+/g, " ").slice(0, 30);
    }
    // One tspan per line, with no whitespace between them, and a word broken across two
    // lines keeps its hyphen on the first: that line joins the next without a space.
    const lines = Array.from(text.childNodes).map((node) => node.textContent);
    const words = lines.map((line, index) =>
      index < lines.length - 1 && !line.endsWith("-") ? `${line} ` : line).join("");
    return words.trim().replace(/\s+/g, " ").slice(0, 30);
  }

  // Text that is not prose: a semicolon in code or math is that notation's own.
  const NOT_PROSE = "code, pre, kbd, samp, .katex, math, script, style, .html-mcp-highlight-layer";

  // How much more one axis may be stretched than the other before a stretch is reported:
  // a numerical tolerance. Sizes and matrices here are unrounded, so an even scale or a
  // rotation comes out at 1 within float error.
  const STRETCH_TOLERANCE = 0.01;

  // What to do with a bullet that interprets a table or figure from elsewhere on the page.
  const INTERPRETATION_ADVICE = "Put the bullet in a list directly below that visual, in the same column (neutral 5.8)";

  // Whether a reader sees an element: rendered, neither hidden nor transparent, and not in
  // an SVG container that is never drawn where it is written.
  function seen(element) {
    return element.checkVisibility({ visibilityProperty: true, opacityProperty: true })
      && element.closest("defs, clipPath, mask, marker, pattern") === null;
  }

  // Whether an element draws a box of its own: a border, a background or a shadow.
  function boxed(element) {
    const style = frameWindow().getComputedStyle(element);
    const shown = (color) => color !== "transparent" && !/^rgba\(.*,\s*0\)$/.test(color);
    return ["Top", "Right", "Bottom", "Left"].some((side) =>
      parseFloat(style[`border${side}Width`]) > 0 && shown(style[`border${side}Color`]))
      || shown(style.backgroundColor) || style.backgroundImage !== "none" || style.boxShadow !== "none";
  }

  // Whether a box meets a boxed neighbour's edge in its row, as the cells of a table drawn
  // as a grid do. Panels stand apart, by a gap or by a track holding an arrow.
  function meetsBoxedNeighbour(element) {
    const box = element.getBoundingClientRect();
    return Array.from(element.parentElement.children).some((other) => {
      if (other === element || !inNormalFlow(other) || !boxed(other)) return false;
      const near = other.getBoundingClientRect();
      return Math.min(box.bottom, near.bottom) > Math.max(box.top, near.top)
        && (Math.abs(near.left - box.right) <= 2 || Math.abs(box.left - near.right) <= 2);
    });
  }

  // How unevenly a 2D linear map stretches: the ratio of its larger to its smaller singular
  // value, 1 for a rotation or an even scale. A rotation is not distortion, and two uneven
  // transforms that undo each other come out even.
  function unevenness(a, b, c, d) {
    const sum = a * a + b * b + c * c + d * d;
    const det = Math.abs(a * d - b * c);
    const root = Math.sqrt(Math.max(0, sum * sum - 4 * det * det));
    const small = Math.sqrt(Math.max(0, (sum - root) / 2));
    return small === 0 ? Infinity : Math.sqrt((sum + root) / 2) / small;
  }

  // The CSS transforms from just inside a page down to an element, its own included, as one
  // matrix. The page's own transform only scales the whole page evenly.
  function pageTransform(page, element) {
    const chain = [];
    for (let node = element; node !== null && node !== page; node = node.parentElement) chain.unshift(node);
    let matrix = new (frameWindow().DOMMatrix)();
    for (const node of chain) {
      const value = frameWindow().getComputedStyle(node).transform;
      if (value && value !== "none") matrix = matrix.multiply(new (frameWindow().DOMMatrix)(value));
    }
    return matrix;
  }

  // The semicolons under `root`, read from the text as the browser decoded it, so an
  // entity counts as the character it stands for. On a page only what a reader sees counts.
  // A script is read out whether or not it is shown, so all of it counts.
  function semicolonsIn(root, visibleOnly) {
    const found = [];
    const walker = root.ownerDocument.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
      if (!node.data.includes(";")) continue;
      const parent = node.parentElement;
      if (parent === null || parent.closest(NOT_PROSE) || (visibleOnly && !seen(parent))) continue;
      found.push({ element: parent, text: node.data, count: node.data.split(";").length - 1 });
    }
    return found;
  }

  function semicolonNote(where, found) {
    const count = found.reduce((total, entry) => total + entry.count, 0);
    const text = found[0].text.replace(/\s+/g, " ").trim();
    const at = text.indexOf(";");
    const quote = text.slice(Math.max(0, at - 20), at + 21);
    return `${where} uses ${count} ${count === 1 ? "semicolon" : "semicolons"}, first in "${quote}". `
      + "Write separate statements instead";
  }

  // How far an arrowhead reaches back along its line from the end it sits on, in the
  // line's user units, or null when its direction does not follow the line. A marker's
  // own children report an empty box, since a marker is never drawn where it is
  // written, so they are measured as a hidden copy in the drawing for that moment.
  function arrowheadReach(marker, strokeWidth, atStart) {
    const orient = marker.getAttribute("orient") ?? "0";
    if (!orient.startsWith("auto")) return null;
    const copy = marker.ownerDocument.createElementNS("http://www.w3.org/2000/svg", "g");
    copy.setAttribute("visibility", "hidden");
    for (const child of marker.children) copy.appendChild(child.cloneNode(true));
    marker.ownerSVGElement.appendChild(copy);
    let box;
    try {
      box = copy.getBBox();
    } finally {
      copy.remove();
    }
    if (box.width === 0) return null;
    const view = marker.viewBox?.baseVal;
    const width = marker.markerWidth.baseVal.value;
    const height = marker.markerHeight.baseVal.value;
    const scale = (view && view.width > 0 && view.height > 0 ? Math.min(width / view.width, height / view.height) : 1)
      * (marker.markerUnits.baseVal === SVGMarkerElement.SVG_MARKERUNITS_STROKEWIDTH ? strokeWidth : 1);
    const refX = marker.refX.baseVal.value;
    // At the start, a head turned with auto-start-reverse points out of the line like the
    // one at the end, and one turned with auto points into it.
    const reach = atStart && orient === "auto" ? box.x + box.width - refX : refX - box.x;
    return Math.max(0, reach) * scale;
  }

  // The distance from an end of a line to the nearest bend within `limit` of it, or null
  // when the line runs straight that far.
  function bendWithin(line, atStart, limit) {
    const total = line.getTotalLength();
    const at = (distance) => line.getPointAtLength(atStart ? distance : total - distance);
    const heading = (from, to) => Math.atan2(to.y - from.y, to.x - from.x);
    const step = 0.25;
    if (total < step * 4) return null;
    const end = heading(at(step), at(0));
    for (let distance = step; distance + step <= Math.min(limit, total); distance += step) {
      let turn = Math.abs(heading(at(distance + step), at(distance)) - end);
      if (turn > Math.PI) turn = 2 * Math.PI - turn;
      if (turn > Math.PI / 6) return distance;
    }
    return null;
  }

  // Errors are faults the check confirms. Warnings are likely faults it cannot confirm,
  // because what would clear them can sit outside what it measures.
  function artifactLayoutFindings() {
    const doc = frameDocument();
    const root = doc.querySelector("body > main.pages");
    if (root === null) return { errors: ['artifact body must contain exactly one <main class="pages"> element'], warnings: [] };
    // Only elements in normal flow can push page breaks around. Elements injected by
    // browser extensions are usually out of flow and are excluded from printing, so they
    // are not reported as an authoring mistake.
    const extra = Array.from(doc.body.children).filter((child) => child !== root && inNormalFlow(child));
    const errors = [];
    const warnings = [];
    let pages = [];
    // The finding carries the block's ref, so the reader of layout() can go straight to
    // layout(target=<ref>) instead of drilling down page by page to find which of
    // a page's four svgs the message meant.
    const withRef = (message, element) => {
      const page = element ? element.closest("section.page") : null;
      const number = page === null ? 0 : pages.indexOf(page) + 1;
      if (number > 0 && element !== page) {
        try {
          message += ` [${elementRef(page, number, element)}]`;
        } catch (error) { /* an element outside its page keeps the plain message */ }
      }
      return message;
    };
    const addError = (message, element) => errors.push(withRef(message, element));
    const addWarning = (message, element) => warnings.push(withRef(message, element));
    if (extra.length > 0) {
      addError(`artifact body must contain only <main class="pages">: found ${extra.map(describeElement).join(", ")}`, extra[0]);
    }
    const children = Array.from(root.children);
    if (children.length === 0) errors.push("main.pages must contain at least one section.page");
    for (const [index, child] of children.entries()) {
      // A template may place a speaker-script block after its page; it is screen-only
      // and carries no page geometry.
      if (child.classList.contains("script-block")) continue;
      if (!child.matches("section.page")) {
        addError(`main.pages child ${index + 1} must be <section class="page">`, child);
      }
    }
    pages = children.filter((child) => child.matches("section.page"));
    // A speaker script follows its page. What it says is prose like the page's, and a
    // paragraph with nothing in it is only spacing. Both are rules of the neutral
    // guideline rather than defects of any rendering, so they hold only where it applies.
    const neutral = state.project?.neutral_guideline === true;
    for (const block of neutral ? root.querySelectorAll(":scope > .script-block") : []) {
      let owner = block.previousElementSibling;
      while (owner !== null && !owner.matches("section.page")) owner = owner.previousElementSibling;
      const where = `page ${owner === null ? 0 : pages.indexOf(owner) + 1} script`;
      const empty = Array.from(block.querySelectorAll("p")).filter((paragraph) =>
        paragraph.textContent.replace(/[\s\u00a0]/g, "") === "" && paragraph.querySelector("img, svg") === null);
      if (empty.length > 0) {
        addError(`${where} has ${empty.length} empty spacing ${empty.length === 1 ? "paragraph" : "paragraphs"}. `
          + "Remove them", null);
      }
      const marked = semicolonsIn(block, false);
      if (marked.length > 0) addError(semicolonNote(where, marked), null);
    }
    // Everything below is measured with the pane zoom lifted. The artifact prints at
    // its own scale, so that is the layout to judge; at a fitted zoom the browser wraps
    // text and rounds boxes differently, and the same page reports different problems
    // depending on how wide the reviewer's window happens to be.
    unzoomed(() => {
    for (const [index, page] of pages.entries()) {
      const horizontal = page.scrollWidth > page.clientWidth + 1;
      const vertical = page.scrollHeight > page.clientHeight + 1;
      if (horizontal || vertical) {
        const axes = [horizontal ? "width" : null, vertical ? "height" : null].filter((value) => value !== null).join(" and ");
        addError(`page ${index + 1} exceeds the ${state.artifact.layout} ${axes}`, page);
      }
      // Templates clip their content box (overflow: hidden), so page-level measurement
      // cannot see content spilling into the chrome (top/bottom bars). A template marks
      // its content area with data-layout-guard, and overflow inside it is an error.
      for (const guard of page.querySelectorAll("[data-layout-guard]")) {
        const gh = guard.scrollHeight > guard.clientHeight + 1;
        const gw = guard.scrollWidth > guard.clientWidth + 1;
        if (gh || gw) {
          const axes = [gw ? "width" : null, gh ? "height" : null].filter((value) => value !== null).join(" and ");
          const over = gh ? ` by ${guard.scrollHeight - guard.clientHeight}px` : "";
          addError(`page ${index + 1} content overflows its content area (${axes}${over})`, guard);
        }
      }
      // A title bar sits outside the content guard and does not clip, so a title that
      // wrapped to a second line spilled above and below the bar, and ran under the bar's
      // corner logo, on a page the guard passed. A template marks such a fixed-height bar
      // with data-layout-bar, and its text lines must stay inside it and clear of its images.
      for (const bar of page.querySelectorAll("[data-layout-bar]")) {
        const box = bar.getBoundingClientRect();
        const lines = [];
        const walker = doc.createTreeWalker(bar, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
          if (node.nodeValue.trim() === "" || node.parentElement.closest("svg") !== null) continue;
          const range = doc.createRange();
          range.selectNodeContents(node);
          lines.push(...Array.from(range.getClientRects()));
        }
        if (lines.length === 0) continue;
        const spill = Math.max(
          box.top - Math.min(...lines.map((line) => line.top)),
          Math.max(...lines.map((line) => line.bottom)) - box.bottom,
          box.left - Math.min(...lines.map((line) => line.left)),
          Math.max(...lines.map((line) => line.right)) - box.right);
        if (spill > 1) {
          addError(`page ${index + 1} title bar text overflows its bar by ${Math.round(spill)}px`, bar);
        }
        for (const picture of bar.querySelectorAll("img, svg")) {
          const area = picture.getBoundingClientRect();
          if (area.width === 0 || area.height === 0) continue;
          const hit = lines.some((line) => Math.min(line.right, area.right) - Math.max(line.left, area.left) > 1
            && Math.min(line.bottom, area.bottom) - Math.max(line.top, area.top) > 1);
          if (hit) addError(`page ${index + 1} title bar text overlaps ${describeElement(picture)}`, picture);
        }
      }
      // Chrome drawn over a page corner, such as a logo stack at the bottom left, is
      // marked data-layout-keepout. A content area may reach beside it, so text in a
      // guard that runs into it is reported, once per text block and picture.
      const corners = Array.from(page.querySelectorAll("[data-layout-keepout] > *"))
        .map((picture) => ({ picture, area: picture.getBoundingClientRect() }))
        .filter(({ area }) => area.width > 0 && area.height > 0);
      for (const guard of corners.length > 0 ? page.querySelectorAll("[data-layout-guard]") : []) {
        const reported = new Set();
        const walker = doc.createTreeWalker(guard, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
          if (node.nodeValue.trim() === "" || node.parentElement.closest(".katex-mathml") !== null) continue;
          const range = doc.createRange();
          range.selectNodeContents(node);
          const lines = Array.from(range.getClientRects());
          for (const { picture, area } of corners) {
            const block = node.parentElement;
            if (reported.has(block) || !lines.some((line) =>
              Math.min(line.right, area.right) - Math.max(line.left, area.left) > 1
              && Math.min(line.bottom, area.bottom) - Math.max(line.top, area.top) > 1)) continue;
            reported.add(block);
            addError(`page ${index + 1} text "${readableText(block).slice(0, 24)}…" runs into the corner `
              + `${describeElement(picture)}`, block);
          }
        }
      }
      // A block whose last line holds only a few characters wastes a full line of
      // height, and that line is what the block above or below it needed: the fix is a
      // line break, a column width, a page split, or on a report page a sentence
      // rewritten. Shortening the words to fit made a definition no one could read.
      // Scope: any block-level element that directly contains text because a tag
      // whitelist missed styled divs. Container elements hold only child elements,
      // so they filter out here. A code block is left out: its lines are the source,
      // prompt or log as written, and no rewording can fill a tail there. A report's
      // paragraph cut at the foot of a column ends in the part that goes on in the next,
      // and that part is judged with the lines of the parts before it. A reference in the
      // list is cited as published and has no sentence to rewrite.
      const report = state.artifact.layout === "report";
      const tails = page.querySelectorAll(report ? ".column > p:not(.split), .column li:not(ol.bib > li)" : "[data-layout-guard] *");
      for (const block of tails) {
        if (block.closest("pre") !== null) continue;
        const style = doc.defaultView.getComputedStyle(block);
        if (!/^(block|list-item|table-cell)$/.test(style.display)) continue;
        const hasDirectText = Array.from(block.childNodes).some(
          (node) => node.nodeType === Node.TEXT_NODE && node.nodeValue.trim() !== "");
        if (!hasDirectText) continue;
        const fontSize = parseFloat(style.fontSize) || 16;
        // A block one line tall has no last line to waste. Its rects can still fall into
        // two groups when an inline box sits well below the baseline, which a subscript or
        // one of KaTeX's own boxes does, and that reported one-line bullets as wasteful.
        const lineHeight = parseFloat(style.lineHeight) || fontSize * 1.2;
        const parts = [block];
        if (report) {
          const flowed = Array.from(doc.querySelectorAll(".column > p"));
          for (let at = flowed.indexOf(parts[0]); at > 0 && parts[0].classList.contains("cont"); at -= 1) parts.unshift(flowed[at - 1]);
        }
        if (parts.reduce((sum, part) => sum + Math.round(part.getBoundingClientRect().height / lineHeight), 0) < 2) continue;
        const lineSets = parts.map((part) => {
          const range = doc.createRange();
          range.selectNodeContents(part);
          return groupLines(Array.from(range.getClientRects()), fontSize);
        });
        const lines = lineSets[lineSets.length - 1];
        const widths = lineSets.flat().map((l) => l.right - l.left);
        if (widths.length < 2 || lines.length === 0) continue;
        const last = widths[widths.length - 1];
        const widest = Math.max(...widths.slice(0, -1));
        // A tail is wasteful when it is tiny in absolute terms (a few characters)
        // or tiny relative to the block's own line width (a wide block whose
        // last line carries a fraction of what the lines above carry).
        if (last <= Math.max(fontSize * 6, widest * 0.25)) {
          const label = readableText(block).slice(0, 24);
          // The tail's own width is the room to make or fill: fitting it took a
          // fix-rebuild-inspect round before, just to learn how far off it was.
          // Its words are the ones to bring back up. The label shows only how the block
          // starts, and finding where it ended took opening the page.
          addError(`page ${index + 1} ${block.tagName.toLowerCase()} "${label}…" wastes its last line `
            + `on a ${Math.round(last)}px tail "${lineText(block, lines[lines.length - 1])}"`, block);
        }
      }
      // A report's columns end on the foot of the text area on every page but the last
      // (KITS 10.10). One the pour could not stretch that far ends short, which shows as a
      // ragged foot, and how far short says how much the content has to give.
      if (report && index < pages.length - 1) {
        for (const [at, column] of Array.from(page.querySelectorAll(".column")).entries()) {
          const last = column.lastElementChild;
          if (last === null || column.offsetHeight === 0) continue;
          const box = column.getBoundingClientRect();
          const short = (box.bottom - last.getBoundingClientRect().bottom) / (box.height / column.offsetHeight) * 0.75;
          if (short > 1) addWarning(`page ${index + 1} column ${at + 1} ends ${short.toFixed(1)}pt above the foot of the text area`, column);
        }
      }
      if (report) {
        // A section or subsection head stands with at least two lines of its text in the
        // same column (KITS 10.11): one left at a column's foot reads as the end of a part.
        for (const [at, column] of Array.from(page.querySelectorAll(".column")).entries()) {
          for (const head of column.querySelectorAll(":scope > :is(h2, h3)")) {
            let next = head.nextElementSibling;
            while (next !== null && (/^H[23]$/.test(next.tagName) || next.tagName === "FIGURE")) next = next.nextElementSibling;
            const fontSize = parseFloat(doc.defaultView.getComputedStyle(head).fontSize) || 16;
            let lines = 0;
            if (next !== null) {
              const range = doc.createRange();
              range.selectNodeContents(next);
              lines = groupLines(Array.from(range.getClientRects()), fontSize).length;
            }
            if (next === null || (lines < 2 && next.classList.contains("split"))) {
              addError(`page ${index + 1} head "${readableText(head).slice(0, 32)}" stands at the foot of column ${at + 1} `
                + "without two lines of its text", head);
            }
          }
        }
        // A justified Korean line that opens its Hangul past --letter-cap (KITS 10.12) reads
        // as letters standing apart. A letter's box takes in what justification gives it, so
        // a line's opening is the middle width of its Hangul past the width the face gives a
        // Hangul letter set apart; the middle, since a letter beside a Latin word also takes
        // the browser's space between the scripts.
        for (const block of doc.documentElement.lang === "ko" ? page.querySelectorAll(".column > p, .column li") : []) {
          const style = doc.defaultView.getComputedStyle(block);
          const fontSize = parseFloat(style.fontSize) || 16;
          const cap = fontSize * (parseFloat(style.getPropertyValue("--letter-cap")) || 0.05);
          const box = block.getBoundingClientRect();
          const scale = block.offsetHeight > 0 ? box.height / block.offsetHeight : 1;
          const pitch = (parseFloat(style.lineHeight) || fontSize * 1.2) * scale;
          const probe = doc.createElement("span");
          probe.style.cssText = "position: absolute; visibility: hidden; white-space: nowrap; letter-spacing: normal; text-justify: none";
          probe.textContent = "가나다라마바사아자차";
          block.append(probe);
          const natural = probe.getBoundingClientRect().width / 10;
          probe.remove();
          const lines = [];
          const walker = doc.createTreeWalker(block, NodeFilter.SHOW_TEXT);
          for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
            if (node.parentElement.closest('[lang="en"], .katex, code') !== null) continue;
            for (let offset = 0; offset < node.length; offset += 1) {
              if (!/[\uac00-\ud7a3]/.test(node.data[offset])) continue;
              const range = doc.createRange();
              range.setStart(node, offset);
              range.setEnd(node, offset + 1);
              const rect = range.getBoundingClientRect();
              if (rect.width === 0) continue;
              const middle = (rect.top + rect.bottom) / 2;
              let line = lines.find((entry) => Math.abs(entry.middle - middle) < pitch / 2);
              if (line === undefined) lines.push(line = { middle, top: rect.top, bottom: rect.bottom, widths: [] });
              line.widths.push(rect.width);
            }
          }
          let worst = null;
          for (const line of lines) {
            const widths = line.widths.slice().sort((x, y) => x - y);
            const opening = (widths[widths.length >> 1] - natural) / scale;
            if (opening > cap + 0.15 && (worst === null || opening > worst.opening)) worst = { opening, line };
          }
          if (worst !== null) {
            addError(`page ${index + 1} ${block.tagName.toLowerCase()} "${readableText(block).slice(0, 24)}…" opens its letters `
              + `${(worst.opening / fontSize).toFixed(2)}em apart on the line "${lineText(block, { coreTop: worst.line.top, coreBottom: worst.line.bottom })}"`, block);
          }
        }
        // A word space a justified line opens past two thirds of the text's size (KITS 10.12)
        // shows as a hole in the column. The widest one of a block is named with its line.
        for (const block of page.querySelectorAll(".column > p, .column li")) {
          const fontSize = parseFloat(doc.defaultView.getComputedStyle(block).fontSize) || 16;
          const box = block.getBoundingClientRect();
          const scale = block.offsetHeight > 0 ? box.height / block.offsetHeight : 1;
          let widest = null;
          const walker = doc.createTreeWalker(block, NodeFilter.SHOW_TEXT);
          for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
            if (node.parentElement.closest(".katex, code, pre") !== null) continue;
            for (let offset = node.data.indexOf(" "); offset !== -1; offset = node.data.indexOf(" ", offset + 1)) {
              const range = doc.createRange();
              range.setStart(node, offset);
              range.setEnd(node, offset + 1);
              const space = range.getBoundingClientRect();
              const width = space.width / scale;
              if (space.height > 0 && width > fontSize * 2 / 3 && (widest === null || width > widest.width)) {
                widest = { width, line: { coreTop: space.top, coreBottom: space.bottom } };
              }
            }
          }
          if (widest !== null) {
            addError(`page ${index + 1} ${block.tagName.toLowerCase()} "${readableText(block).slice(0, 24)}…" opens a word space `
              + `to ${(widest.width * 0.75).toFixed(1)}pt on the line "${lineText(block, widest.line)}"`, block);
          }
        }
      }
      // Text placed with baseline-shift, alignment-baseline, or a tspan's dominant-baseline
      // is moved by Chromium and left on the baseline by Firefox, the browser this check
      // and the PDF use. Subscripts dropped through boxes and table rules in a reviewer's
      // browser while the check, measuring them unmoved, passed them. dy and y move text
      // the same way in both.
      for (const svg of page.querySelectorAll("svg")) {
        const shifted = new Map();
        for (const text of svg.querySelectorAll("text, tspan, textPath")) {
          const style = text.getAttribute("style") ?? "";
          const names = ["baseline-shift", "alignment-baseline"];
          if (text.tagName !== "text") names.push("dominant-baseline");
          for (const name of names) {
            if (text.hasAttribute(name) || style.includes(name)) shifted.set(name, (shifted.get(name) ?? 0) + 1);
          }
        }
        for (const [name, count] of shifted) {
          addError(`page ${index + 1} ${describeElement(svg)} places ${count} text ${count === 1 ? "run" : "runs"} `
            + `with ${name}, which Firefox ignores, so this check and the PDF draw them unmoved. `
            + "Move them with dy instead, and set a subscript or superscript as KaTeX math in a <foreignObject>", svg);
        }
      }
      const marked = neutral ? semicolonsIn(page, true) : [];
      if (marked.length > 0) addError(semicolonNote(`page ${index + 1} text`, marked), marked[0].element);
      // A grid or flex row stretches its items to the row's height unless told otherwise, so
      // a boxed panel beside a taller one drew its border or background far past its content,
      // a height added only to match the neighbour. The panel's own height is read by setting
      // it to the row's start for a moment: a panel with a height of its own, or one already
      // aligned, reads the same. A panel holding nothing is a rule or a stripe, and meant to
      // run the row's height. Also a rule of the neutral guideline.
      const panels = neutral ? Array.from(page.querySelectorAll("[data-layout-guard] *")).filter((element) => {
        if (element.closest("svg") !== null || !inNormalFlow(element) || !seen(element) || !boxed(element)) return false;
        const row = frameWindow().getComputedStyle(element.parentElement);
        return (/grid$/.test(row.display) || (/flex$/.test(row.display) && row.flexDirection.startsWith("row")))
          && !meetsBoxedNeighbour(element);
      }) : [];
      const stretched = panels.map((panel) => panel.offsetHeight);
      const styles = panels.map((panel) => panel.getAttribute("style"));
      for (const panel of panels) panel.style.setProperty("align-self", "start", "important");
      const own = panels.map((panel) => panel.offsetHeight);
      panels.forEach((panel, at) => styles[at] === null
        ? panel.removeAttribute("style") : panel.setAttribute("style", styles[at]));
      for (const [at, panel] of panels.entries()) {
        const style = frameWindow().getComputedStyle(panel);
        const frame = ["paddingTop", "paddingBottom", "borderTopWidth", "borderBottomWidth"]
          .reduce((sum, edge) => sum + parseFloat(style[edge]), 0);
        const content = own[at] - frame;
        const room = stretched[at] - frame;
        // Some room is left alone: a panel a third empty beside a taller one reads well.
        if (content > 0 && content < room / 2 && room - content >= 40) {
          addError(`page ${index + 1} ${describeElement(panel)} is stretched from its own ${own[at]}px `
            + `to its row's ${stretched[at]}px. Let it keep its own height, centered in the row`, panel);
        }
      }
      // A table column whose body cells all say the same words tells the reader nothing row by
      // row: a condition shared by every row stood eight times down a results table. It belongs
      // once outside the columns. A column of one number is a measured tie and is left alone,
      // and so is one member of a compared set whose value varies in the others, a judge who
      // marked every row ✓ beside judges who did not. Also a rule of the neutral guideline.
      for (const table of neutral ? page.querySelectorAll("table") : []) {
        if (table.closest("svg") !== null || !seen(table)) continue;
        // Each row as the cells that cover its columns, a cell spanning rows or columns
        // standing in every place it covers.
        const rows = Array.from(table.rows);
        const carried = [];
        const grid = rows.map((row) => {
          const line = [];
          let column = 0;
          const takeCarried = () => {
            while (carried[column]?.left > 0) {
              line[column] = carried[column].cell;
              carried[column].left -= 1;
              column += 1;
            }
          };
          for (const cell of row.cells) {
            takeCarried();
            for (let across = 0; across < cell.colSpan; across += 1) {
              line[column + across] = cell;
              if (cell.rowSpan > 1) carried[column + across] = { cell, left: cell.rowSpan - 1 };
            }
            column += cell.colSpan;
          }
          for (; column < carried.length; column += 1) takeCarried();
          return line;
        });
        const heading = (row) => row.parentElement.tagName === "THEAD"
          || Array.from(row.cells).every((cell) => cell.tagName === "TH");
        const body = rows.map((row, at) => ({ row, line: grid[at] }))
          .filter(({ row }) => row.parentElement.tagName !== "TFOOT" && !heading(row));
        if (body.length < 3) continue;
        const firstBody = rows.indexOf(body[0].row);
        const header = rows.slice(0, firstBody).map((row, at) => ({ row, line: grid[at] })).filter(({ row }) => heading(row)).pop();
        const columns = Array.from({ length: Math.max(...body.map(({ line }) => line.length)) }, (_, column) =>
          body.map(({ line }) => line[column]));
        const texts = columns.map((cells) => cells.map((cell) => (cell === undefined ? null : readableText(cell))));
        for (const [column, cells] of columns.entries()) {
          if (cells.some((cell) => cell === undefined)) continue;
          const value = texts[column][0];
          if (value === "" || /^[-+−±~≈<>]?\d/.test(value) || texts[column].some((text) => text !== value)) continue;
          if (texts.some((other, at) => at !== column && other.includes(value) && other.some((text) => text !== value))) continue;
          const name = header?.line[column] ? readableText(header.line[column]) : "";
          addError(`page ${index + 1} ${describeElement(table)} column ${name === "" ? column + 1 : `"${name}"`} `
            + `holds "${value.slice(0, 40)}" in all ${cells.length} rows. State it once in the line above the table `
            + "and drop the column", cells[0]);
        }
      }
      // A bullet that cites values a table or figure shows interprets that visual, and its place
      // is the list directly below it. Put under an equation in the next column, it was read as
      // part of the equation's argument while the visual it explained stood apart. Below means
      // drawn under the visual, across part of its width, with no other visual between. A bullet
      // cites a visual when it shares two or more numbers with it and one of them reads as a
      // measured value, with a decimal point or three digits or more. Round numbers alone, the
      // 10, 50 and 90 a waveform sketch marks on its axis, or a count mentioned in passing,
      // tie a bullet to no visual. Also a rule of the neutral guideline.
      const visuals = neutral ? Array.from(page.querySelectorAll("[data-layout-guard] table, [data-layout-guard] svg"))
        .filter((visual) => visual.parentElement.closest("svg") === null && seen(visual)) : [];
      if (visuals.length > 0) {
        const values = (text) => new Set((text.match(/\d[\d,]*(?:\.\d+)?/g) ?? [])
          .map((value) => value.replace(/,/g, "")).filter((value) => value.replace(/\D/g, "").length >= 2));
        const shown = visuals.map((visual) => ({ visual, box: visual.getBoundingClientRect(),
          values: values(visual.tagName === "svg" ? visual.textContent : readableText(visual)) }));
        const below = (list, { visual, box }) => {
          const area = list.getBoundingClientRect();
          return area.top >= box.bottom - 2 && Math.min(area.right, box.right) - Math.max(area.left, box.left) > 0
            && !shown.some((other) => other.visual !== visual && other.box.top >= box.bottom - 2
              && other.box.bottom <= area.top + 2
              && Math.min(area.right, other.box.right) - Math.max(area.left, other.box.left) > 0);
        };
        for (const item of page.querySelectorAll("[data-layout-guard] li")) {
          const list = item.parentElement;
          if (item.closest("table, svg") !== null || list.parentElement.closest("li") !== null || !seen(item)) continue;
          const cited = values(readableText(item));
          const sources = shown.filter(({ values: own }) => {
            const shared = [...cited].filter((value) => own.has(value));
            return shared.length >= 2 && shared.some((value) => value.includes(".") || value.length >= 3);
          });
          if (sources.length === 0 || sources.some((source) => below(list, source))) continue;
          const visual = sources[0].visual;
          addError(`page ${index + 1} li "${readableText(item).slice(0, 30)}…" cites values of `
            + `${describeElement(visual)} but is not in the list directly below it. ${INTERPRETATION_ADVICE}`, item);
        }
      }
      // A plot axis numbered without a name. A reader reads the axes first, and numbers alone
      // do not say what is counted or in what unit. An axis is three or more numbers in a row
      // or a column, in order and evenly spaced, beside a line drawn along them, which keeps a
      // column of figures in a drawn table out. A filled shape is a panel's background, not a
      // line. Its name is other text or a foreignObject just past the numbers on the far side
      // from the line, or just past the axis's far end, above a column or right of a row, where
      // the name of a value axis often sits, or for a row a plot title above it. A title
      // outside the drawing, in a caption, is not seen, so this is a warning. Also a rule of the
      // neutral guideline.
      for (const svg of neutral ? page.querySelectorAll("[data-layout-guard] svg") : []) {
        if (svg.parentElement.closest("svg") !== null || !seen(svg)) continue;
        const numbers = [];
        const words = [];
        for (const text of svg.querySelectorAll("text")) {
          const content = text.textContent.trim();
          if (content === "" || !seen(text)) continue;
          const box = text.getBoundingClientRect();
          const number = content.match(/^([-+−]?(?:\d[\d,]*(?:\.\d+)?|\.\d+))\s*%?$/);
          if (number === null) words.push(box);
          else numbers.push({ box, value: parseFloat(number[1].replace(/,/g, "").replace("−", "-")) });
        }
        if (numbers.length < 3) continue;
        for (const object of svg.querySelectorAll("foreignObject")) {
          if (seen(object)) words.push(object.getBoundingClientRect());
        }
        const strokes = Array.from(svg.querySelectorAll("line, polyline, path, rect")).filter((shape) => {
          if (!seen(shape)) return false;
          const box = shape.getBoundingClientRect();
          const fill = frameWindow().getComputedStyle(shape).fill;
          return shape.matches("line, polyline") || Math.min(box.width, box.height) <= 3
            || fill === "none" || fill === "transparent" || /^rgba\(.*,\s*0\)$/.test(fill);
        }).map((shape) => shape.getBoundingClientRect());
        const sizes = numbers.map(({ box }) => box.height).sort((a, b) => a - b);
        const size = sizes[Math.floor(sizes.length / 2)];
        // A box in the axis's own terms: along it from a0 to a1, across it from c0 to c1. A row's
        // numbers share their middle, a column's their right or their left edge.
        const rowOf = (box) => ({ a0: box.left, a1: box.right, c0: box.top, c1: box.bottom });
        const columnOf = (box) => ({ a0: box.top, a1: box.bottom, c0: box.left, c1: box.right });
        const axes = [
          { name: "horizontal", of: rowOf, key: (box) => (box.top + box.bottom) / 2 },
          { name: "vertical", of: columnOf, key: (box) => box.right },
          { name: "vertical", of: columnOf, key: (box) => box.left },
        ];
        const middle = (place) => (place.a0 + place.a1) / 2;
        const used = new Set();
        // Panels repeating one axis are reported once, with how many there are.
        const unnamed = new Map();
        for (const axis of axes) {
          const sorted = numbers.filter((number) => !used.has(number))
            .sort((a, b) => axis.key(a.box) - axis.key(b.box));
          const groups = [];
          for (const number of sorted) {
            const last = groups[groups.length - 1];
            if (last && axis.key(number.box) - axis.key(last[0].box) <= size / 2) last.push(number);
            else groups.push([number]);
          }
          // Panels side by side put their axes in one row: an axis ends where the spacing
          // jumps or the numbers turn back.
          const runs = [];
          for (const group of groups) {
            const at = (number) => middle(axis.of(number.box));
            group.sort((a, b) => at(a) - at(b));
            let run = [];
            for (const number of group) {
              const [before, last] = run.slice(-2);
              if (last !== undefined) {
                const step = number.value - last.value;
                const gap = at(number) - at(last);
                const turned = before !== undefined && (Math.sign(step) !== Math.sign(last.value - before.value)
                  || gap > 1.5 * (at(last) - at(before)) || 1.5 * gap < at(last) - at(before));
                if (step === 0 || gap <= 0 || turned) {
                  runs.push(run);
                  run = [];
                }
              }
              run.push(number);
            }
            runs.push(run);
          }
          for (const run of runs) {
            if (run.length < 3) continue;
            // Tick numbers step evenly, by a sum on a linear axis or a factor on a logarithmic
            // one. Values printed beside marks do not, though they may happen to stand in a line.
            const values = run.map(({ value }) => value);
            const steadily = (changes) => changes.every((change) => Math.abs(change - changes[0]) <= 0.01 * Math.abs(changes[0]));
            const factors = values.every((value) => value > 0) || values.every((value) => value < 0)
              ? values.slice(1).map((value, at) => value / values[at]) : null;
            if (!steadily(values.slice(1).map((value, at) => value - values[at]))
              && !(factors !== null && steadily(factors))) continue;
            const places = run.map(({ box }) => axis.of(box));
            const c0 = Math.min(...places.map((place) => place.c0));
            const c1 = Math.max(...places.map((place) => place.c1));
            const a0 = Math.min(...places.map((place) => place.a0));
            const a1 = Math.max(...places.map((place) => place.a1));
            const from = middle(places[0]);
            const to = middle(places[places.length - 1]);
            // The line the numbers mark runs along most of them, its near edge close to them.
            // The name goes past the numbers on its other side.
            const sides = new Set();
            for (const stroke of strokes.map((box) => axis.of(box))) {
              if (Math.min(stroke.a1, to) - Math.max(stroke.a0, from) < 0.8 * (to - from)) continue;
              if (stroke.c1 <= c0 + size / 2 && c0 - stroke.c1 <= 2 * size) sides.add("past");
              else if (stroke.c0 >= c1 - size / 2 && stroke.c0 - c1 <= 2 * size) sides.add("before");
            }
            if (sides.size === 0) continue;
            run.forEach((number) => used.add(number));
            const named = words.map((box) => axis.of(box)).some((word) => {
              // Past the numbers anywhere along them, so one title shared by a row of panels
              // names each panel's axis.
              const past = sides.has("past") && word.c0 >= c1 - size / 3 && word.c0 - c1 <= 3 * size;
              const before = sides.has("before") && word.c1 <= c0 + size / 3 && c0 - word.c1 <= 3 * size;
              // The far end: within half a number's height above a column's top number and over
              // the column, where a panel's own title, set further up, does not sit. A name there
              // may start a little left of the numbers. Right of a row's last number.
              const end = axis.name === "vertical"
                ? word.a1 <= a0 + size / 3 && a0 - word.a1 <= size / 2 && word.c1 >= c0 && word.c0 <= c1 + 2 * size
                : word.a0 >= a1 - size / 3 && word.a0 - a1 <= 2 * size && word.c1 >= c0 - 2 * size && word.c0 <= c1 + 2 * size;
              // A row's quantity is often stated by the title of the plot above it.
              const over = axis.name === "horizontal" && word.c1 <= c0 && word.a1 >= from && word.a0 <= to;
              return past || before || end || over;
            });
            if (named) continue;
            const key = `${axis.name} axis ${values.join(", ")}`;
            unnamed.set(key, (unnamed.get(key) ?? 0) + 1);
          }
        }
        for (const [key, count] of unnamed) {
          const [kind, numbered] = key.split(" axis ");
          addWarning(`page ${index + 1} ${describeElement(svg)} numbers `
            + (count === 1 ? `its ${kind} axis ${numbered} without naming it` : `${count} ${kind} axes ${numbered} without naming them`)
            + ". Name the axis by its quantity and unit in the drawing (neutral 5.8)", svg);
        }
      }
      // An image drawn in another shape than its source's. Inside its box, object-fit fill
      // stretches the picture to the content box, and every other value keeps its
      // proportions, so letterboxing and a frame of padding or border are not stretching.
      // Outside the box, a CSS transform on the image or an ancestor can stretch it too, or
      // undo a stretch, so the two are taken together.
      for (const image of page.querySelectorAll("img")) {
        if (image.closest("svg") || image.naturalWidth === 0 || image.naturalHeight === 0 || !seen(image)) continue;
        const style = frameWindow().getComputedStyle(image);
        let scaleX = 1;
        let scaleY = 1;
        if (style.objectFit === "fill") {
          const inner = (size, ...edges) => parseFloat(size)
            - (style.boxSizing === "border-box" ? edges.reduce((sum, edge) => sum + parseFloat(edge), 0) : 0);
          scaleX = inner(style.width, style.paddingLeft, style.paddingRight, style.borderLeftWidth, style.borderRightWidth)
            / image.naturalWidth;
          scaleY = inner(style.height, style.paddingTop, style.paddingBottom, style.borderTopWidth, style.borderBottomWidth)
            / image.naturalHeight;
        }
        if (!(scaleX > 0 && scaleY > 0)) continue;
        const drawn = pageTransform(page, image).multiply(new (frameWindow().DOMMatrix)([scaleX, 0, 0, scaleY, 0, 0]));
        const stretch = unevenness(drawn.a, drawn.b, drawn.c, drawn.d);
        if (stretch > 1 + STRETCH_TOLERANCE) {
          addError(`page ${index + 1} ${describeElement(image)} is drawn stretched, one axis `
            + `${stretch.toFixed(2)} times the other. Keep its source proportions`, image);
        }
      }
      // Text drawn wider or taller than its font, in an SVG through its viewBox mapping or a
      // transform, and in HTML through CSS transforms. An SVG's screen matrix takes in every
      // transform above it, CSS ones included. Shapes stretched with the drawing are left
      // alone: only letters are distorted by it.
      for (const svg of page.querySelectorAll("svg")) {
        if (svg.parentElement?.closest("svg")) continue;
        let count = 0;
        let worst = 1;
        for (const text of svg.querySelectorAll("text")) {
          if (!seen(text)) continue;
          const matrix = text.getScreenCTM();
          if (matrix === null) continue;
          const stretch = unevenness(matrix.a, matrix.b, matrix.c, matrix.d);
          if (stretch > 1 + STRETCH_TOLERANCE) {
            count += 1;
            worst = Math.max(worst, stretch);
          }
        }
        if (count > 0) {
          addError(`page ${index + 1} ${describeElement(svg)} draws ${count} text ${count === 1 ? "run" : "runs"} `
            + `stretched, one axis ${worst.toFixed(2)} times the other. Scale the drawing evenly where it `
            + "holds text", svg);
        }
      }
      const transformed = Array.from(page.querySelectorAll("*")).filter((element) =>
        !element.closest("svg") && frameWindow().getComputedStyle(element).transform !== "none");
      const lettered = new Set();
      for (const element of transformed) {
        for (const candidate of [element, ...element.querySelectorAll("*")]) {
          if (candidate.closest("svg") || !seen(candidate)) continue;
          if (Array.from(candidate.childNodes).some((node) => node.nodeType === 3 && node.data.trim() !== "")) {
            lettered.add(candidate);
          }
        }
      }
      const stretchedText = Array.from(lettered)
        .map((element) => {
          const matrix = pageTransform(page, element);
          return { element, stretch: unevenness(matrix.a, matrix.b, matrix.c, matrix.d) };
        })
        .filter((entry) => entry.stretch > 1 + STRETCH_TOLERANCE);
      if (stretchedText.length > 0) {
        const worst = Math.max(...stretchedText.map((entry) => entry.stretch));
        addError(`page ${index + 1} text in ${stretchedText.length} ${stretchedText.length === 1 ? "place" : "places"} `
          + `is drawn stretched by a CSS transform, one axis ${worst.toFixed(2)} times the other. `
          + "Scale text evenly", stretchedText[0].element);
      }
      // An arrowhead needs plain line behind it to read as an arrow. The straight stretch
      // it sits on runs back to the last bend, or to where the line begins, often a
      // junction with another line or a box edge. A 10-unit drop from a bus under a 7-unit
      // head showed 3 units of line, and the head seemed to touch the corner it left from.
      // A head is reported when the line it leaves visible is shorter than half the head,
      // or than two stroke widths for a small head. Half a head keeps a short arrow whose
      // line still shows, as 8 units behind a 12.6-unit head do. On a straight line
      // headed at both ends, both heads share the line and it is reported once.
      for (const svg of page.querySelectorAll("svg")) {
        for (const line of svg.querySelectorAll("path, line, polyline")) {
          const style = frameWindow().getComputedStyle(line);
          const strokeWidth = parseFloat(style.strokeWidth) || 1;
          const reaches = [false, true].map((atStart) => {
            const named = (atStart ? style.markerStart : style.markerEnd).match(/url\(["']?#([^"')]+)["']?\)/);
            const marker = named ? line.ownerDocument.getElementById(named[1]) : null;
            if (!(marker instanceof frameWindow().SVGMarkerElement)) return 0;
            return arrowheadReach(marker, strokeWidth, atStart) ?? 0;
          });
          for (const atStart of [false, true]) {
            const reach = reaches[atStart ? 1 : 0];
            if (reach === 0) continue;
            const shaft = Math.max(reach / 2, 2 * strokeWidth);
            const bend = bendWithin(line, atStart, reach + shaft);
            const other = reaches[atStart ? 0 : 1];
            if (bend === null && other > 0 && atStart) continue;
            const run = bend ?? line.getTotalLength();
            const visible = run - reach - (bend === null ? other : 0);
            if (visible >= shaft) continue;
            const round = (value) => Math.round(value * 10) / 10;
            const stretch = bend === null ? `is a ${round(run)}-unit straight line`
              : atStart ? `starts with a ${round(run)}-unit line before its first bend`
                : `ends with a ${round(run)}-unit line after its last bend`;
            const shown = visible > 0 ? `only ${round(visible)} units of line show behind the head`
              : bend === null ? "the head covers the line" : "the head covers the bend";
            addError(`page ${index + 1} ${describeElement(svg)} ${describeElement(line)} ${stretch}`
              + ` under a ${round(reach)}-unit arrowhead, so ${shown}. `
              + (bend === null ? "Shorten the head or lengthen the line" : "Shorten the head or move the bend back"), line);
          }
        }
      }
      // An SVG viewport hides whatever falls outside its viewBox, and no box-model
      // measurement sees it: the element reports the same scroll and client size
      // either way. getBBox holds the drawing's geometry, which is what the viewBox has
      // to cover. An arrow head bleeds a sliver past it that no reader sees, and that paint
      // stays out of the comparison. A shape's border is checked below on its own.
      for (const svg of Array.from(page.querySelectorAll("svg")).map((element) => {
        const view = element.viewBox?.baseVal;
        if (!view || view.width === 0 || view.height === 0) return null;
        let box;
        try {
          box = element.getBBox();
        } catch {
          return null;
        }
        if (box.width === 0 && box.height === 0) return null;
        return { element, view, box };
      }).filter((entry) => entry !== null)) {
        const { view, box } = svg;
        const drawn = {
          left: box.x,
          top: box.y,
          right: box.x + box.width,
          bottom: box.y + box.height,
        };
        const cut = {
          left: view.x - drawn.left,
          top: view.y - drawn.top,
          right: drawn.right - (view.x + view.width),
          bottom: drawn.bottom - (view.y + view.height),
        };
        const tolerance = {
          x: Math.max(1, view.width * 0.005),
          y: Math.max(1, view.height * 0.005),
        };
        const sides = Object.entries(cut)
          .filter(([side, amount]) => amount > (side === "top" || side === "bottom" ? tolerance.y : tolerance.x))
          .map(([side, amount]) => `${side} by ${Math.round(amount)}`);
        if (sides.length > 0) {
          addError(
            `page ${index + 1} ${describeElement(svg.element)} draws outside its viewBox and is cut off (${sides.join(", ")})`,
            svg.element);
        }
        // Half of a shape's border lies outside its geometry, which getBBox leaves out, so a
        // box drawn against the viewBox edge passed the check above while the outer half of
        // its border was cut: readers saw that side drawn thinner. A closed shape whose
        // border loses more than half of its outer half at an edge is reported, measured in
        // the svg's own units. Sides already reported above are not repeated.
        const toView = svg.element.getScreenCTM()?.inverse();
        const clipped = [];
        for (const shape of svg.element.querySelectorAll("rect:not([data-html-slot]), circle, ellipse, polygon")) {
          if (toView === undefined || shape.closest("defs, symbol, clipPath, mask, pattern, marker") !== null) continue;
          const paint = doc.defaultView.getComputedStyle(shape);
          const width = parseFloat(paint.strokeWidth);
          if (paint.stroke === "none" || paint.visibility === "hidden" || !(width > 0)) continue;
          const bbox = safeBBox(shape);
          const own = shape.getScreenCTM();
          if (bbox === null || own === null || (bbox.width === 0 && bbox.height === 0)) continue;
          const matrix = toView.multiply(own);
          const corners = [[bbox.x, bbox.y], [bbox.x + bbox.width, bbox.y],
                           [bbox.x, bbox.y + bbox.height], [bbox.x + bbox.width, bbox.y + bbox.height]]
            .map(([x, y]) => [matrix.a * x + matrix.c * y + matrix.e, matrix.b * x + matrix.d * y + matrix.f]);
          const half = (width / 2) * Math.sqrt(Math.abs(matrix.a * matrix.d - matrix.b * matrix.c));
          const lost = {
            left: view.x - (Math.min(...corners.map(([x]) => x)) - half),
            top: view.y - (Math.min(...corners.map(([, y]) => y)) - half),
            right: Math.max(...corners.map(([x]) => x)) + half - (view.x + view.width),
            bottom: Math.max(...corners.map(([, y]) => y)) + half - (view.y + view.height),
          };
          const edges = Object.entries(lost)
            .filter(([side, amount]) => amount > half / 2 && !sides.some((entry) => entry.startsWith(`${side} `)))
            .map(([side]) => side);
          const corner = `${Math.round(Math.min(...corners.map(([x]) => x)))},${Math.round(Math.min(...corners.map(([, y]) => y)))}`;
          if (edges.length > 0) clipped.push(`${describeElement(shape)} at (${corner}) cut at the ${edges.join(" and ")}`);
        }
        if (clipped.length > 0) {
          addError(
            `page ${index + 1} ${describeElement(svg.element)} cuts off the border of ${clipped.length} shape`
            + `${clipped.length > 1 ? "s" : ""} at its viewBox edge (${clipped.slice(0, 3).join(", ")}`
            + `${clipped.length > 3 ? ", and more" : ""}). Keep each border inside the viewBox by half its stroke width`,
            svg.element);
        }
        // The opposite mistake: page space the drawing does not use. It comes from two
        // places at once. A viewBox roomier than the drawing leaves space inside, and an
        // element box of a different shape from the viewBox leaves a band above and below
        // or at both sides, because the rendering keeps the viewBox's proportions. The page
        // pays for the element box either way, so the strips are measured from it to the
        // drawing, in the pixels the strip actually occupies.
        const room = svg.element.getBoundingClientRect();
        const placed = placeViewBox(svg.element, view, room);
        const empty = {
          left: placed.x + (box.x - view.x) * placed.scaleX,
          top: placed.y + (box.y - view.y) * placed.scaleY,
          right: room.width - (placed.x + (box.x + box.width - view.x) * placed.scaleX),
          bottom: room.height - (placed.y + (box.y + box.height - view.y) * placed.scaleY),
        };
        const idle = Object.entries(empty)
          .filter(([side, pixels]) => {
            const across = side === "top" || side === "bottom";
            const share = pixels / (across ? room.height : room.width);
            return share >= 0.25 && pixels >= 100;
          })
          .map(([side, pixels]) => {
            const across = side === "top" || side === "bottom";
            const whole = across ? room.height : room.width;
            return `${side} ${Math.round((pixels / whole) * 100)}%, ${Math.round(pixels)}px of ${Math.round(whole)}`;
          });
        if (idle.length > 0) {
          addError(
            `page ${index + 1} ${describeElement(svg.element)} reserves space it does not draw in (${idle.join("; ")})`,
            svg.element);
        }
        // Two labels printed over each other are unreadable, and nothing else in this
        // file sees it: both sit inside the viewBox and the drawing fills its box.
        // Only labels are compared, because text over a shape or a line is normal.
        // A label box carries glyph padding, so neighbouring lines touch by a few
        // pixels as a matter of course; a collision covers much of both boxes.
        // Boxes and labels are read in the svg's own viewport space, so a group's
        // translate counts: read in their own space, a label in a moved group was
        // compared against one a hundred pixels away as if they shared a line.
        const inViewport = (node) => {
          const bbox = safeBBox(node);
          const ctm = node.getCTM();
          if (bbox === null || ctm === null || bbox.width === 0 || bbox.height === 0) return null;
          const corners = [[bbox.x, bbox.y], [bbox.x + bbox.width, bbox.y],
                           [bbox.x, bbox.y + bbox.height], [bbox.x + bbox.width, bbox.y + bbox.height]]
            .map(([x, y]) => [ctm.a * x + ctm.c * y + ctm.e, ctm.b * x + ctm.d * y + ctm.f]);
          return {
            left: Math.min(...corners.map(([x]) => x)), right: Math.max(...corners.map(([x]) => x)),
            top: Math.min(...corners.map(([, y]) => y)), bottom: Math.max(...corners.map(([, y]) => y)),
          };
        };
        const labels = Array.from(svg.element.querySelectorAll("text"))
          .filter((text) => text.closest("defs, symbol, clipPath, mask, pattern, marker") === null)
          .map((text) => ({ text, box: inViewport(text) }))
          .filter((label) => label.box !== null);
        const printedOver = (a, b) => {
          const across = Math.min(a.right, b.right) - Math.max(a.left, b.left);
          const down = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
          return across > 0 && down > 0
            && across >= Math.min(a.right - a.left, b.right - b.left) * 0.25
            && down >= Math.min(a.bottom - a.top, b.bottom - b.top) * 0.5;
        };
        const collisions = [];
        for (let first = 0; first < labels.length; first++) {
          for (let second = first + 1; second < labels.length; second++) {
            if (printedOver(labels[first].box, labels[second].box)) {
              collisions.push([labels[first].text, labels[second].text]);
            }
          }
        }
        for (const [first, second] of collisions.slice(0, 3)) {
          const name = (node) => `"${labelWords(node)}"`;
          addError(
            `page ${index + 1} ${describeElement(svg.element)} prints two labels over each other (${name(first)} / ${name(second)})`,
            svg.element);
        }
        // A label written on a box stays inside it, and a reader pointed at every one
        // that did not: a 14px sentence ran 30px past a 630px box, a centred 11px label
        // 4px past its 380px box. The box a label sits in is the smallest rect of the
        // same svg that holds the point the label is anchored at (its left edge, its
        // middle or its right edge, by text-anchor); a label on no box is on none. Only
        // the sides are compared: a label that runs off the box's top or bottom is caught
        // as an overlap, or is a caption above the box. The slot the builder leaves where
        // a foreignObject's HTML was lifted out is no box: a label beside a formula sat
        // in the slot's corner and was reported past it.
        const boxes = Array.from(svg.element.querySelectorAll("rect:not([data-html-slot])"))
          .filter((rect) => rect.closest("defs, symbol, clipPath, mask, pattern, marker") === null)
          .map((rect) => inViewport(rect))
          .filter((box) => box !== null);
        let spilled = 0;
        for (const label of labels) {
          const box = label.box;
          const anchor = doc.defaultView.getComputedStyle(label.text).textAnchor;
          const at = {
            x: anchor === "middle" ? (box.left + box.right) / 2 : anchor === "end" ? box.right : box.left,
            y: (box.top + box.bottom) / 2,
          };
          const holder = boxes
            .filter((candidate) => candidate.left <= at.x && at.x <= candidate.right
              && candidate.top <= at.y && at.y <= candidate.bottom)
            .sort((a, b) => (a.right - a.left) * (a.bottom - a.top) - (b.right - b.left) * (b.bottom - b.top))[0];
          if (holder === undefined) continue;
          const past = [["left", holder.left - box.left], ["right", box.right - holder.right]]
            .filter(([, amount]) => amount > 1)
            .map(([side, amount]) => `${side} by ${Math.round(amount)}`);
          if (past.length === 0 || spilled >= 3) continue;
          spilled += 1;
          addError(
            `page ${index + 1} ${describeElement(svg.element)} label "${labelWords(label.text)}" runs past its box (${past.join(", ")})`,
            svg.element);
        }
        // The HTML of a foreignObject, such as a formula or highlighted lines of a file, is
        // lifted into a layer over the drawing, and the checks above never saw it: the
        // layer is no part of the svg. Its lines answer to the same two rules as a label.
        // A line printed over a label hides it, and a line written on a box stays inside
        // the box's sides, the smallest box holding the line's middle. The foreignObject's
        // own box is no limit: nothing clips the lifted text, and a formula a few units
        // past it shows no fault. Lines are read in the svg's viewport space, where the
        // labels and boxes are, through the slot the builder left: its CTM takes the
        // drawing to that space and its screen CTM to the screen. Read in the viewBox's
        // units instead, a line was compared with labels at another scale and was
        // reported over a label a hundred units away.
        const slot = svg.element.querySelector(":scope > rect[data-html-slot]");
        const fromScreen = slot === null ? undefined : slot.getCTM()?.multiply(slot.getScreenCTM().inverse());
        const liftedBoxes = svg.element.parentElement?.classList.contains("svg-html")
          ? Array.from(svg.element.parentElement.querySelectorAll(".svg-html-box")) : [];
        const viewRect = (rect) => {
          const corners = [[rect.left, rect.top], [rect.right, rect.bottom]]
            .map(([x, y]) => [fromScreen.a * x + fromScreen.c * y + fromScreen.e,
                              fromScreen.b * x + fromScreen.d * y + fromScreen.f]);
          return {
            left: Math.min(...corners.map(([x]) => x)), right: Math.max(...corners.map(([x]) => x)),
            top: Math.min(...corners.map(([, y]) => y)), bottom: Math.max(...corners.map(([, y]) => y)),
          };
        };
        let liftedFaults = 0;
        for (const lifted of liftedBoxes) {
          if (fromScreen === undefined || liftedFaults >= 3) break;
          // The layer is scaled to the viewBox, and its letters with it.
          const scale = lifted.offsetWidth > 0 ? lifted.getBoundingClientRect().width / lifted.offsetWidth : 1;
          const fontSize = (parseFloat(doc.defaultView.getComputedStyle(lifted).fontSize) || 16) * scale;
          // Only the letters: a pre or div holding them is a box as wide as the slot, and
          // read as a line it would cover every label beside the text.
          const range = doc.createRange();
          const letters = [];
          const walker = doc.createTreeWalker(lifted, NodeFilter.SHOW_TEXT);
          for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
            if (node.nodeValue.trim() === "" || node.parentElement.closest(".katex-mathml") !== null) continue;
            range.selectNodeContents(node);
            letters.push(...range.getClientRects());
          }
          const lines = groupLines(letters, fontSize).map(viewRect);
          const words = readableText(lifted).slice(0, 30);
          const hidden = labels.find((label) => lines.some((line) => printedOver(line, label.box)));
          if (hidden !== undefined) {
            liftedFaults += 1;
            addError(
              `page ${index + 1} ${describeElement(svg.element)} HTML "${words}" prints over label "${labelWords(hidden.text)}"`,
              svg.element);
          }
          for (const line of lines) {
            const x = (line.left + line.right) / 2;
            const y = (line.top + line.bottom) / 2;
            const holder = boxes
              .filter((candidate) => candidate.left <= x && x <= candidate.right
                && candidate.top <= y && y <= candidate.bottom)
              .sort((a, b) => (a.right - a.left) * (a.bottom - a.top) - (b.right - b.left) * (b.bottom - b.top))[0];
            if (holder === undefined) continue;
            const past = [["left", holder.left - line.left], ["right", line.right - holder.right]]
              .filter(([, amount]) => amount > 1)
              .map(([side, amount]) => `${side} by ${Math.round(amount)}`);
            if (past.length === 0) continue;
            liftedFaults += 1;
            addError(
              `page ${index + 1} ${describeElement(svg.element)} HTML "${words}" runs past its box (${past.join(", ")})`,
              svg.element);
            break;
          }
        }
        // A box drawn inside another stays inside it: a step box ended 2 units below the
        // box it sat in once that box was shortened. A rect is held by the smallest rect
        // larger on both axes that holds its centre, and among holders of one size, the
        // one it fits best, so the front outline of a stack of equal offset copies holds
        // what is drawn in it. It is reported when it crosses that holder's edge by more
        // than a unit but by less than a quarter of its own size on that axis: a tag set
        // half over a corner crosses on purpose. A rect that paints nothing, or is turned,
        // takes no part.
        const drawnRects = Array.from(svg.element.querySelectorAll("rect"))
          .filter((rect) => rect.closest("defs, symbol, clipPath, mask, pattern, marker") === null)
          .filter((rect) => {
            const paint = doc.defaultView.getComputedStyle(rect);
            const ctm = rect.getCTM();
            return (paint.fill !== "none" || paint.stroke !== "none") && ctm !== null && ctm.b === 0 && ctm.c === 0;
          })
          .map((rect) => ({ rect, box: inViewport(rect) }))
          .filter((entry) => entry.box !== null);
        const overshoot = (inner, outer) => [
          ["left", outer.left - inner.left, inner.right - inner.left],
          ["right", inner.right - outer.right, inner.right - inner.left],
          ["top", outer.top - inner.top, inner.bottom - inner.top],
          ["bottom", inner.bottom - outer.bottom, inner.bottom - inner.top],
        ];
        const crossing = (inner, outer) => overshoot(inner, outer).reduce((sum, [, amount]) => sum + Math.max(0, amount), 0);
        let poking = 0;
        for (const { rect, box } of drawnRects) {
          const width = box.right - box.left;
          const height = box.bottom - box.top;
          const x = (box.left + box.right) / 2;
          const y = (box.top + box.bottom) / 2;
          const area = (other) => Math.round((other.right - other.left) * (other.bottom - other.top));
          const holder = drawnRects
            .map((entry) => entry.box)
            .filter((other) => other.right - other.left > width + 1 && other.bottom - other.top > height + 1
              && other.left < x && x < other.right && other.top < y && y < other.bottom)
            .sort((a, b) => area(a) - area(b) || crossing(box, a) - crossing(box, b))[0];
          if (holder === undefined) continue;
          const sides = overshoot(box, holder);
          if (sides.some(([, amount, size]) => amount >= size / 4)) continue;
          const crossed = sides.filter(([, amount]) => amount > 1).map(([side, amount]) => `${side} by ${Math.round(amount)}`);
          if (crossed.length === 0 || poking >= 3) continue;
          poking += 1;
          addError(
            `page ${index + 1} ${describeElement(svg.element)} ${describeElement(rect)} runs past the box it is drawn in `
            + `(${crossed.join(", ")}). Fit it inside or grow the box`,
            rect);
        }
        // Where arrows meet boxes. A connector is a path, line or polyline; an end with an
        // arrowhead enters, the other end leaves. An end attaches to the side of the
        // smallest box (a painted rect at least 16 units on each side) that it lies on,
        // within the head's length for an entering end and 3 units for a leaving one.
        // Points are read in the svg's viewport space, as the labels are.
        const at = (element, point) => {
          const m = element.getCTM();
          return { x: m.a * point.x + m.c * point.y + m.e, y: m.b * point.x + m.d * point.y + m.f };
        };
        const panels = drawnRects.map((entry) => entry.box)
          .filter((box) => box.right - box.left >= 16 && box.bottom - box.top >= 16);
        const connectors = [];
        for (const line of svg.element.querySelectorAll("path, line, polyline")) {
          if (line.closest("defs, symbol, clipPath, mask, pattern, marker") !== null || line.getCTM() === null) continue;
          const total = line.getTotalLength();
          if (!(total > 0)) continue;
          const style = doc.defaultView.getComputedStyle(line);
          const strokeWidth = parseFloat(style.strokeWidth) || 1;
          const heads = [true, false].map((atStart) => {
            const named = (atStart ? style.markerStart : style.markerEnd).match(/url\(["']?#([^"')]+)["']?\)/);
            const marker = named ? line.ownerDocument.getElementById(named[1]) : null;
            return marker instanceof frameWindow().SVGMarkerElement ? (arrowheadReach(marker, strokeWidth, atStart) ?? 0) : 0;
          });
          connectors.push({
            line, total, strokeWidth, heads,
            guide: heads[0] === 0 && heads[1] === 0 && style.strokeDasharray !== "none",
            ends: [at(line, line.getPointAtLength(0)), at(line, line.getPointAtLength(total))],
          });
        }
        const sideOf = (point, reach) => {
          const near = Math.max(3, reach + 2);
          let found = null;
          for (const box of panels) {
            const within = (low, high, value) => low - near <= value && value <= high + near;
            const gaps = [
              ["left", Math.abs(point.x - box.left), within(box.top, box.bottom, point.y)],
              ["right", Math.abs(point.x - box.right), within(box.top, box.bottom, point.y)],
              ["top", Math.abs(point.y - box.top), within(box.left, box.right, point.x)],
              ["bottom", Math.abs(point.y - box.bottom), within(box.left, box.right, point.x)],
            ].filter(([, gap, along]) => along && gap <= near).sort((a, b) => a[1] - b[1]);
            if (gaps.length === 0) continue;
            const area = (box.right - box.left) * (box.bottom - box.top);
            if (found === null || area < found.area) found = { box, side: gaps[0][0], area };
          }
          return found;
        };
        const attached = new Map();
        for (const connector of connectors) {
          connector.joins = connector.ends.map((point, end) => {
            const enters = connector.heads[end] > 0;
            const join = sideOf(point, enters ? connector.heads[end] : 0);
            if (join === null) return null;
            const key = `${join.box.left},${join.box.top},${join.box.right},${join.box.bottom}`;
            if (!attached.has(key)) attached.set(key, { box: join.box, sides: { left: [], right: [], top: [], bottom: [] } });
            attached.get(key).sides[join.side].push({ connector, enters });
            return { key, side: join.side };
          });
        }
        const round = (value) => Math.round(value);
        // Points are read in the svg's viewport and reported in its own units, the ones its
        // source is written in.
        const shown = (point) => ({
          x: (point.x - placed.x) / placed.scaleX + view.x, y: (point.y - placed.y) / placed.scaleY + view.y,
        });
        const units = (dx, dy) => Math.hypot(dx / placed.scaleX, dy / placed.scaleY);
        const trace = (connector) => {
          const [from, to] = connector.ends.map(shown);
          return `(${round(from.x)},${round(from.y)})→(${round(to.x)},${round(to.y)})`;
        };
        const panelName = (box) => {
          const first = labels
            .filter(({ box: label }) => label.left >= box.left && label.right <= box.right
              && label.top >= box.top && label.bottom <= box.bottom)
            .sort((a, b) => a.box.top - b.box.top || a.box.left - b.box.left)[0];
          const corner = shown({ x: box.left, y: box.top });
          return `the box at (${round(corner.x)},${round(corner.y)})`
            + (first === undefined ? "" : ` holding "${labelWords(first.text)}"`);
        };
        // A return arrow, one that runs back left or up against the reading order, that
        // enters a box on a side where another connection already sits while another
        // side of that box has none, crowds the busy side. Arrows entering one side
        // together in the reading order, a fan-in, are normal and not reported. Nor is the
        // return's own partner: two boxes joined both ways between the same two sides run
        // on two parallel lanes, the usual drawing of a loop, which a free side would only
        // reach by a detour around a box. A return that leaves its box by another side
        // than the one its partner meets still crowds the busy side.
        const backward = (connector) => {
          const [from, to] = connector.ends;
          return (to.x < from.x - 3 && to.y <= from.y + 3) || (to.y < from.y - 3 && to.x <= from.x + 3);
        };
        const partners = (connector, entry) => {
          const start = connector.joins[0];
          return start !== null && entry.connector.joins.some(
            (join) => join !== null && join.key === start.key && join.side === start.side);
        };
        let crowded = 0;
        for (const connector of connectors) {
          if (connector.heads[1] === 0 || connector.joins[1] === null) continue;
          if (!backward(connector)) continue;
          const { key, side } = connector.joins[1];
          const { box, sides } = attached.get(key);
          const others = sides[side].filter((entry) => entry.connector !== connector && !partners(connector, entry));
          const clear = Object.entries(sides).filter(([, entries]) => entries.length === 0).map(([name]) => name);
          if (others.length === 0 || clear.length === 0 || crowded >= 3) continue;
          crowded += 1;
          addError(
            `page ${index + 1} ${describeElement(svg.element)} return arrow ${trace(connector)} enters ${panelName(box)} `
            + `on its ${side} side beside ${others.map((entry) => trace(entry.connector)).join(", ")}, while its `
            + `${clear.join(" and ")} ${clear.length === 1 ? "side is" : "sides are"} clear. Enter by a clear side`,
            connector.line);
        }
        // An arrowhead, with the stretch of line just before it, that runs over a label or
        // crosses another connector makes the target unclear. The stretch covers the head
        // and twice its length of line before it. Lines that meet at an end, as an arrow
        // into a bus, a branch out of it, the arms of a merge or arrows into one target do,
        // are joined rather than crossed, and a line laid along another, as a span arrow on
        // a reference line is, runs with it. A dashed line without a head is a guide, not a
        // connector. None of these is reported.
        const traced = new Map();
        const pointsOf = (connector) => {
          if (!traced.has(connector)) {
            const points = [];
            for (let step = 0; step <= Math.ceil(connector.total / 2); step++) {
              points.push(at(connector.line, connector.line.getPointAtLength(Math.min(connector.total, step * 2))));
            }
            traced.set(connector, points);
          }
          return traced.get(connector);
        };
        const heading = (points, index) => {
          const a = points[Math.max(0, index - 1)];
          const b = points[Math.min(points.length - 1, index + 1)];
          const length = Math.hypot(b.x - a.x, b.y - a.y) || 1;
          return { x: (b.x - a.x) / length, y: (b.y - a.y) / length };
        };
        const tangles = new Set();
        for (const connector of connectors) {
          for (const end of [0, 1]) {
            const reach = connector.heads[end];
            if (reach === 0 || tangles.size >= 3) continue;
            const stretch = Math.min(connector.total, 3 * reach);
            const approach = [];
            for (let step = 0; step <= 12; step++) {
              const along = (stretch * step) / 12;
              approach.push(at(connector.line, connector.line.getPointAtLength(end === 1 ? connector.total - along : along)));
            }
            const label = labels.find(({ box }) => approach.some((point) => box.left < point.x && point.x < box.right
              && box.top < point.y && point.y < box.bottom));
            let crossed = null;
            const tip = connector.ends[end];
            for (const other of connectors) {
              if (other === connector || crossed !== null || other.guide) continue;
              if (other.ends.some((point) => Math.hypot(point.x - tip.x, point.y - tip.y) <= reach + 2)) continue;
              const near = (connector.strokeWidth + other.strokeWidth) / 2 + 0.5;
              const ends = [...connector.ends, ...other.ends];
              const points = pointsOf(other);
              for (let spot = 0; spot < points.length && crossed === null; spot++) {
                const point = points[spot];
                if (ends.some((tip) => Math.hypot(tip.x - point.x, tip.y - point.y) <= near + 2)) continue;
                const touch = approach.findIndex((sample) => Math.hypot(sample.x - point.x, sample.y - point.y) <= near);
                if (touch < 0) continue;
                const mine = heading(approach, touch);
                const theirs = heading(points, spot);
                if (Math.abs(mine.x * theirs.y - mine.y * theirs.x) >= 0.3) crossed = other;
              }
            }
            if (label === undefined && crossed === null) continue;
            tangles.add(`page ${index + 1} ${describeElement(svg.element)} arrowhead of ${trace(connector)} runs over `
              + (label !== undefined ? `the label "${labelWords(label.text)}"` : `the connector ${trace(crossed)}`));
          }
        }
        for (const message of tangles) addError(message, svg.element);
        // A connector that leaves a box by one side in a short stub and then turns to pass
        // another side of that box, or that enters by one side after a short stub turned
        // from beyond another, takes a bend it does not need: leaving or entering by that
        // other side reaches the same path directly. The reading order's sides (outputs at
        // the right or bottom, inputs at the left or top) are a default that a visibly
        // simpler route overrides, so any side counts, the default ones tried first, as
        // long as the straight piece that replaces the stub and turn crosses no other
        // connector, label or box. A stub is at most three head lengths, 24 units when the
        // connector has no head.
        const cornersOf = (line) => {
          const tag = line.tagName.toLowerCase();
          let points = [];
          if (tag === "line") {
            points = [{ x: line.x1.baseVal.value, y: line.y1.baseVal.value },
                      { x: line.x2.baseVal.value, y: line.y2.baseVal.value }];
          } else if (tag === "polyline") {
            points = Array.from(line.points, (point) => ({ x: point.x, y: point.y }));
          } else {
            const tokens = (line.getAttribute("d") || "").match(/[a-zA-Z]|-?\d*\.?\d+(?:e[-+]?\d+)?/g) || [];
            let x = 0;
            let y = 0;
            let command = "";
            for (let cursor = 0; cursor < tokens.length;) {
              if (/[a-zA-Z]/.test(tokens[cursor])) {
                command = tokens[cursor++];
                if (!/[MmLlHhVv]/.test(command)) return null;
                continue;
              }
              const take = () => Number(tokens[cursor++]);
              if (command === "M" || command === "L") { x = take(); y = take(); }
              else if (command === "m" || command === "l") { x += take(); y += take(); }
              else if (command === "H") x = take();
              else if (command === "h") x += take();
              else if (command === "V") y = take();
              else y += take();
              points.push({ x, y });
              if (command === "M") command = "L";
              if (command === "m") command = "l";
            }
          }
          const placed = points.map((point) => at(line, point));
          return placed.filter((point, spot) => spot === 0
            || Math.hypot(point.x - placed[spot - 1].x, point.y - placed[spot - 1].y) > 0.5);
        };
        const normals = { left: { x: -1, y: 0 }, right: { x: 1, y: 0 }, top: { x: 0, y: -1 }, bottom: { x: 0, y: 1 } };
        const opposite = { left: "right", right: "left", top: "bottom", bottom: "top" };
        const beyond = (point, box, side) => (side === "left" ? point.x < box.left - 1
          : side === "right" ? point.x > box.right + 1 : side === "top" ? point.y < box.top - 1 : point.y > box.bottom + 1);
        const past = (point, box, side) => (side === "left" ? (box.left - point.x) / placed.scaleX
          : side === "right" ? (point.x - box.right) / placed.scaleX
            : side === "top" ? (box.top - point.y) / placed.scaleY : (point.y - box.bottom) / placed.scaleY);
        const unit = (from, to) => {
          const length = Math.hypot(to.x - from.x, to.y - from.y) || 1;
          return { x: (to.x - from.x) / length, y: (to.y - from.y) / length };
        };
        const clearRun = (connector, box, from, to) => {
          const steps = Math.max(1, Math.ceil(Math.hypot(to.x - from.x, to.y - from.y) / 2));
          for (let step = 0; step <= steps; step++) {
            const point = { x: from.x + ((to.x - from.x) * step) / steps, y: from.y + ((to.y - from.y) * step) / steps };
            if (labels.some(({ box: label }) => label.left < point.x && point.x < label.right
              && label.top < point.y && point.y < label.bottom)) return false;
            if (panels.some((other) => other !== box && !(other.left <= box.left && other.right >= box.right
              && other.top <= box.top && other.bottom >= box.bottom)
              && other.left < point.x && point.x < other.right && other.top < point.y && point.y < other.bottom)) return false;
            for (const other of connectors) {
              if (other === connector || other.guide) continue;
              const near = (connector.strokeWidth + other.strokeWidth) / 2 + 0.5;
              if (pointsOf(other).some((spot) => Math.hypot(spot.x - point.x, spot.y - point.y) <= near)) return false;
            }
          }
          return true;
        };
        const onSide = (box, side, toward) => (side === "left" || side === "right"
          ? { x: side === "left" ? box.left : box.right, y: Math.min(box.bottom - 4, Math.max(box.top + 4, toward.y)) }
          : { x: Math.min(box.right - 4, Math.max(box.left + 4, toward.x)), y: side === "top" ? box.top : box.bottom });
        let detours = 0;
        for (const connector of connectors) {
          const corners = cornersOf(connector.line);
          if (corners === null || corners.length < 3 || detours >= 3) continue;
          const stubMost = Math.max(24, 3 * Math.max(...connector.heads));
          // One report per connector, and the end the reader looks at, its head, comes first.
          const ends = [
            { join: connector.joins[1], stub: [corners.at(-2), corners.at(-1)], next: [corners.at(-3), corners.at(-2)], leaving: false },
            { join: connector.joins[0], stub: [corners[0], corners[1]], next: [corners[1], corners[2]], leaving: true },
          ];
          for (const { join, stub, next, leaving } of ends) {
            if (join === null || detours >= 3) continue;
            const stubLength = units(stub[1].x - stub[0].x, stub[1].y - stub[0].y);
            if (stubLength > stubMost) continue;
            const { box } = attached.get(join.key);
            // A step between two boxes whose joined sides face each other, its jog in the gap
            // between them, crosses that gap in reading order and is left alone.
            const across = connector.joins[leaving ? 1 : 0];
            if (across !== null && across.side === opposite[join.side] && corners.length === 4) {
              const normal = normals[join.side];
              const jog = normal.x !== 0 ? next[0].x : next[0].y;
              const from = box[join.side];
              const to = attached.get(across.key).box[across.side];
              const sign = normal.x + normal.y;
              if ((to - from) * sign > 0 && (jog - from) * sign > 0 && (to - jog) * sign > 0) continue;
            }
            const allowed = leaving ? ["right", "bottom", "top", "left"] : ["left", "top", "bottom", "right"];
            const heading = unit(next[0], next[1]);
            const far = leaving ? next[1] : next[0];
            // The turn must lie far enough past the other side to use it: room for a short
            // run when leaving, for the head when entering. Branches that split just above
            // stacked boxes pass their sides by a few units and are left alone.
            const space = leaving ? 12 : 1.5 * connector.heads[1];
            const other = allowed.find((side) => side !== join.side
              && (heading.x * normals[side].x + heading.y * normals[side].y) * (leaving ? 1 : -1) >= 0.9
              && beyond(far, box, side) && past(far, box, side) >= space);
            if (other === undefined) continue;
            const start = onSide(box, other, leaving ? stub[1] : stub[0]);
            const reach = normals[other].x !== 0 ? { x: far.x, y: start.y } : { x: start.x, y: far.y };
            if (!clearRun(connector, box, start, reach)) continue;
            detours += 1;
            addError(
              `page ${index + 1} ${describeElement(svg.element)} connector ${trace(connector)} `
              + (leaving
                ? `leaves ${panelName(box)} by its ${join.side} side, turns after ${Math.round(stubLength)} units and passes its ${other} side. Leave by the ${other} side`
                : `enters ${panelName(box)} by its ${join.side} side after turning ${Math.round(stubLength)} units short of it from beyond its ${other} side. Enter by the ${other} side`),
              connector.line);
            break;
          }
        }
        // A label the deck wrapped (data-wrap) records its line count in data-lines; one
        // that needs more lines than its box allows (data-max-lines) is reported with both.
        for (const text of svg.element.querySelectorAll("text[data-max-lines]")) {
          const needs = Number(text.dataset.lines);
          const allows = Number(text.dataset.maxLines);
          if (!(needs > allows)) continue;
          addError(
            `page ${index + 1} ${describeElement(svg.element)} label "${labelWords(text)}" needs ${needs} lines, box allows ${allows}`,
            svg.element);
        }
        // A label fitted to a box (data-fit) is set at the largest size the box holds and
        // its lines read tight. One that no size sets tight is loose at the size it got;
        // one the box holds at no size does not fit and is drawn at the smallest.
        for (const text of svg.element.querySelectorAll("text[data-fits]")) {
          const words = labelWords(text);
          const where = `${text.dataset.fit} at ${text.dataset.fitSize}px`;
          addError(
            text.dataset.fits === "no"
              ? `page ${index + 1} ${describeElement(svg.element)} label "${words}" does not fit ${where}`
              : `page ${index + 1} ${describeElement(svg.element)} label "${words}" is loose in ${where}`,
            svg.element);
        }
      }
      // In-flow siblings never overlap in normal flow, so any real overlap
      // (negative margins, transforms, oversized absolute children) covers
      // content and is reported as an error.
      for (const guard of page.querySelectorAll("[data-layout-guard]")) {
        const byParent = new Map();
        for (const el of guard.querySelectorAll("*")) {
          const style = doc.defaultView.getComputedStyle(el);
          if (style.display === "none" || style.visibility === "hidden") continue;
          if (style.position === "absolute" || style.position === "fixed") continue;
          if (!/^(block|list-item|table|flex|grid)$/.test(style.display)) continue;
          const rect = el.getBoundingClientRect();
          if (rect.width === 0 || rect.height === 0) continue;
          if (!byParent.has(el.parentElement)) byParent.set(el.parentElement, []);
          byParent.get(el.parentElement).push({ el, rect });
        }
        for (const siblings of byParent.values()) {
          for (let i = 0; i < siblings.length; i++) {
            for (let j = i + 1; j < siblings.length; j++) {
              const a = siblings[i];
              const b = siblings[j];
              const x = Math.min(a.rect.right, b.rect.right) - Math.max(a.rect.left, b.rect.left);
              const y = Math.min(a.rect.bottom, b.rect.bottom) - Math.max(a.rect.top, b.rect.top);
              if (x > 4 && y > 4) {
                addError(`page ${index + 1} ${describeElement(a.el)} overlaps its sibling ${describeElement(b.el)}`, b.el);
              }
            }
          }
        }
      }
    }
    });
    return { errors, warnings };
  }

  function updateLayoutUi() {
    const status = $("#artifact-status");
    const layoutCheck = state.artifact.layout_check;
    const checked = layoutCheck.checked_revision === state.revision;
    const errors = checked ? layoutCheck.errors : [];
    // A server started before warnings existed sends none. It reads this page code from disk,
    // so every review page it served stopped at start until the agent reconnected.
    const warnings = checked ? (layoutCheck.warnings ?? []) : [];
    // An artifact whose main file is missing is not "checking": there is nothing to check,
    // and saying otherwise reads as "wait a moment" forever. Warnings leave it ready.
    status.textContent = state.artifact.error ? "missing"
      : checked ? (errors.length === 0 ? "ready" : "layout error")
      : state.project.layout_checker ? "checking" : "unchecked";
    status.classList.toggle("error", errors.length > 0 || Boolean(state.artifact.error));
    renderProblems(checked, errors, warnings);
  }

  // The Problems tab mirrors what the agent sees in layout(): the artifact error and the
  // build error, then the layout errors and warnings for the current revision.
  function renderProblems(checked, errors, warnings) {
    const list = $("#problems-list");
    const count = $("#problems-count");
    if (list === null) return;
    clear(list);
    const problems = [];
    if (state.artifact.error) problems.push({ kind: "artifact", text: state.artifact.error });
    if (state.artifact.build_error) problems.push({ kind: "build", text: state.artifact.build_error });
    // A check that cannot be reported is worse than one that finds something: the tab said
    // only that nothing had been checked yet, which reads as "wait a moment" forever.
    if (state.layoutCheckError) problems.push({ kind: "check", text: state.layoutCheckError });
    for (const error of errors) problems.push({ kind: "layout", text: error });
    for (const warning of warnings) problems.push({ kind: "warning", text: warning });
    if (!checked && !state.artifact.build_error && problems.length === 0) {
      list.appendChild(h("p", { class: "placeholder", text: "Layout not checked yet for the current revision." }));
    } else if (problems.length === 0) {
      list.appendChild(h("p", { class: "placeholder", text: "No problems." }));
    } else {
      for (const problem of problems) {
        const item = h("div", { class: "problem" });
        item.appendChild(h("span", { class: "problem-kind", text: problem.kind }));
        item.appendChild(h("span", { text: problem.text }));
        if (problem.kind === "layout" || problem.kind === "warning") {
          item.classList.add("clickable");
          item.addEventListener("click", () => revealProblem(problem.text));
        }
        list.appendChild(item);
      }
    }
    count.textContent = String(problems.length);
    count.classList.toggle("hidden", problems.length === 0);
  }
  
  // The element behind a layout error. The review page measures nothing itself, and the
  // server's check names the element by its ref at the end of the message, a path of
  // child positions from the page down. An error without a ref falls back to its page.
  function errorTarget(text) {
    const ref = text.match(/\[p(\d+):([\d.]+)\]$/);
    const number = (ref ?? text.match(/^page (\d+)/) ?? [])[1];
    const page = artifactPages()[Number(number) - 1] ?? null;
    if (page === null || ref === null) return page;
    let element = page;
    for (const index of ref[2].split(".")) element = element?.children[Number(index)];
    return element ?? page;
  }

  // Scrolls the artifact to the element behind a layout error and flashes an
  // outline on it.
  function revealProblem(text) {
    const target = errorTarget(text);
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    const previous = target.style.outline;
    target.style.outline = "3px solid #e0955a";
    target.style.outlineOffset = "2px";
    setTimeout(() => {
      target.style.outline = previous;
      target.style.outlineOffset = "";
    }, 1500);
  }
  
  async function checkArtifactLayout() {
    if (state.slideShow) return;
    const revision = state.revision;
    // Only the document of the revision being reported is measured. The one before an
    // edit stays on show until the next has loaded, and a check scheduled on it ran
    // after the new revision was announced: it reported the old document under the
    // new revision, and then marked the frame settled, so the real check never ran.
    const doc = frameDocument();
    if (doc.documentElement.dataset.htmlMcpRevision !== String(revision)) return;
    // A measurement taken before the fonts or images arrive is reported, so the server knows
    // the page is working, and is taken again once they have; only the later one is kept.
    const settled = doc.fonts.status === "loaded" && Array.from(doc.images).every((image) => image.complete);
    const body = JSON.stringify({
      revision,
      // The code this page runs: the server records a result only from the code it serves.
      static: document.querySelector('meta[name="html-mcp-static"]')?.content ?? null,
      check: checkToken,
      settled,
      ...artifactLayoutFindings(),
      // Space is reported in page pixels, so it is read at the page's own scale too.
      space: unzoomed(() => measureArtifactSpace(frameDocument())),
    });
    let payload;
    try {
      payload = await fetchJson(`${artifactBase()}/layout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      });
      if (settled) $("#artifact-frame").dataset.settled = String(revision);
    } catch (error) {
      state.layoutCheckError =
        `the layout check ran but could not be reported (${String(error.message || error)}); `
        + `the measurement was ${Math.round(body.length / 1024)}KB`;
      updateLayoutUi();
      throw error;
    }
    state.layoutCheckError = null;
    if (state.revision !== revision) return;
    state.artifact = payload;
    // The project state is what the next tab switch reads the artifact back from. Left
    // as it was, it still said the artifact was unchecked, and a frame kept across the
    // switch, which is checked and does not check again, showed "checking" for good.
    state.project.artifacts[state.artifactId] = payload;
    updateLayoutUi();
  }
  
  function scheduleLayoutCheck() {
    // Only the server's own check measures, in a browser it opens with a token. A review
    // page shows that check's result: browsers measure a few pixels apart, and a page on
    // another pixel ratio turned the same content from overflowing to clean and back.
    if (checkToken === null) return;
    if (state.slideShow) return;
    // A frame that has been measured with its fonts in and its images complete has
    // nothing more to say for that revision, and is left alone. The check walks every
    // block of every page, and it was scheduled on every resize, the split being dragged
    // included, as well as on load and on each font and image arriving, so a deck was
    // measured over and over on a tablet that had nothing to learn from it. The mark is
    // the frame's own, taken at the check: the server holding a result is not enough,
    // since the first check runs before the fonts arrive and the one after them is what
    // corrects it.
    if ($("#artifact-frame").dataset.settled === String(state.revision)) return;
    const win = frameWindow();
    if (state.layoutFrame !== null) win.cancelAnimationFrame(state.layoutFrame);
    state.layoutFrame = win.requestAnimationFrame(() => {
      state.layoutFrame = null;
      win.requestAnimationFrame(() => {
        if (!state.slideShow) checkArtifactLayout().catch((error) => console.error(error));
      });
    });
  };
  

  return { scheduleLayoutCheck, updateLayoutUi };
}
