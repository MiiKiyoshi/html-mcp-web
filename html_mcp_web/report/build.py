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
# and a figure or table that does not fit waits for the head of the next column while the
# text goes on past it. A figure marked wide waits for the top of the next page, across
# both columns, as many as fill no more than 0.7 of it. The fonts change the lines, so the
# flow is poured again once they arrive.
PAGINATE_SCRIPT = r"""<script>
(() => {
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

  // The lines of a paragraph inside a column, as one rectangle per line.
  function lineBoxes(node) {
    const range = document.createRange();
    range.selectNodeContents(node);
    const lines = [];
    for (const box of range.getClientRects()) {
      if (box.width === 0) continue;
      const last = lines[lines.length - 1];
      if (last !== undefined && box.top < last.bottom - 1) {
        // A line's top is its highest box: a Latin word's box starts lower than the Hangul
        // around it, and a line that began with one was cut below its own Hangul letters.
        last.top = Math.min(last.top, box.top);
        last.bottom = Math.max(last.bottom, box.bottom);
        last.right = Math.max(last.right, box.right);
        continue;
      }
      lines.push({ top: box.top, bottom: box.bottom, right: box.right, left: box.left });
    }
    return lines;
  }

  // The first letter of a paragraph that sits on or below a given height. Letters are
  // measured one by one with a range, which works wherever the page is: a point lookup
  // finds nothing below the window, and most of a document is below it.
  function firstLetterBelow(node, top) {
    const letters = [];
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const text = walker.currentNode;
      for (let offset = 0; offset < text.length; offset += 1) letters.push([text, offset]);
    }
    const topOf = ([text, offset]) => {
      const range = document.createRange();
      range.setStart(text, offset);
      range.setEnd(text, offset + 1);
      const box = Array.from(range.getClientRects()).find((rect) => rect.width > 0 || rect.height > 0);
      return box === undefined ? -Infinity : box.top;
    };
    let low = 0, high = letters.length;
    while (low < high) {
      const middle = (low + high) >> 1;
      if (topOf(letters[middle]) >= top - 1) high = middle; else low = middle + 1;
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
    while (keep < lines.length && lines[keep].bottom <= foot + 0.5) keep += 1;
    if (keep < 2 || lines.length - keep < 1) return null;
    if (lines.length - keep === 1) keep -= 1;
    if (keep < 2) return null;
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
    return rest;
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
      // Figures that waited go first, as many as the column holds.
      while (waitingColumn.length) {
        const figure = waitingColumn[0];
        column.append(figure);
        fitTables(figure);
        if (!fits(figure, column) && column.children.length > 1) { figure.remove(); break; }
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
      if (isFloat(block) && waitingColumn.length) {
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
          const probe = following.cloneNode(true);
          column.append(probe);
          const lines = probe.tagName === "P" ? lineBoxes(probe) : [];
          const room = lines.length >= 2 ? lines[1].bottom : probe.getBoundingClientRect().bottom;
          probe.remove();
          if (room > bottomOf(column) + 0.5 && column.children.length > 1) {
            block.remove();
            nextColumn();
            blocks.unshift(block);
          }
        }
        continue;
      }
      if (isFloat(block)) {
        block.remove();
        if (column.children.length === 0) { column.append(block); nextColumn(); continue; }
        waitingColumn.push(block);
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
  }

  pour();
  document.fonts.ready.then(pour);
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
    assets = document_assets(flow_html)
    running = html.escape(f'{{"title": {_json(content.title)}, "author": {_json(content.author)}}}', quote=True)
    output_path.write_text(f'''<!doctype html>
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
    print(f"{output_path}: {len(content.sections)} sections, {figures} figures, {tables} tables")


def _json(text: str) -> str:
    import json
    return json.dumps(html.unescape(re.sub(r"<[^>]+>", "", text)), ensure_ascii=False)

