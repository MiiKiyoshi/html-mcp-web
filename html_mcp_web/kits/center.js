// A label set on a shape, such as a letter in a box or a sign in a circle, is written with
// x and y at the shape's middle and data-center, and the middle of its letters lands
// there:
//
//   <circle cx="150" cy="120" r="10"/>
//   <text x="150" y="120" data-center>+</text>
//
// y in svg is the baseline, and dominant-baseline="central" is the middle of the face's
// em box, not of the letters drawn: a "+" so placed sat 3.5 units above its circle's
// middle, an italic W 1.7 units right of its box's. Coordinates tuned by hand moved again
// with each change of face. Here the letters' extent is read from the face itself, with a
// canvas measureText in the label's font, and the label is moved by dx and dy, so x and y
// keep the middle the content gave. The extent is measured at a hundred times the size,
// since Firefox gives it in whole pixels: at 13px an x read 0 to 7 where it is drawn from
// 0.45 to 6.95. data-center="x" or "y" centres one direction only, and the other keeps
// text-anchor or the baseline. A centred label is one line of plain text, and the
// builder stops on one holding markup or broken by data-wrap or data-fit.
//
// A <foreignObject data-center>'s HTML, such as a formula, has the middle of its ink at
// the middle of the foreignObject, rather than the middle of the line box that holds it,
// which a fraction or a tall letter leaves off its centre.
(() => {
  // A report the builder has set keeps what was measured when it was set.
  if (document.documentElement.hasAttribute("data-frozen")) return;
  const SCALE = 100;
  const context = document.createElement("canvas").getContext("2d");
  const ALIGN = { start: "left", middle: "center", end: "right" };

  const fontOf = (style, size) => `${style.fontStyle} ${style.fontWeight} ${size}px ${style.fontFamily}`;

  const centerText = (text) => {
    const axes = text.dataset.center || "both";
    // The extent is read from the alphabetic baseline, which y then names, whatever
    // baseline the label was given.
    if (axes !== "x") text.style.dominantBaseline = "alphabetic";
    const style = getComputedStyle(text);
    context.font = fontOf(style, parseFloat(style.fontSize) * SCALE);
    context.textAlign = ALIGN[style.textAnchor] ?? "left";
    context.textBaseline = "alphabetic";
    const ink = context.measureText(text.textContent);
    const dx = -(ink.actualBoundingBoxRight - ink.actualBoundingBoxLeft) / 2 / SCALE;
    const dy = (ink.actualBoundingBoxAscent - ink.actualBoundingBoxDescent) / 2 / SCALE;
    if (axes !== "y") text.setAttribute("dx", dx.toFixed(3));
    if (axes !== "x") text.setAttribute("dy", dy.toFixed(3));
  };

  const centerHtml = (box) => {
    const axes = box.dataset.center || "both";
    box.style.translate = "";
    const outer = box.getBoundingClientRect();
    const scale = outer.width / box.offsetWidth;
    // A run of text is drawn from its box's left edge and round its baseline, which an
    // empty inline-block set before it stands on, and its letters reach as far round
    // that point as measureText says. The face's ascent below the box's top is no
    // baseline: Firefox rounds the box to whole pixels, and letters so placed were read
    // half a unit high. A run that draws nothing, such as a zero-width space, is no ink.
    // A fraction's rule and a drawn sign, such as a root, are ink all over.
    const range = document.createRange();
    const letters = [];
    const nodes = [];
    const walker = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
      if (node.nodeValue.trim() !== "" && node.parentElement.closest(".katex-mathml") === null) nodes.push(node);
    }
    for (const node of nodes) {
      range.selectNodeContents(node);
      const rects = range.getClientRects();
      if (rects.length !== 1) continue;
      const style = getComputedStyle(node.parentElement);
      context.font = fontOf(style, parseFloat(style.fontSize) * SCALE);
      context.textAlign = "left";
      const ink = context.measureText(node.nodeValue);
      if (ink.actualBoundingBoxLeft + ink.actualBoundingBoxRight <= 0
          || ink.actualBoundingBoxAscent + ink.actualBoundingBoxDescent <= 0) continue;
      const probe = document.createElement("span");
      probe.style.cssText = "display: inline-block; width: 0; height: 0";
      node.before(probe);
      const baseline = probe.getBoundingClientRect().bottom;
      probe.remove();
      const left = rects[0].left;
      const k = scale / SCALE;
      letters.push({
        left: left - ink.actualBoundingBoxLeft * k, right: left + ink.actualBoundingBoxRight * k,
        top: baseline - ink.actualBoundingBoxAscent * k, bottom: baseline + ink.actualBoundingBoxDescent * k,
      });
    }
    for (const drawn of box.querySelectorAll(".frac-line, .katex-html svg")) letters.push(drawn.getBoundingClientRect());
    if (letters.length === 0) return;
    const middle = (low, high) => (Math.min(...letters.map(low)) + Math.max(...letters.map(high))) / 2;
    const dx = axes === "y" ? 0 : ((outer.left + outer.right) / 2 - middle((r) => r.left, (r) => r.right)) / scale;
    const dy = axes === "x" ? 0 : ((outer.top + outer.bottom) / 2 - middle((r) => r.top, (r) => r.bottom)) / scale;
    box.style.translate = `${dx.toFixed(3)}px ${dy.toFixed(3)}px`;
  };

  const centerIn = (root) => {
    for (const text of root.querySelectorAll("svg text[data-center]")) centerText(text);
    for (const box of root.querySelectorAll(".svg-html-box[data-center]")) {
      if (box.offsetWidth > 0) centerHtml(box);
    }
  };
  const centerAll = () => centerIn(document);
  // Each face a label uses is asked for by name, so its arrival does not wait on the
  // browser deciding to fetch it, and every label is centred again when one arrives.
  const askFaces = (root) => {
    const faces = new Map();
    for (const text of root.querySelectorAll("svg text[data-center]")) {
      const font = fontOf(getComputedStyle(text), parseFloat(getComputedStyle(text).fontSize));
      if (!faces.has(font)) faces.set(font, text.textContent);
    }
    Promise.allSettled(Array.from(faces, ([font, sample]) => document.fonts.load(font, sample))).then(() => centerIn(root));
  };
  const setup = (root) => {
    centerIn(root);
    askFaces(root);
  };
  setup(document);
  document.fonts.ready.then(centerAll);
  document.fonts.addEventListener("loadingdone", centerAll);
  (window.htmlMcpPageSetup ??= []).push(setup);
})();
