"""Compile content.html into a two-column A4 paper with a report skin.

The title block opens the first page across both columns. Each section of the content is
a numbered section head followed by its blocks, and the whole text runs on from column to
column and page to page, set by the script at the end of the document in the reader's own
browser, which is the only place the lines can be measured.
"""

import html
import re
from pathlib import Path

from ..kits import COMPONENTS, descendants, document_assets, inline_woff2, prepare_body
from ..template_content import ContentParser, Element, parse_template_content


HERE = Path(__file__).parent
SKELETON = HERE / "skeleton.css"

# The flow is built once as a column of blocks, outside the pages, and the script pours a
# copy of it into the columns: a paragraph that reaches the foot of a column is cut after
# its last whole line and goes on at the head of the next, a list is cut between its items,
# and a figure or table stands at the top of a column, this one while it holds only
# figures and the next otherwise, while the text goes on past it. A figure marked wide waits for the top of the next page, across
# both columns, as many as fill no more than 0.7 of it. The fonts change the lines, so the
# flow is poured again once they arrive.
PAGINATE_SCRIPT = r"""<script>
(() => {
  // The width of the hyphen drawn after a line, which a range over its text leaves out.
  const hyphen = (line) => {
    const probe = document.createElement("span");
    probe.textContent = "\u2010";
    probe.style.cssText = "position: absolute; visibility: hidden";
    line.append(probe);
    const width = probe.getBoundingClientRect().width;
    probe.remove();
    return width;
  };
  // Where a line's letters and formulas begin and end: KaTeX's MathML copy is not drawn and
  // its box is another size in each browser, and a hyphen drawn after the line adds its
  // width.
  const extent = (line) => {
    const boxes = [];
    const walker = document.createTreeWalker(line, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const text = walker.currentNode;
      if (text.parentElement.closest(".katex") !== null || text.data.trim() === "") continue;
      const range = document.createRange();
      range.selectNodeContents(text);
      boxes.push(...Array.from(range.getClientRects()).filter((box) => box.width > 0));
    }
    line.querySelectorAll(".katex-html").forEach((formula) => boxes.push(formula.getBoundingClientRect()));
    if (boxes.length === 0) return null;
    const after = line.classList.contains("h") ? hyphen(line) : 0;
    return { left: Math.min(...boxes.map((box) => box.left)), right: Math.max(...boxes.map((box) => box.right)) + after };
  };
  // The number of word spaces of a line, a run of spaces counting once, outside math and
  // code and not at its ends.
  const spacesOf = (line) => {
    let count = 0;
    let previous = "";
    let started = false;
    const walker = document.createTreeWalker(line, NodeFilter.SHOW_TEXT);
    const pending = [];
    while (walker.nextNode()) {
      const text = walker.currentNode;
      if (text.parentElement.closest(".katex, code") !== null) { if (text.parentElement.closest(".katex-html")) { started = true; previous = "x"; } continue; }
      for (const character of text.data) {
        if (character === " ") { if (started && previous !== " ") pending.push(1); }
        else { count += pending.length; pending.length = 0; started = true; }
        previous = character;
      }
    }
    return count;
  };

  // A report the builder has set is written with its pages, and nothing is poured again.
  // Another browser may advance a glyph or a formula by a fraction of a pixel more or
  // less than Firefox did, which over a line ended it up to a few pixels from where Firefox
  // ended it. Every line with word spaces carries the width Firefox gave its words, and is
  // brought back to it by its word spaces, which Firefox, where it was measured, leaves.
  if (document.documentElement.hasAttribute("data-frozen")) {
    const settle = () => document.querySelectorAll(".ln[data-width]").forEach((line) => {
      const spaces = Number(line.dataset.spaces);
      const span = extent(line);
      if (!(spaces > 0) || span === null) return;
      const off = Number(line.dataset.width) - (span.right - span.left);
      if (Math.abs(off) > 0.05) line.style.wordSpacing = `${(parseFloat(line.style.wordSpacing) || 0) + off / spaces}px`;
    });
    // Twice, since the first change of spacing is rounded by the browser again.
    document.fonts.ready.then(() => { settle(); settle(); });
    return;
  }
  const flow = document.getElementById("report-flow");
  const holder = document.querySelector("main.pages");
  const pristine = flow.cloneNode(true);
  flow.replaceChildren();
  const head = JSON.parse(pristine.dataset.runningHead);
  const isFloat = (node) => node.tagName === "FIGURE";

  function newPage(number) {
    const page = document.createElement("section");
    page.className = "page";
    if (number > 1) {
      const running = document.createElement("div");
      running.className = "running-head";
      const left = document.createElement("span");
      const right = document.createElement("span");
      if (number % 2 === 1) left.textContent = head.title; else right.textContent = head.author;
      running.append(left, right);
      page.append(running);
    }
    const body = document.createElement("div");
    body.className = "page-body";
    const top = document.createElement("div");
    top.className = "page-top";
    const columns = document.createElement("div");
    columns.className = "columns";
    for (let index = 0; index < 2; index += 1) {
      const column = document.createElement("div");
      column.className = "column";
      column.setAttribute("data-layout-guard", "");
      columns.append(column);
    }
    body.append(top, columns);
    page.append(body);
    holder.append(page);
    return page;
  }

  // A table shares out the width of the place it lands in, a column or the page.
  const fitTables = (block) => {
    const tables = block.tagName === "TABLE" ? [block] : Array.from(block.querySelectorAll?.("table") ?? []);
    tables.forEach((table) => window.htmlMcpFitColumns(table));
  };
  const bottomOf = (column) => column.getBoundingClientRect().bottom;
  const fits = (node, column) => node.getBoundingClientRect().bottom <= bottomOf(column) + 0.5;
  // A figure at a column's top fits it and, with the figures above it, fills no more than
  // 0.7 of it.
  const atTop = (figure, column) => {
    const box = column.getBoundingClientRect();
    return fits(figure, column) && figure.getBoundingClientRect().bottom - box.top <= box.height * 0.7;
  };

  // The lines of a paragraph inside a column, as one rectangle per line. A box joins the
  // line whose middle is within half a pitch of its own: joining boxes that overlapped
  // made a whole paragraph one line in a face whose letters stand taller than the pitch.
  // Line boxes meet halfway between the middles of neighbouring lines, and the first starts
  // and the last ends with the paragraph's text, so a line's top and foot are where its
  // line box runs, which is what has to fit in the column. They are measured, not counted
  // in pitches: a Hangul letter set in a fallback face can make a line taller than the
  // pitch.
  function lineBoxes(node) {
    const style = getComputedStyle(node);
    const box = node.getBoundingClientRect();
    const scale = node.offsetHeight > 0 ? box.height / node.offsetHeight : 1;
    const pitch = (parseFloat(style.lineHeight) || 16) * scale;
    const letter = (parseFloat(style.fontSize) || 12) * scale;
    const range = document.createRange();
    range.selectNodeContents(node);
    const lines = [];
    for (const rect of range.getClientRects()) {
      // A box much shorter than a letter is no line of text: KaTeX sets subscripts, rules
      // and accents in boxes of their own, and one below the text began a line of its own.
      if (rect.width === 0 || rect.height < letter * 0.6) continue;
      const middle = (rect.top + rect.bottom) / 2;
      const last = lines[lines.length - 1];
      if (last !== undefined && Math.abs(middle - last.middle) < pitch / 2) {
        last.left = Math.min(last.left, rect.left);
        last.right = Math.max(last.right, rect.right);
        continue;
      }
      lines.push({ left: rect.left, right: rect.right, middle });
    }
    const first = box.top + (parseFloat(style.paddingTop) + parseFloat(style.borderTopWidth)) * scale;
    const end = box.bottom - (parseFloat(style.paddingBottom) + parseFloat(style.borderBottomWidth)) * scale;
    lines.forEach((line, index) => {
      line.top = index === 0 ? first : (lines[index - 1].middle + line.middle) / 2;
      line.foot = index === lines.length - 1 ? end : (line.middle + lines[index + 1].middle) / 2;
    });
    return lines;
  }

  // The first letter of a paragraph whose middle sits on or below a given height, a line's
  // top: a Hangul letter's box can rise above its line box. Letters are
  // measured one by one with a range, which works wherever the page is: a point lookup
  // finds nothing below the window, and most of a document is below it.
  function firstLetterBelow(node, top) {
    const letters = [];
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const text = walker.currentNode;
      // KaTeX's MathML copy is not drawn: its letters have no place on a line, and taken as
      // above every line they sent the search past the line to cut.
      if (text.parentElement.closest(".katex-mathml") !== null) continue;
      for (let offset = 0; offset < text.length; offset += 1) letters.push([text, offset]);
    }
    const topOf = ([text, offset]) => {
      const range = document.createRange();
      range.setStart(text, offset);
      range.setEnd(text, offset + 1);
      const box = Array.from(range.getClientRects()).find((rect) => rect.width > 0 || rect.height > 0);
      return box === undefined ? -Infinity : (box.top + box.bottom) / 2;
    };
    let low = 0, high = letters.length;
    while (low < high) {
      const middle = (low + high) >> 1;
      if (topOf(letters[middle]) >= top) high = middle; else low = middle + 1;
    }
    if (low >= letters.length) return null;
    // A word the browser hyphenated at the foot is cut inside: the line before keeps a hyphen.
    const before = low > 0 ? letters[low - 1] : null;
    const midWord = before !== null && /[\p{L}\p{N}]/u.test(before[0].data[before[1]])
      && /[\p{L}\p{N}]/u.test(letters[low][0].data[letters[low][1]]);
    return [...letters[low], midWord];
  }

  // Cuts a paragraph after the last line that ends above the foot of its column. Returns
  // the rest, or null when fewer than two lines fit. One line left over goes on with the
  // line before it, so no column ends or opens with a paragraph's lone line.
  function splitParagraph(node, column) {
    const lines = lineBoxes(node);
    const foot = bottomOf(column);
    let keep = 0;
    while (keep < lines.length && lines[keep].foot <= foot + 0.5) keep += 1;
    if (keep < 2 || lines.length - keep < 1) return null;
    if (lines.length - keep === 1) keep -= 1;
    // A line's foot is measured from the middles of its letters, which sit a little higher
    // or lower as a line holds more Hangul or more Latin, so the cut paragraph is measured
    // again and cut a line earlier if its last line runs past the foot.
    const whole = Array.from(node.childNodes, (child) => child.cloneNode(true));
    for (; keep >= 2; keep -= 1) {
      const letter = firstLetterBelow(node, lines[keep].top);
      if (letter === null) return null;
      const cut = document.createRange();
      cut.setStart(letter[0], letter[1]);
      // Math is cut before, never inside.
      const math = letter[0].parentElement?.closest(".katex");
      if (math && node.contains(math)) cut.setStartBefore(math);
      cut.setEnd(node, node.childNodes.length);
      const rest = node.cloneNode(false);
      rest.removeAttribute("id");
      rest.classList.add("cont");
      rest.append(cut.extractContents());
      if (letter[2]) node.append("‐");
      node.classList.add("split");
      if (fits(node, column)) return rest;
      node.classList.remove("split");
      node.replaceChildren(...whole.map((child) => child.cloneNode(true)));
    }
    return null;
  }

  // Cuts a list before its first item that runs past the foot, keeping its numbering.
  function splitList(node, column) {
    const items = Array.from(node.children);
    const first = items.findIndex((item) => !fits(item, column));
    if (first <= 0) return null;
    const rest = node.cloneNode(false);
    rest.removeAttribute("id");
    if (node.tagName === "OL") rest.setAttribute("start", String((node.start || 1) + first));
    rest.append(...items.slice(first));
    return rest;
  }

  function pour() {
    holder.replaceChildren();
    const blocks = Array.from(pristine.cloneNode(true).children);
    let pageNumber = 1;
    let page = newPage(pageNumber);
    let columnIndex = 0;
    let column = page.querySelectorAll(".column")[0];
    const waitingColumn = [];
    const waitingWide = [];

    const nextColumn = () => {
      columnIndex += 1;
      if (columnIndex === 2) {
        pageNumber += 1;
        page = newPage(pageNumber);
        columnIndex = 0;
        // Wide figures that waited stack at the top while they take no more than 0.7 of the
        // page, LaTeX's \dbltopfraction, and the rest wait for the page after. One alone
        // always goes. Stacked past the page, they pushed the columns out of it.
        const top = page.querySelector(".page-top");
        const limit = page.querySelector(".page-body").getBoundingClientRect().height * 0.7;
        while (waitingWide.length) {
          const figure = waitingWide[0];
          top.append(figure);
          fitTables(figure);
          if (top.getBoundingClientRect().height > limit && top.children.length > 1) { figure.remove(); break; }
          waitingWide.shift();
        }
      }
      column = page.querySelectorAll(".column")[columnIndex];
      // Figures that waited go first, in their order, while they fit and fill no more than
      // 0.7 of the column, LaTeX's \topfraction. One alone always goes.
      while (waitingColumn.length) {
        const figure = waitingColumn[0];
        column.append(figure);
        fitTables(figure);
        if (!atTop(figure, column) && column.children.length > 1) { figure.remove(); break; }
        waitingColumn.shift();
      }
    };

    let guard = 0;
    while (blocks.length && guard < 5000) {
      guard += 1;
      const block = blocks.shift();
      if (block.classList.contains("title-block")) {
        page.querySelector(".page-top").append(block);
        continue;
      }
      if (isFloat(block) && block.classList.contains("wide")) {
        waitingWide.push(block);
        continue;
      }
      // A figure or table stands at the top of a column, as LaTeX's [t] places it: at the
      // top of this one while it holds only figures, else at the top of the next, after
      // those already waiting, so the numbers keep their order and none comes before the
      // place it is written.
      if (isFloat(block)) {
        if (waitingColumn.length || Array.from(column.children).some((node) => !isFloat(node))) {
          waitingColumn.push(block);
          continue;
        }
        column.append(block);
        fitTables(block);
        if (atTop(block, column)) continue;
        if (column.children.length === 1) { nextColumn(); continue; }
        block.remove();
        waitingColumn.push(block);
        continue;
      }
      column.append(block);
      fitTables(block);
      if (fits(block, column)) {
        // A head stays with the two lines of text after it. A figure between them floats
        // and is not what the head is kept with.
        const following = blocks.find((next) => !isFloat(next));
        if (/^H[23]$/.test(block.tagName) && following !== undefined) {
          // The head stays when what follows can begin under it as the pour would set it: a
          // copy is placed and cut the same way, so a paragraph whose cut would leave a line
          // alone, or a list whose first item does not fit, sends the head on.
          const probe = following.cloneNode(true);
          column.append(probe);
          let room = fits(probe, column);
          if (!room && /^(P|LI)$/.test(probe.tagName)) room = splitParagraph(probe, column) !== null;
          else if (!room && /^(UL|OL)$/.test(probe.tagName)) room = splitList(probe, column) !== null;
          probe.remove();
          if (!room && column.children.length > 1) {
            block.remove();
            // A section head right above a subsection head goes on with it.
            const above = column.lastElementChild;
            const heads = above !== null && /^H[23]$/.test(above.tagName) && column.children.length > 1 ? [above, block] : [block];
            if (heads.length === 2) above.remove();
            nextColumn();
            blocks.unshift(...heads);
          }
        }
        continue;
      }
      let rest = null;
      if (block.tagName === "P" || block.tagName === "LI") rest = splitParagraph(block, column);
      else if (block.tagName === "UL" || block.tagName === "OL") rest = splitList(block, column);
      if (rest !== null) {
        nextColumn();
        blocks.unshift(rest);
        continue;
      }
      if (column.children.length === 1) {
        // Taller than a column: it stays, and the layout check reports it.
        nextColumn();
        continue;
      }
      block.remove();
      nextColumn();
      blocks.unshift(block);
    }
    // Figures still waiting go on pages of their own after the text.
    while (waitingColumn.length || waitingWide.length) {
      if (waitingWide.length) { columnIndex = 1; nextColumn(); continue; }
      nextColumn();
    }
    for (const caption of holder.querySelectorAll("figcaption")) {
      if (lineBoxes(caption).length <= 1) caption.classList.add("single");
    }
    // The document's other scripts set up what they placed, such as a figure's lifted HTML,
    // again on the poured copy.
    for (const setup of window.htmlMcpPageSetup ?? []) setup(holder);
    const pages = Array.from(holder.children);
    for (const page of pages.slice(0, -1)) page.querySelectorAll(".column").forEach(spread);
    balance(pages[pages.length - 1]);
  }


  // The last page's two columns are made even, as a proceedings class ends a paper: its
  // blocks are poured again into both columns at the least height that holds them, found
  // by halving, a figure moving whole. A head is not left at the foot of the first. A page
  // whose blocks no lower height holds keeps its pour.
  function balance(page) {
    const columns = Array.from(page.querySelectorAll(".column"));
    const frame = page.querySelector(".columns");
    const original = columns.map((column) => Array.from(column.children));
    const items = original.flat().map((node) => node.cloneNode(true));
    if (items.length === 0) return;
    const full = frame.getBoundingClientRect().height;
    const pourAt = (height) => {
      frame.style.flex = "none";
      frame.style.height = `${height}px`;
      columns.forEach((column) => column.replaceChildren());
      const queue = items.map((node) => node.cloneNode(true));
      const deferred = [];
      let index = 0;
      const second = () => { index = 1; columns[1].append(...deferred); };
      while (queue.length) {
        const column = columns[index];
        const block = queue.shift();
        // A figure keeps to a column's top: after text it opens the second column.
        if (isFloat(block) && Array.from(column.children).some((node) => !isFloat(node))) {
          if (index === 1) return false;
          deferred.push(block);
          continue;
        }
        column.append(block);
        if (fits(block, column)) continue;
        if (index === 1) return false;
        let rest = null;
        if (block.tagName === "P" || block.tagName === "LI") rest = splitParagraph(block, column);
        else if (block.tagName === "UL" || block.tagName === "OL") rest = splitList(block, column);
        if (rest === null) {
          if (column.children.length === 1) return false;
          block.remove();
          rest = block;
        }
        queue.unshift(rest);
        if (/^H[23]$/.test(column.lastElementChild?.tagName ?? "")) queue.unshift(column.lastElementChild);
        second();
      }
      if (index === 0 && deferred.length) second();
      return Array.from(columns[1].children).every((node) => fits(node, columns[1]));
    };
    let low = 0, high = full;
    while (high - low > 1) {
      const middle = (low + high) / 2;
      if (pourAt(middle)) high = middle; else low = middle;
    }
    if (high < full - 1 && pourAt(high)) return;
    frame.style.flex = "";
    frame.style.height = "";
    columns.forEach((column, at) => column.replaceChildren(...original[at]));
  }

  // Every column but those of the last page ends on its foot, as LaTeX's \flushbottom sets
  // a two-column paper: left where the text stopped, the columns of a page ended at
  // different heights. The height left over goes first, evenly, to the space between the
  // paragraphs and list items of a section, up to 4pt each, then to the space above heads
  // and around figures, up to 12pt each. What is still left is written on the column as data-underfull, in
  // points, for the layout check to report.
  const PT = 4 / 3;
  function spread(column) {
    const last = column.lastElementChild;
    if (last === null) return;
    let slack = bottomOf(column) - last.getBoundingClientRect().bottom;
    if (slack <= 0.5) return;
    const blocks = Array.from(column.children);
    const prose = (node) => /^(P|UL|OL|DIV)$/.test(node.tagName);
    const paragraphs = [];
    // Under a title block or wide figures, the space down to the columns stretches too.
    const others = column.closest(".page-body").querySelector(".page-top").children.length > 0 ? [blocks[0]] : [];
    blocks.forEach((node, index) => {
      if (index > 0) (prose(node) && prose(blocks[index - 1]) ? paragraphs : others).push(node);
      if (/^(UL|OL)$/.test(node.tagName)) paragraphs.push(...Array.from(node.children).slice(1));
    });
    // The space between two blocks is the larger of their margins, which merge, so it grows
    // by an amount when the later block's top margin becomes that space plus the amount.
    // Padding would grow it too, but on a wrapper it also stopped its first child's margin
    // from merging with the wrapper's, and that child's margin was added on top. A column's
    // first block has no margin to grow and takes padding.
    const gap = new Map([...paragraphs, ...others].map((node) => {
      const previous = node.previousElementSibling;
      const own = parseFloat(getComputedStyle(node).marginTop) || 0;
      return [node, previous === null ? own : Math.max(own, parseFloat(getComputedStyle(previous).marginBottom) || 0)];
    }));
    const grow = (node, amount) => {
      if (node === blocks[0]) node.style.paddingTop = `${amount}px`;
      else node.style.marginTop = `${gap.get(node) + amount}px`;
    };
    const share = (left) => {
      const each = [Math.min(4 * PT, left / Math.max(paragraphs.length, 1))];
      left -= paragraphs.length ? each[0] * paragraphs.length : 0;
      each.push(Math.min(12 * PT, Math.max(left, 0) / Math.max(others.length, 1)));
      paragraphs.forEach((node) => grow(node, each[0]));
      others.forEach((node) => grow(node, each[1]));
    };
    share(slack);
    const over = last.getBoundingClientRect().bottom - bottomOf(column);
    if (over > 0.5) share(slack - over);
    const left = bottomOf(column) - last.getBoundingClientRect().bottom;
    if (left > 0.5) column.dataset.underfull = (left / PT).toFixed(1);
  }

  // The builder sets every line the pour made as a block of its own and writes the pages
  // down, so a reader's browser draws the lines Firefox broke and the layout check
  // measured, whatever its own line breaking, justification or hyphenation would do. A
  // line keeps the block's alignment, justified ones stretched to the column, and a word
  // Firefox hyphenated at a line's end gets its hyphen drawn after the line, outside the
  // text a comment quotes. A table keeps the column widths Firefox gave it.
  function freezeLines(block) {
    const lines = lineBoxes(block);
    if (lines.length === 0) return;
    const atoms = [];
    const visit = (node) => {
      for (const child of node.childNodes) {
        if (child.nodeType === Node.TEXT_NODE) {
          for (let offset = 0; offset < child.length; offset += 1) {
            if (child.data[offset].trim() !== "") atoms.push({ node: child, offset });
          }
        } else if (child.nodeType === Node.ELEMENT_NODE) {
          // KaTeX may break inline math between the boxes it sets each part in, so those
          // boxes are the parts a line holds.
          if (child.matches(".katex")) child.querySelectorAll(".katex-html > .base").forEach((base) => atoms.push({ node: base, offset: null }));
          else if (child.matches("img, svg, br")) atoms.push({ node: child, offset: null });
          else if (!child.matches(".katex-mathml, .eqno")) visit(child);
        }
      }
    };
    visit(block);
    const lineOf = (atom) => {
      let rect;
      if (atom.offset === null) rect = atom.node.getBoundingClientRect();
      else {
        const range = document.createRange();
        range.setStart(atom.node, atom.offset);
        range.setEnd(atom.node, atom.offset + 1);
        rect = Array.from(range.getClientRects()).find((box) => box.width > 0) ?? range.getBoundingClientRect();
      }
      const middle = (rect.top + rect.bottom) / 2;
      const at = lines.findIndex((line) => middle >= line.top && middle < line.foot);
      return at === -1 ? (middle < lines[0].top ? 0 : lines.length - 1) : at;
    };
    const starts = [];
    let current = -1;
    for (const atom of atoms) {
      const at = lineOf(atom);
      if (at > current) { starts.push(atom); current = at; }
    }
    const style = getComputedStyle(block);
    const justified = style.textAlign === "justify";
    const lastJustified = justified && style.textAlignLast === "justify";
    const before = (atom, range, edge) => {
      if (atom.offset === null) range[edge === "start" ? "setStartBefore" : "setEndBefore"](atom.node);
      else range[edge === "start" ? "setStart" : "setEnd"](atom.node, atom.offset);
    };
    // A word cut by the browser's hyphenation: the letters on either side of the break
    // touch, with nothing between them in the text.
    const hyphenated = starts.map((start, index) => {
      if (index === starts.length - 1) return false;
      const next = starts[index + 1];
      const previous = atoms[atoms.indexOf(next) - 1];
      if (previous.offset === null || next.offset === null) return false;
      const between = document.createRange();
      between.setStart(previous.node, previous.offset + 1);
      between.setEnd(next.node, next.offset);
      return between.toString() === "" && /\p{L}/u.test(previous.node.data[previous.offset]) && /\p{L}/u.test(next.node.data[next.offset]);
    });
    let after = null;
    for (let index = starts.length - 1; index >= 0; index -= 1) {
      const range = document.createRange();
      if (index === 0) range.setStart(block, 0); else before(starts[index], range, "start");
      if (after === null) range.setEnd(block, block.childNodes.length); else range.setEndBefore(after);
      const line = document.createElement("span");
      line.className = "ln";
      if (index < starts.length - 1 ? justified : lastJustified) line.classList.add("j");
      line.append(range.extractContents());
      if (hyphenated[index]) line.classList.add("h");
      if (after === null) block.append(line); else block.insertBefore(line, after);
      after = line;
    }
    // A break opportunity has done its work once the lines are set, and Chrome took one
    // even inside a line that does not wrap.
    block.querySelectorAll("wbr").forEach((opportunity) => opportunity.remove());
  }

  // A justified line keeps its spacing as Firefox would spread it, written as letter and
  // word spacing, which every browser draws alike, and is no longer justified by the
  // browser: Chrome spread a Korean line between letters and WebKit between words only,
  // so the same line ended at the same place with its words in other places. The slack
  // goes to every space and, in a Korean document, every Hangul letter alike, as Firefox's
  // inter-character justification spreads it, a letter taking no more than --letter-cap
  // and the words the rest. A Latin word, a number, math and code are not spread inside.
  const HANGUL = /[\uac00-\ud7a3]/;
  function setSpacing(line) {
    line.classList.remove("j");
    line.classList.add("set");
    const style = getComputedStyle(line);
    const right = line.getBoundingClientRect().right - parseFloat(style.paddingRight);
    const contentRight = () => extent(line).right;
    const slack = right - contentRight();
    if (!(slack > 0.05)) return;
    const korean = document.documentElement.lang === "ko";
    const cap = parseFloat(style.fontSize) * parseFloat(style.getPropertyValue("--letter-cap"));
    const letters = [];
    let spaces = 0;
    const text = line.textContent;
    const inner = text.trim();
    const walker = document.createTreeWalker(line, NodeFilter.SHOW_TEXT);
    let seen = 0;
    const start = text.length - text.trimStart().length;
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const skip = node.parentElement.closest(".katex, code") !== null;
      const latin = node.parentElement.closest('[lang="en"]') !== null;
      for (let offset = 0; offset < node.length; offset += 1, seen += 1) {
        const at = seen - start;
        if (skip || at < 0 || at >= inner.length) continue;
        if (node.data[offset] === " " && inner[at - 1] !== " ") spaces += 1;
        else if (korean && !latin && HANGUL.test(node.data[offset]) && at < inner.length - 1) letters.push({ node, offset });
      }
    }
    spaces = spacesOf(line);
    const each = letters.length + spaces > 0 ? slack / (letters.length + spaces) : 0;
    const letter = spaces > 0 ? Math.min(cap, each) : (letters.length ? slack / letters.length : 0);
    const word = spaces > 0 ? (slack - letter * letters.length) / spaces : 0;
    // Each letter's span, from the last so the offsets before it hold.
    for (const { node, offset } of letters.reverse()) {
      const range = document.createRange();
      range.setStart(node, offset);
      range.setEnd(node, offset + 1);
      const span = document.createElement("span");
      span.className = "ls";
      range.surroundContents(span);
    }
    line.style.setProperty("--ls", `${letter}px`);
    line.style.wordSpacing = `${word}px`;
    // What the browser rounded is given back to the word spaces.
    const off = right - contentRight();
    if (spaces > 0 && Math.abs(off) > 0.05) line.style.wordSpacing = `${word + off / spaces}px`;
  }

  function freezeTable(table) {
    const widths = [];
    for (const row of table.rows) {
      let column = 0;
      for (const cell of row.cells) {
        if (cell.colSpan === 1 && widths[column] === undefined) widths[column] = cell.getBoundingClientRect().width;
        column += cell.colSpan;
      }
    }
    const group = document.createElement("colgroup");
    for (const width of widths) {
      const col = document.createElement("col");
      col.style.width = `${width}px`;
      group.append(col);
    }
    table.style.width = `${table.getBoundingClientRect().width}px`;
    table.style.tableLayout = "fixed";
    table.prepend(group);
  }

  window.htmlMcpFreeze = () => {
    holder.querySelectorAll("table").forEach(freezeTable);
    const blocks = Array.from(holder.querySelectorAll("*")).filter((element) => {
      if (element.closest("svg, pre, .katex, .katex-display, .svg-html-layer, .ln") !== null) return false;
      // A displayed equation keeps its own layout, which a line would break up.
      if (element.querySelector(".katex-display") !== null) return false;
      if (!/^(block|list-item|table-cell)$/.test(getComputedStyle(element).display)) return false;
      const direct = Array.from(element.childNodes).some((node) =>
        (node.nodeType === Node.TEXT_NODE && node.data.trim() !== "") || (node.nodeType === Node.ELEMENT_NODE && node.matches(".katex, span, b, i, em, strong, code, a, mark, sub, sup, cite, wbr")));
      const blockChild = Array.from(element.children).some((child) =>
        !child.matches(".eqno") && /^(block|list-item|table|flex|grid)$/.test(getComputedStyle(child).display));
      return direct && !blockChild;
    });
    blocks.forEach(freezeLines);
    holder.querySelectorAll(".ln.j").forEach(setSpacing);
    holder.querySelectorAll(".ln").forEach((line) => {
      const span = extent(line);
      const spaces = spacesOf(line);
      if (span === null || spaces === 0) return;
      line.dataset.width = (span.right - span.left).toFixed(3);
      line.dataset.spaces = String(spaces);
    });
    document.documentElement.setAttribute("data-frozen", "");
  };

  pour();
  document.fonts.ready.then(() => {
    pour();
    document.documentElement.setAttribute("data-poured", "");
  });
})();
</script>"""


