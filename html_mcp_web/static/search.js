// Find in the artifact. The words typed are looked for in the pages, and in the speaker
// scripts while they are shown, ignoring case and runs of white space. Each match is marked
// over its letters the way a comment's quote is, in a layer of the page's own, so the
// document's text is left as it is: comment anchors and the layout check read it unchanged.
// The search opens from the toolbar or with Cmd+F or Ctrl+F while the deck or the previews
// have the focus. Enter goes to the next match, Shift+Enter to the one before, Escape closes.
export function createSearch(state, dependencies) {
  const {
    $,
    artifactPages,
    frameDocument,
    frameWindow,
    movePresentationPage,
    pageFrameFor,
    selectionRects,
  } = dependencies;

  // Text the reader does not see as the page's words: KaTeX keeps a MathML copy of each
  // formula for screen readers, and the viewer's own layers carry badge numbers.
  const SKIPPED = "script, style, noscript, template, title, .katex-mathml, .html-mcp-highlight-layer, .html-mcp-search-layer";
  // Words of two blocks, two list items or two labels of a figure, are not read as one run.
  const BLOCK = "p, li, dt, dd, td, th, caption, h1, h2, h3, h4, h5, h6, pre, blockquote, figcaption, div, section, text";
  // A page with thousands of matches is not helped by marking every one.
  const LIMIT = 2000;

  let matches = [];
  let current = -1;
  let layers = new Set();
  let typing = null;

  const bar = () => $("#search-bar");
  const input = () => $("#search-input");
  const isOpen = () => !bar().classList.contains("hidden");

  const fold = (text) => Array.from(text, (char) => {
    const lower = char.toLowerCase();
    return lower.length === char.length ? lower : char;
  }).join("");

  // The searched text as one string, a character of it per place in the document: white
  // space folded to one space, and a break that matches nothing between blocks.
  function readText(doc) {
    const scriptsShown = !doc.documentElement.hasAttribute("data-html-mcp-scripts-hidden");
    const roots = doc.querySelectorAll(scriptsShown
      ? "body > main.pages > section.page, body > main.pages > .script-block"
      : "body > main.pages > section.page");
    const chars = [];
    const places = [];
    for (const root of roots) {
      let block = null;
      const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode: (node) => (node.parentElement?.closest(SKIPPED) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
      });
      chars.push("\u0000");
      places.push(null);
      let node;
      while ((node = walker.nextNode()) !== null) {
        const owner = node.parentElement.closest(BLOCK);
        if (owner !== block) {
          block = owner;
          chars.push("\u0000");
          places.push(null);
        }
        const value = node.nodeValue;
        for (let offset = 0; offset < value.length; offset += 1) {
          const char = value[offset];
          if (/\s/.test(char)) {
            const last = chars[chars.length - 1];
            if (last === " " || last === "\u0000") continue;
            chars.push(" ");
          } else {
            chars.push(fold(char));
          }
          places.push([node, offset]);
        }
      }
    }
    return { text: chars.join(""), places };
  }

  function findAll(doc, query) {
    const wanted = fold(query.trim().replace(/\s+/g, " "));
    if (wanted === "") return [];
    const { text, places } = readText(doc);
    const found = [];
    for (let at = text.indexOf(wanted); at !== -1 && found.length < LIMIT; at = text.indexOf(wanted, at + 1)) {
      const [startNode, startOffset] = places[at];
      const [endNode, endOffset] = places[at + wanted.length - 1];
      const range = doc.createRange();
      range.setStart(startNode, startOffset);
      range.setEnd(endNode, endOffset + 1);
      found.push({ range });
    }
    return found;
  }

  function searchLayer(page) {
    const doc = page.ownerDocument;
    if (doc.querySelector("#html-mcp-search-style") === null) {
      const style = doc.createElement("style");
      style.id = "html-mcp-search-style";
      style.textContent = `
        .html-mcp-search-layer { position: absolute; left: 0; top: 0; right: 0; bottom: 0; overflow: hidden; z-index: 2147483645; pointer-events: none; }
        .html-mcp-search-mark { position: absolute; border-radius: 2px; background: rgba(255, 214, 10, .45); }
        .html-mcp-search-mark.current { background: rgba(255, 140, 0, .55); box-shadow: 0 0 0 1px rgba(196, 98, 0, .85); }
      `;
      doc.head.appendChild(style);
    }
    let layer = page.querySelector(":scope > .html-mcp-search-layer");
    if (layer === null) {
      layer = doc.createElement("div");
      layer.className = "html-mcp-search-layer";
      page.appendChild(layer);
      layers.add(layer);
    }
    // A scrolling speaker-script block clips an inset layer to its visible box.
    if (page.scrollHeight > page.clientHeight) {
      layer.style.bottom = "auto";
      layer.style.height = `${page.scrollHeight}px`;
    }
    return layer;
  }

  function clearMarks() {
    for (const layer of layers) layer.remove();
    layers = new Set();
  }

  // Each match is drawn over its letters, in the coordinates of the page it is on, so the
  // marks move and scale with the page. A match with nothing drawn is not counted.
  function draw(found) {
    const doc = frameDocument();
    const drawn = [];
    for (const match of found) {
      const frame = pageFrameFor(match.range.startContainer);
      if (frame === null) continue;
      const rects = selectionRects(match.range);
      if (rects.length === 0) continue;
      const layer = searchLayer(frame.page);
      match.page = frame.page;
      match.top = rects[0].top;
      match.marks = rects.map((rect) => {
        const mark = doc.createElement("div");
        mark.className = "html-mcp-search-mark";
        Object.assign(mark.style, {
          left: `${(rect.left - frame.rect.left) / frame.ratio + frame.scrollLeft}px`,
          top: `${(rect.top - frame.rect.top) / frame.ratio + frame.scrollTop}px`,
          width: `${rect.width / frame.ratio}px`,
          height: `${rect.height / frame.ratio}px`,
        });
        layer.appendChild(mark);
        return mark;
      });
      drawn.push(match);
    }
    return drawn;
  }

  function showCount() {
    const query = input().value.trim();
    $("#search-count").textContent = query === "" ? "" : `${matches.length === 0 ? 0 : current + 1}/${matches.length}`;
    $("#search-prev-btn").disabled = matches.length === 0;
    $("#search-next-btn").disabled = matches.length === 0;
  }

  // The match is marked as the current one and brought into view: in the slide show its
  // page is shown, and otherwise the deck scrolls only when the match is out of sight.
  function select(index, reveal) {
    if (matches.length === 0) {
      current = -1;
      showCount();
      return;
    }
    current = (index + matches.length) % matches.length;
    matches.forEach((match, at) => match.marks.forEach((mark) => mark.classList.toggle("current", at === current)));
    showCount();
    if (!reveal) return;
    const match = matches[current];
    const number = artifactPages().indexOf(match.page) + 1;
    if (state.slideShow && number > 0 && number !== state.currentPage) movePresentationPage(number - state.currentPage);
    const win = frameWindow();
    const box = match.marks[0].getBoundingClientRect();
    if (box.top < 0 || box.bottom > win.innerHeight || box.left < 0 || box.right > win.innerWidth) {
      match.marks[0].scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" });
    }
  }

  // A new query starts from the place being read: the first match at or below the top of
  // the window, rather than the deck's first page.
  function run() {
    typing = null;
    clearMarks();
    const doc = frameDocument();
    matches = doc === null || doc.body === null ? [] : draw(findAll(doc, input().value));
    const ahead = matches.findIndex((match) => match.top >= 0);
    select(ahead === -1 ? 0 : ahead, true);
  }

  // After the document changes under an open search, its matches are found again and the
  // same one stays current where it can, without moving the reader.
  function refresh() {
    if (!isOpen()) return;
    const kept = current;
    clearMarks();
    const doc = frameDocument();
    matches = doc === null || doc.body === null ? [] : draw(findAll(doc, input().value));
    select(Math.min(Math.max(kept, 0), matches.length - 1), false);
  }

  function open() {
    bar().classList.remove("hidden");
    $("#search-btn").classList.add("active");
    $("#search-btn").setAttribute("aria-expanded", "true");
    input().focus();
    input().select();
    if (input().value.trim() !== "") run();
  }

  function close() {
    if (typing !== null) clearTimeout(typing);
    typing = null;
    bar().classList.add("hidden");
    $("#search-btn").classList.remove("active");
    $("#search-btn").setAttribute("aria-expanded", "false");
    clearMarks();
    matches = [];
    current = -1;
    showCount();
    frameWindow()?.focus();
  }

  // Cmd+F or Ctrl+F in the deck or the previews opens this search rather than the browser's.
  function handleKeydown(event) {
    if (!(event.metaKey || event.ctrlKey) || event.altKey || event.shiftKey || event.key.toLowerCase() !== "f") return;
    event.preventDefault();
    open();
  }

  function attachControls() {
    $("#search-btn").addEventListener("click", () => (isOpen() ? close() : open()));
    input().addEventListener("input", () => {
      if (typing !== null) clearTimeout(typing);
      typing = setTimeout(run, 150);
    });
    input().addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        if (typing !== null) run();
        else select(current + (event.shiftKey ? -1 : 1), true);
      } else if (event.key === "Escape") {
        event.preventDefault();
        close();
      } else if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "f") {
        event.preventDefault();
        input().select();
      }
    });
    $("#search-prev-btn").addEventListener("click", () => select(current - 1, true));
    $("#search-next-btn").addEventListener("click", () => select(current + 1, true));
    $("#search-close-btn").addEventListener("click", close);
  }

  return { attachControls, handleKeydown, refresh };
}
