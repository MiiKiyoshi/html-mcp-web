const out = [];
const leaf = (element) => {
  if (element.closest('svg, .katex, .svg-html-layer') !== null) return false;
  const display = getComputedStyle(element).display;
  if (!/^(block|list-item|table-cell)$/.test(display)) return false;
  const direct = Array.from(element.childNodes).some((n) => n.nodeType === 3 && n.data.trim() !== '');
  const inlineText = Array.from(element.children).some((c) => !/^(block|list-item|table|flex|grid)$/.test(getComputedStyle(c).display) && c.textContent.trim() !== '');
  const blockChild = Array.from(element.children).some((c) => /^(block|list-item|table|flex|grid)$/.test(getComputedStyle(c).display) && !c.matches('.eqno, .katex-display'));
  return (direct || inlineText) && !blockChild;
};
document.querySelectorAll('main.pages > section.page').forEach((page, pi) => {
  const lines = [];
  for (const block of Array.from(page.querySelectorAll('*')).filter(leaf)) {
    const pitch = parseFloat(getComputedStyle(block).lineHeight) || 14;
    const rows = [];
    const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const t = walker.currentNode;
      if (t.parentElement.closest('.katex-mathml, .eqno') !== null) continue;
      for (let i = 0; i < t.length; i += 1) {
        const r = document.createRange(); r.setStart(t, i); r.setEnd(t, i + 1);
        const b = Array.from(r.getClientRects()).find((x) => x.width > 0 || x.height > 0);
        if (!b) continue;
        const mid = (b.top + b.bottom) / 2;
        let row = rows.find((x) => Math.abs(x.mid - mid) < pitch / 2);
        if (!row) rows.push(row = { mid, text: '' });
        row.text += t.data[i];
      }
    }
    rows.sort((a, b) => a.mid - b.mid);
    for (const row of rows) {
      const words = row.text.replace(/‐$/, '').trim().split(/\s+/);
      if (words[0] !== '') lines.push(words[0] + ' … ' + words[words.length - 1]);
    }
  }
  out.push(lines);
});
return out;