def build(content_path: Path, output_path: Path, skin_dir: Path) -> None:
    content = parse_template_content(content_path)
    lang = content.lang
    numbers: dict[str, int] = {}
    figures = tables = equations = 0
    blocks: list[str] = []

    meta = "".join(f'<p class="affiliation">{line}</p>' for line in content.metadata if line)
    subtitle = f'<p class="subtitle">{content.subtitle}</p>' if content.subtitle else ""
    blocks.append(f'<header class="title-block"><h1>{content.title}</h1>{subtitle}'
                  f'<p class="authors">{content.author}</p>{meta}</header>')

    section_number = 0
    for section in content.sections:
        if section.layout != "body":
            raise ValueError(f'a report has no {section.layout} page; data-layout belongs to a deck')
        body_html, _ = prepare_body(section.body_html, content.references, numbers, content.lang)
        parser = ContentParser()
        parser.feed(body_html)
        parser.close()
        if "data-abstract" in section.attributes:
            heading = f'<h2 class="abstract">{section.title or "Abstract"}</h2>'
        else:
            section_number += 1
            heading = f'<h2><span class="secno">{section_number}</span>{section.title}</h2>'
        blocks.append(heading)
        subsection = 0
        for child in parser.root.children:
            if not isinstance(child, Element):
                if child.strip() and not child.lstrip().startswith("<!--"):
                    raise ValueError(f'section "{section.title}": text outside a block element')
                continue
            if child.tag == "h3" and "data-abstract" not in section.attributes:
                subsection += 1
                child.children.insert(0, Element("span", {"class": "secno"}, [f"{section_number}.{subsection}"]))
            # A displayed equation is numbered where it stands, also inside the wrapper that
            # keeps it with its definitions.
            for node in [child, *descendants(child)]:
                if node.tag == "p" and "eq" in node.attributes.get("class", "").split():
                    equations += 1
                    node.children.append(Element("span", {"class": "eqno"}, [f"({equations})"]))
            if child.tag == "figure":
                captions = [node for node in child.children if isinstance(node, Element) and node.tag == "figcaption"]
                if len(captions) != 1:
                    raise ValueError(f'section "{section.title}": a figure takes one figcaption')
                caption = captions[0]
                child.children.remove(caption)
                is_table = any(isinstance(node, Element) and (node.tag == "table" or node.tag == "div" and "table-fit" in node.attributes.get("class", ""))
                               for node in child.children)
                if is_table:
                    tables += 1
                    label = f"Table {tables}:"
                    child.attributes["class"] = " ".join(["table", *child.attributes.get("class", "").split()])
                    child.children.insert(0, caption)
                else:
                    figures += 1
                    label = f"Figure {figures}:"
                    child.children.append(caption)
                caption.children.insert(0, Element("span", {"class": "caption-label"}, [label + " "]))
            blocks.append(child.to_html())

    if numbers:
        entries = "".join(
            f'<li id="{key}"><span class="bib-no">[{number}]</span>{content.references[key]}</li>'
            for key, number in sorted(numbers.items(), key=lambda item: item[1]))
        blocks.append(f'<h2>{"참고문헌" if lang == "ko" else "References"}</h2>')
        blocks.append(f'<ol class="bib">{entries}</ol>')

    flow_html = "\n".join(blocks)
    # The skin is read last, so it restates what it changes of the frame.
    css = (COMPONENTS.read_text(encoding="utf-8") + "\n" + SKELETON.read_text(encoding="utf-8") + "\n"
           + inline_woff2((skin_dir / "skin.css").read_text(encoding="utf-8"), skin_dir / "fonts"))
    assets = document_assets(flow_html, lang)
    running = html.escape(f'{{"title": {_json(content.title)}, "author": {_json(content.author)}}}', quote=True)
    poured = output_path.with_name(f".{output_path.name}.pour.html")
    poured.write_text(f'''<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{content.title}</title>
  <style>
{css}
  </style>{assets[0]}
</head>
<body>
  <main class="pages"></main>
  <div id="report-flow" data-running-head="{running}">
{flow_html}
  </div>{assets[1]}
{PAGINATE_SCRIPT}
</body>
</html>
''', encoding="utf-8")
    try:
        output_path.write_text(set_pages(poured), encoding="utf-8")
    finally:
        poured.unlink()
    print(f"{output_path}: {len(content.sections)} sections, {figures} figures, {tables} tables")


def set_pages(document: Path) -> str:
    """The document with its pages set: Firefox pours the text into the columns once, and
    what it made, every line in its place, is written down (KITS 10.13). Left to pour in
    the reader's browser, Chrome or Safari broke and spread the lines its own way, and the
    pages the reader saw were not the pages the layout check had measured."""
    from ..firefox import firefox, wait_loaded

    with firefox() as client:
        client.navigate(document.resolve().as_uri())
        wait_loaded(client, 'document.documentElement.hasAttribute("data-poured")', tries=150)
        # In the page's own scope, where its script left the setting function.
        return "<!doctype html>\n" + client.execute_script(
            "window.htmlMcpFreeze(); return document.documentElement.outerHTML;", sandbox=None) + "\n"


def _json(text: str) -> str:
    import json
    return json.dumps(html.unescape(re.sub(r"<[^>]+>", "", text)), ensure_ascii=False)

