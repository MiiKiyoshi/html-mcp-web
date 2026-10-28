// A table too wide for its place shares the width out as tabularx does: a column whose
// longest line fits in an even share of the width left keeps that line whole, and the
// columns of longer text divide what remains and wrap. Left to the browser, every column
// gave up width in proportion to its text, so a column of short labels such as "TODO 1-5"
// broke in two beside a column of sentences that could have taken the line.
//
// The widths are measured on the page, in the face it is set in, and a cell of a column
// kept whole gets data-fit-line, which the components draw without wrapping. A cell
// spanning several columns is left to wrap.
(() => {
  const grid = (table) => {
    const columns = [];
    const covered = [];
    Array.from(table.rows).forEach((row, r) => {
      let column = 0;
      for (const cell of row.cells) {
        while (covered[r]?.[column]) column += 1;
        for (let down = 0; down < cell.rowSpan; down += 1) {
          for (let across = 0; across < cell.colSpan; across += 1) {
            (covered[r + down] ??= [])[column + across] = true;
          }
        }
        if (cell.colSpan === 1) (columns[column] ??= []).push(cell);
        column += cell.colSpan;
      }
    });
    return columns;
  };

  const fit = (table) => {
    const cells = Array.from(table.querySelectorAll("[data-fit-line]"));
    cells.forEach((cell) => cell.removeAttribute("data-fit-line"));
    const width = table.offsetWidth;
    if (width === 0) return;
    const columns = grid(table).map((column) => column ?? []);
    // Each column's longest line: the table laid out with no line broken.
    const before = table.style.width;
    table.style.width = "max-content";
    table.querySelectorAll("th, td").forEach((cell) => cell.setAttribute("data-fit-line", ""));
    const longest = columns.map((column) => column.length ? column[0].offsetWidth : 0);
    const natural = table.offsetWidth;
    table.querySelectorAll("th, td").forEach((cell) => cell.removeAttribute("data-fit-line"));
    table.style.width = before;
    if (natural <= width + 0.5) return;
    let open = columns.map((_, index) => index).filter((index) => columns[index].length);
    let left = width;
    for (;;) {
      const share = left / open.length;
      const kept = open.filter((index) => longest[index] <= share);
      if (kept.length === 0 || kept.length === open.length) break;
      for (const index of kept) {
        left -= longest[index];
        columns[index].forEach((cell) => cell.setAttribute("data-fit-line", ""));
      }
      open = open.filter((index) => !kept.includes(index));
    }
  };

  window.htmlMcpFitColumns = fit;
  const setup = (root) => root.querySelectorAll("table").forEach(fit);
  setup(document);
  document.fonts.ready.then(() => setup(document));
  (window.htmlMcpPageSetup ??= []).push(setup);
})();
