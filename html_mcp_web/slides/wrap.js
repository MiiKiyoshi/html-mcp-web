// A long label in an inline svg is written as one sentence and broken into lines here,
// in the deck itself, with the font the skin renders it in: the content file holds
//
//   <text x=".." y=".." data-wrap="196" data-align="justify" data-line-height="1.35"
//         data-max-lines="4">one sentence</text>
//
// and the deck shows tspans, one per line, x set on each and dy stepping down. Lines
// break between words at the widest run that fits data-wrap, measured on the sentence
// itself; center puts x at the middle of every line, justify widens the spaces of every
// line but the last to the full width, balance takes the line count of left and then
// the narrowest width that still needs no more lines, so the lines come out even. The
// lines carry no whitespace between them: a newline there is drawn as a space and
// widens the bbox the layout check measures. Fonts arrive after the body, so the
// wrapping runs once now and again when they are ready; a second run reads the sentence
// back from the lines, the words joined by spaces. data-lines then holds the count for
// the layout check to hold against data-max-lines.
(() => {
  const NS = "http://www.w3.org/2000/svg";
  const sentence = (text) => Array.from(text.childNodes).map((node) => node.textContent)
    .join(" ").trim().replace(/\s+/g, " ");

  const wrap = (text) => {
    const width = Number(text.dataset.wrap);
    const words = sentence(text);
    if (!(width > 0) || words === "") return;
    text.textContent = words;
    const starts = [];
    const ends = [];
    let at = 0;
    for (const word of words.split(" ")) {
      starts.push(at);
      ends.push(at + word.length);
      at += word.length + 1;
    }
    const run = (from, to) => text.getSubStringLength(from, to - from);
    // Greedy: a line takes words while the run from its first word still fits; a word
    // wider than the width stands alone on its line.
    const breakAt = (limit) => {
      const rows = [];
      let first = 0;
      for (let word = 1; word < starts.length; word++) {
        if (run(starts[first], ends[word]) > limit) {
          rows.push([starts[first], ends[word - 1]]);
          first = word;
        }
      }
      rows.push([starts[first], ends[ends.length - 1]]);
      return rows;
    };
    const align = text.dataset.align || "left";
    let rows = breakAt(width);
    if (align === "balance" && rows.length > 1) {
      let low = 0;
      let high = width;
      while (high - low > 0.5) {
        const middle = (low + high) / 2;
        if (breakAt(middle).length <= rows.length) high = middle; else low = middle;
      }
      rows = breakAt(high);
    }
    const widths = rows.map(([from, to]) => run(from, to));
    const x = Number(text.getAttribute("x")) || 0;
    const step = (Number(text.dataset.lineHeight) || 1.35) * parseFloat(getComputedStyle(text).fontSize);
    if (align === "center") text.setAttribute("text-anchor", "middle");
    text.textContent = "";
    rows.forEach(([from, to], index) => {
      const line = document.createElementNS(NS, "tspan");
      line.setAttribute("x", String(x));
      line.setAttribute("dy", index === 0 ? "0" : String(step));
      line.textContent = words.slice(from, to);
      const gaps = words.slice(from, to).split(" ").length - 1;
      if (align === "justify" && index < rows.length - 1 && gaps > 0) {
        line.setAttribute("word-spacing", String((width - widths[index]) / gaps));
      }
      text.appendChild(line);
    });
    text.dataset.lines = String(rows.length);
  };

  const wrapAll = () => {
    for (const text of document.querySelectorAll("svg text[data-wrap]")) {
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
