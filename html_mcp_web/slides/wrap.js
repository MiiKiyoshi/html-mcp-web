// A long label in an inline svg is written as one sentence and broken into lines here,
// in the deck itself, with the font the skin renders it in: the content file holds
//
//   <text x=".." y=".." data-wrap="196" data-align="justify" data-line-height="1.35"
//         data-max-lines="4">one sentence</text>
//
// and the deck shows tspans, one per line, x set on each and dy stepping down.
//
// The lines are chosen by the Knuth-Plass algorithm, the one TeX uses: it weighs every
// way of breaking the whole sentence at once, including breaking a word at a hyphenation
// point, and takes the set of lines with the least total badness. A greedy line that
// takes words while they fit reads one line at a time and cannot see that giving a word
// back would save the two lines after it. In a column this narrow that shows: a line
// with few words on it has to open its spaces to three or four times their natural
// width, and hyphenation is what closes them.
//
// data-align: justify widens the spaces of every line but the last to the full width;
// balance holds the last line to the width as well, which is TeX's \parfillskip=0pt and
// evens the lines out; left and center leave the spaces alone, center putting x at the
// middle of every line.
//
// data-fit="196x92" names a box instead of a width, and the size is then chosen too: the
// largest half-pixel from data-fit-range whose lines fill no more of the box's height
// than data-line-height gives them. Cards of a row written this way come out at the
// density their sentences allow, rather than at one size with the short ones gaping.
// How far a line has to open is then reported, not chosen for: data-fit-stretch (2 by
// default) says that under justify a space may open to that multiple of a natural space,
// otherwise that a line may fall to the width divided by it, and a label past it says
// loose in data-fits. One the box holds at no size in the range is drawn at the smallest
// and says no. The layout check reports both.
//
// The lines carry no whitespace between them: a newline there is drawn as a space and
// widens the bbox the layout check measures. Fonts arrive after the body, so the
// wrapping runs once now and again when they are ready; the sentence each label started
// from is kept here, since a hyphen the breaking added cannot be told from one the word
// was written with once it is on the page. data-lines then holds the count for the
// layout check to hold against data-max-lines.
(() => {
  const NS = "http://www.w3.org/2000/svg";
  const STEP = 0.5;
  const tex = window.texLineBreak_lib;
  const englishPatterns = window["texLineBreak_hyphens_en-us"];
  const hyphenate = tex.createHyphenator(englishPatterns.default || englishPatterns);
  const written = new WeakMap();

  const sentence = (text) => {
    if (!written.has(text)) {
      written.set(text, text.textContent.trim().replace(/\s+/g, " "));
    }
    return written.get(text);
  };

  // A label of its own, off the page, in the same font: the widths the breaking needs are
  // of words and of word pieces, which are not substrings of what the label shows.
  const ruler = (text) => {
    const node = document.createElementNS(NS, "text");
    node.setAttribute("x", "-10000");
    node.setAttribute("y", "-10000");
    const style = getComputedStyle(text);
    for (const property of ["fontFamily", "fontWeight", "fontStyle", "letterSpacing"]) {
      node.style[property] = style[property];
    }
    text.ownerSVGElement.appendChild(node);
    let widths = new Map();
    return {
      at(size) {
        node.style.fontSize = `${size}px`;
        widths = new Map();
      },
      width(piece) {
        // A run of spaces on its own measures nothing: an svg text run drops the spaces at
        // its edges, whatever xml:space says. Measured between two letters it is itself,
        // and the breaking reads spaces as free without this.
        if (/^\s+$/.test(piece)) return this.width(`a${piece}a`) - this.width("aa");
        if (!widths.has(piece)) {
          node.textContent = piece;
          widths.set(piece, node.getComputedTextLength());
        }
        return widths.get(piece);
      },
      done() {
        node.remove();
      },
    };
  };

  const linesOf = (words, width, measure) => {
    const items = tex.layoutItemsFromString(words, measure, hyphenate);
    // TeX may set a line's spaces narrower than they were drawn to fit one more word, and
    // then the line's own letters run past the width: on the last line, which is not
    // stretched to the width and so keeps what it was given, that ran 6px out of a 188px
    // card. A space here keeps its width and a line takes only what fits.
    for (const item of items) if (item.type === "glue") item.shrink = 0;
    const breaks = tex.breakLines(items, width, { maxAdjustmentRatio: null });
    const lines = [];
    for (let line = 0; line < breaks.length - 1; line++) {
      const from = tex.lineContentStart(items, breaks[line], breaks[line + 1]);
      const to = breaks[line + 1];
      let shown = "";
      for (let index = from; index < to; index++) {
        const item = items[index];
        if (item.type === "box" || item.type === "glue") shown += item.text || "";
      }
      // A break inside a word carries a hyphen, and the hyphen is part of that line.
      if (items[to].type === "penalty" && items[to].width > 0) shown += "-";
      lines.push(shown.trim());
    }
    return lines;
  };

  const wrap = (text) => {
    const words = sentence(text);
    if (words === "") return;
    const box = (text.dataset.fit || "").split("x").map(Number);
    const fitting = box.length === 2 && box[0] > 0 && box[1] > 0;
    const width = fitting ? box[0] : Number(text.dataset.wrap);
    if (!(width > 0)) return;
    const align = text.dataset.align || "left";
    const lineHeight = Number(text.dataset.lineHeight) || 1.35;
    const rule = ruler(text);
    const measure = (piece) => rule.width(piece);
    const broken = (size, at) => {
      rule.at(size);
      return linesOf(words, at === undefined ? width : at, measure);
    };
    // Balance: the same lines the width asks for, at the narrowest width that still needs
    // no more of them, so the last line is no shorter than the rest.
    const evened = (size, lines) => {
      let low = 0;
      let high = width;
      while (high - low > 0.25) {
        const middle = (low + high) / 2;
        if (broken(size, middle).length <= lines.length) high = middle; else low = middle;
      }
      return broken(size, high);
    };

    try {
      let size;
      let lines;
      if (fitting) {
        // The size the skin sets is the largest tried, so a label never outgrows its deck;
        // the inline size a previous run left behind is cleared first to read it.
        text.style.fontSize = "";
        const range = (text.dataset.fitRange || "").trim().split(/\s+/).map(Number);
        const high = range.length === 2 && range[1] > 0 ? range[1] : parseFloat(getComputedStyle(text).fontSize);
        const low = range.length === 2 && range[0] > 0 ? range[0] : 8;
        let held = false;
        for (size = high; size >= low - 1e-9; size -= STEP) {
          lines = broken(size);
          if (lines.length * lineHeight * size <= box[1]) {
            held = true;
            break;
          }
        }
        if (!held) {
          size = low;
          lines = broken(size);
        }
        text.style.fontSize = `${size}px`;
        const stretch = Number(text.dataset.fitStretch) || 2;
        const loose = lines.slice(0, -1).some((line) => {
          const gaps = line.split(" ").length - 1;
          const slack = width - rule.width(line);
          if (align !== "justify") return rule.width(line) < width / stretch;
          return gaps > 0 && slack / gaps > (stretch - 1) * rule.width(" ");
        });
        if (!held) text.dataset.fits = "no";
        else if (loose) text.dataset.fits = "loose";
        else delete text.dataset.fits;
        text.dataset.fitSize = String(size);
      } else {
        size = parseFloat(getComputedStyle(text).fontSize);
        lines = broken(size);
      }

      if (align === "balance" && lines.length > 1) lines = evened(size, lines);
      const x = Number(text.getAttribute("x")) || 0;
      if (align === "center") text.setAttribute("text-anchor", "middle");
      text.textContent = "";
      lines.forEach((shown, index) => {
        const line = document.createElementNS(NS, "tspan");
        line.setAttribute("x", String(x));
        line.setAttribute("dy", index === 0 ? "0" : String(lineHeight * size));
        line.textContent = shown;
        const gaps = shown.split(" ").length - 1;
        if (align === "justify" && index < lines.length - 1 && gaps > 0) {
          line.setAttribute("word-spacing", String((width - rule.width(shown)) / gaps));
        }
        text.appendChild(line);
      });
      text.dataset.lines = String(lines.length);
    } finally {
      rule.done();
    }
  };

  const wrapAll = () => {
    for (const text of document.querySelectorAll("svg text[data-wrap], svg text[data-fit]")) {
      try {
        wrap(text);
      } catch (error) {
        // A label that is not rendered has no lengths to measure; it keeps its sentence.
      }
    }
  };
  wrapAll();
  document.fonts.ready.then(wrapAll);
})();
