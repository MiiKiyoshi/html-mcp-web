// A long label in an inline svg is written as one sentence and broken into lines here,
// in the deck itself, with the font the skin renders it in: the content file holds
//
//   <text x=".." y=".." data-wrap="196" data-align="justify" data-line-height="1.35"
//         data-max-lines="4">one sentence</text>
//
// and the deck shows tspans, one per line, x set on each and dy stepping down. Each word
// and one space are measured once on the sentence itself, and a line's width is their
// sum. left and center break greedily: a line takes words while they fit the width.
// balance keeps that line count and chooses the breaks that leave the least slack,
// squared, over all the lines, so they come out even: a greedy pass at a narrowed width
// broke before a long word and left a stub half the length of its neighbours. justify
// does the same over every line but the last, which stays ragged, so the spaces it
// widens are alike from line to line. center puts x at the middle of every line;
// justify widens the spaces of every line but the last to the full width.
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
// wrapping runs once now and again when they are ready; a second run reads the sentence
// back from the lines, the words joined by spaces. data-lines then holds the count for
// the layout check to hold against data-max-lines.
(() => {
  const NS = "http://www.w3.org/2000/svg";
  const STEP = 0.5;
  const sentence = (text) => Array.from(text.childNodes).map((node) => node.textContent)
    .join(" ").trim().replace(/\s+/g, " ");

  // Every width a break needs, at the size the label is set in now.
  const measure = (text, words) => {
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
    return {
      starts, ends, count, run, space,
      // The width of the words first..last on one line.
      lineWidth: (first, last) => prefix[last + 1] - prefix[first] + (last - first) * space,
    };
  };

  // Greedy: a line takes words while they fit; a word wider than the width stands alone
  // on its line.
  const greedy = (sizes, width) => {
    const rows = [];
    let first = 0;
    for (let word = 1; word < sizes.count; word++) {
      if (sizes.lineWidth(first, word) > width) {
        rows.push([first, word - 1]);
        first = word;
      }
    }
    rows.push([first, sizes.count - 1]);
    return rows;
  };

  // The same number of lines, none wider than the width, with the least slack squared
  // over the lines, the last one left out when it stays ragged. best[k][j]: the first j
  // words on k lines.
  const even = (sizes, width, lines, lastFree) => {
    const count = sizes.count;
    const best = Array.from({ length: lines + 1 }, () => new Array(count + 1).fill(Infinity));
    const from = Array.from({ length: lines + 1 }, () => new Array(count + 1).fill(-1));
    best[0][0] = 0;
    for (let k = 1; k <= lines; k++) {
      for (let j = k; j <= count; j++) {
        for (let i = k - 1; i < j; i++) {
          if (best[k - 1][i] === Infinity) continue;
          const slack = width - sizes.lineWidth(i, j - 1);
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

  const breakInto = (sizes, width, align) => {
    const rows = greedy(sizes, width);
    if (rows.length === 1) return rows;
    if (align === "balance") return even(sizes, width, rows.length, false) || rows;
    if (align === "justify") return even(sizes, width, rows.length, true) || rows;
    return rows;
  };

  // A line other than the last that would have to open too far: under justify its spaces
  // carry the slack, otherwise the slack shows as raggedness. A line of one word has no
  // space to open and is left alone.
  const loose = (sizes, rows, width, align, stretch) => rows.slice(0, -1).some(([first, last]) => {
    const line = sizes.lineWidth(first, last);
    if (align !== "justify") return line < width / stretch;
    return last > first && (width - line) / (last - first) > (stretch - 1) * sizes.space;
  });

  const wrap = (text) => {
    const words = sentence(text);
    if (words === "") return;
    text.textContent = words;
    const box = (text.dataset.fit || "").split("x").map(Number);
    const fitting = box.length === 2 && box[0] > 0 && box[1] > 0;
    const width = fitting ? box[0] : Number(text.dataset.wrap);
    if (!(width > 0)) return;
    const align = text.dataset.align || "left";
    const lineHeight = Number(text.dataset.lineHeight) || 1.35;

    let size;
    let rows;
    let sizes;
    if (fitting) {
      // The size the skin sets is the largest tried, so a label never outgrows its deck;
      // the inline size a previous run left behind is cleared first to read it.
      text.style.fontSize = "";
      const range = (text.dataset.fitRange || "").trim().split(/\s+/).map(Number);
      const high = range.length === 2 && range[1] > 0 ? range[1] : parseFloat(getComputedStyle(text).fontSize);
      const low = range.length === 2 && range[0] > 0 ? range[0] : 8;
      const stretch = Number(text.dataset.fitStretch) || 2;
      // The height decides the size: the largest that holds is taken, so cards of a row
      // come out at the density their sentences allow. How far a line opens is reported
      // rather than chosen for, since it barely moves with the size: both a line's slack
      // and its spaces grow with the letters, so a sentence set loose at one size is
      // loose at every size, and picking a size by it left a two-line card at 12px in a
      // box that held 14.5px.
      let held = false;
      for (size = high; size >= low - 1e-9; size -= STEP) {
        text.style.fontSize = `${size}px`;
        if (breakInto(measure(text, words), width, align).length * lineHeight * size <= box[1]) {
          held = true;
          break;
        }
      }
      if (!held) size = low;
      text.style.fontSize = `${size}px`;
      sizes = measure(text, words);
      rows = breakInto(sizes, width, align);
      if (!held) text.dataset.fits = "no";
      else if (loose(sizes, rows, width, align, stretch)) text.dataset.fits = "loose";
      else delete text.dataset.fits;
      text.dataset.fitSize = String(size);
    } else {
      size = parseFloat(getComputedStyle(text).fontSize);
      sizes = measure(text, words);
      rows = breakInto(sizes, width, align);
    }

    const x = Number(text.getAttribute("x")) || 0;
    if (align === "center") text.setAttribute("text-anchor", "middle");
    // The line's own width, measured whole, so a justified line lands on the width exactly.
    const widths = rows.map(([first, last]) => sizes.run(sizes.starts[first], sizes.ends[last]));
    text.textContent = "";
    rows.forEach(([first, last], index) => {
      const line = document.createElementNS(NS, "tspan");
      line.setAttribute("x", String(x));
      line.setAttribute("dy", index === 0 ? "0" : String(lineHeight * size));
      line.textContent = words.slice(sizes.starts[first], sizes.ends[last]);
      if (align === "justify" && index < rows.length - 1 && last > first) {
        line.setAttribute("word-spacing", String((width - widths[index]) / (last - first)));
      }
      text.appendChild(line);
    });
    text.dataset.lines = String(rows.length);
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
