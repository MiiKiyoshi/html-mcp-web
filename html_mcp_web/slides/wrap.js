// A long label in an inline svg is written as one sentence and broken into lines here,
// in the deck itself, with the font the skin renders it in: the content file holds
//
//   <text x=".." y=".." data-wrap="196" data-align="justify" data-line-height="1.35"
//         data-max-lines="4">one sentence</text>
//
// and the deck shows tspans, one per line, x set on each and dy stepping down. Each word
// and one space are measured once on the sentence itself, and a line's width is their
// sum. left and center break greedily: a line takes words while they fit data-wrap.
// balance keeps that line count and chooses the breaks that leave the least slack,
// squared, over all the lines, so they come out even: a greedy pass at a narrowed width
// broke before a long word and left a stub half the length of its neighbours. justify
// does the same over every line but the last, which stays ragged, so the spaces it
// widens are alike from line to line. center puts x at the middle of every line;
// justify widens the spaces of every line but the last to the full width. The lines
// carry no whitespace between them: a newline there is drawn as a space and widens the
// bbox the layout check measures. Fonts arrive after the body, so the wrapping runs
// once now and again when they are ready; a second run reads the sentence back from
// the lines, the words joined by spaces. data-lines then holds the count for the layout
// check to hold against data-max-lines.
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
    const count = starts.length;
    const run = (from, to) => text.getSubStringLength(from, to - from);
    const space = count > 1 ? run(ends[0], starts[1]) : 0;
    const prefix = [0];
    starts.forEach((start, word) => prefix.push(prefix[word] + run(start, ends[word])));
    // The width of the words first..last on one line.
    const lineWidth = (first, last) => prefix[last + 1] - prefix[first] + (last - first) * space;

    // Greedy: a line takes words while they fit; a word wider than the width stands
    // alone on its line.
    const greedy = () => {
      const rows = [];
      let first = 0;
      for (let word = 1; word < count; word++) {
        if (lineWidth(first, word) > width) {
          rows.push([first, word - 1]);
          first = word;
        }
      }
      rows.push([first, count - 1]);
      return rows;
    };
    // The same number of lines, none wider than the width, with the least slack squared
    // over the lines, the last one left out when it stays ragged. best[k][j]: the first
    // j words on k lines.
    const even = (lines, lastFree) => {
      const best = Array.from({ length: lines + 1 }, () => new Array(count + 1).fill(Infinity));
      const from = Array.from({ length: lines + 1 }, () => new Array(count + 1).fill(-1));
      best[0][0] = 0;
      for (let k = 1; k <= lines; k++) {
        for (let j = k; j <= count; j++) {
          for (let i = k - 1; i < j; i++) {
            if (best[k - 1][i] === Infinity) continue;
            const slack = width - lineWidth(i, j - 1);
            if (slack < 0) continue;
            const cost = best[k - 1][i] + (lastFree && k === lines ? 0 : slack * slack);
            if (cost < best[k][j]) {
              best[k][j] = cost;
              from[k][j] = i;
            }
          }
        }
      }
      if (best[lines][count] === Infinity) return null;
      const rows = [];
      for (let k = lines, j = count; k >= 1; k--) {
        rows.unshift([from[k][j], j - 1]);
        j = from[k][j];
      }
      return rows;
    };

    const align = text.dataset.align || "left";
    let rows = greedy();
    if (align === "balance" && rows.length > 1) rows = even(rows.length, false) || rows;
    if (align === "justify" && rows.length > 1) rows = even(rows.length, true) || rows;
    const x = Number(text.getAttribute("x")) || 0;
    const step = (Number(text.dataset.lineHeight) || 1.35) * parseFloat(getComputedStyle(text).fontSize);
    if (align === "center") text.setAttribute("text-anchor", "middle");
    // The line's own width, measured whole, so a justified line lands on the width exactly.
    const widths = rows.map(([first, last]) => run(starts[first], ends[last]));
    text.textContent = "";
    rows.forEach(([first, last], index) => {
      const line = document.createElementNS(NS, "tspan");
      line.setAttribute("x", String(x));
      line.setAttribute("dy", index === 0 ? "0" : String(step));
      line.textContent = words.slice(starts[first], ends[last]);
      if (align === "justify" && index < rows.length - 1 && last > first) {
        line.setAttribute("word-spacing", String((width - widths[index]) / (last - first)));
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
