import { measureArtifactSpace, groupLines, elementRef } from "./space-measure.js";

export function createLayoutChecks(dependencies) {
  const {
    $,
    artifactBase,
    artifactPages,
    clear,
    fetchJson,
    frameDocument,
    frameWindow,
    h,
    state,
  } = dependencies;

  function inNormalFlow(element) {
    const style = frameWindow().getComputedStyle(element);
    return style.display !== "none" && style.position !== "fixed" && style.position !== "absolute";
  }
  
  // The words as the slide shows them. KaTeX keeps a MathML copy of every formula for
  // screen readers, holding the TeX source, and textContent runs the two together: a
  // bullet opening with a formula was named "iceff‾\overline{i_{c_{\m…", which does not
  // match anything the writer can find in the source.
  function readableText(element) {
    const copy = element.cloneNode(true);
    for (const hidden of copy.querySelectorAll(".katex-mathml")) hidden.remove();
    return copy.textContent.trim().replace(/\s+/g, " ");
  }

  // Where the viewBox lands inside the element box, and at what scale. An element box of a
  // different shape from the viewBox does not stretch the drawing: the rendering keeps the
  // viewBox's proportions and sits in the box according to preserveAspectRatio, leaving a
  // band on the two sides that are over-long.
  function placeViewBox(element, view, room) {
    const ratio = element.preserveAspectRatio?.baseVal;
    const align = ratio ? ratio.align : 6;  // xMidYMid, the default
    const slice = ratio ? ratio.meetOrSlice === 2 : false;
    if (align === 1) {  // none: the drawing is stretched, so no band is left
      return { x: 0, y: 0, scale: 1, scaleX: room.width / view.width, scaleY: room.height / view.height };
    }
    const scale = slice
      ? Math.max(room.width / view.width, room.height / view.height)
      : Math.min(room.width / view.width, room.height / view.height);
    const fraction = [0, 0.5, 1];
    const across = fraction[(align - 2) % 3];
    const down = fraction[Math.floor((align - 2) / 3)];
    return {
      x: (room.width - view.width * scale) * across,
      y: (room.height - view.height * scale) * down,
      scale,
      scaleX: scale,
      scaleY: scale,
    };
  }

  function describeElement(element) {
    const name = element.tagName.toLowerCase();
    const id = element.id === "" ? "" : `#${element.id}`;
    const cls = element.classList.length === 0 ? "" : `.${Array.from(element.classList).join(".")}`;
    return `<${name}${id}${cls}>`;
  }
  
  // Maps each layout error text to the element that produced it, so a click on
  // the Problems tab can reveal the spot. Rebuilt on every local layout check;
  // errors checked by another browser fall back to page-number parsing.
  const problemTargets = new Map();
  
  // Runs read() with the page zoom lifted and puts it back before returning, so a
  // measurement that the zoom would distort is taken in the artifact's own scale.
  function unzoomed(read) {
    const style = frameDocument().documentElement.style;
    const previous = style.getPropertyValue("--html-mcp-page-scale");
    style.setProperty("--html-mcp-page-scale", "1");
    try {
      return read();
    } finally {
      if (previous === "") style.removeProperty("--html-mcp-page-scale");
      else style.setProperty("--html-mcp-page-scale", previous);
    }
  }

  function safeBBox(element) {
    try {
      return element.getBBox();
    } catch {
      return null;
    }
  }

  function artifactLayoutErrors() {
    problemTargets.clear();
    const doc = frameDocument();
    const root = doc.querySelector("body > main.pages");
    if (root === null) return ['artifact body must contain exactly one <main class="pages"> element'];
    // Only elements in normal flow can push page breaks around. Elements injected by
    // browser extensions are usually out of flow and are excluded from printing, so they
    // are not reported as an authoring mistake.
    const extra = Array.from(doc.body.children).filter((child) => child !== root && inNormalFlow(child));
    const errors = [];
    let pages = [];
    // The error carries the block's ref, so the reader of inspect() can go straight to
    // measure_space(target=<ref>) instead of drilling down page by page to find which of
    // a page's four svgs the message meant.
    const addError = (message, element) => {
      const page = element ? element.closest("section.page") : null;
      const number = page === null ? 0 : pages.indexOf(page) + 1;
      if (number > 0 && element !== page) {
        try {
          message += ` [${elementRef(page, number, element)}]`;
        } catch (error) { /* an element outside its page keeps the plain message */ }
      }
      errors.push(message);
      if (element) problemTargets.set(message, element);
    };
    if (extra.length > 0) {
      addError(`artifact body must contain only <main class="pages">: found ${extra.map(describeElement).join(", ")}`, extra[0]);
    }
    const children = Array.from(root.children);
    if (children.length === 0) errors.push("main.pages must contain at least one section.page");
    for (const [index, child] of children.entries()) {
      // A template may place a speaker-script block after its page; it is screen-only
      // and carries no page geometry.
      if (child.classList.contains("script-block")) continue;
      if (!child.matches("section.page")) {
        addError(`main.pages child ${index + 1} must be <section class="page">`, child);
      }
    }
    pages = children.filter((child) => child.matches("section.page"));
    // Everything below is measured with the pane zoom lifted. The artifact prints at
    // its own scale, so that is the layout to judge; at a fitted zoom the browser wraps
    // text and rounds boxes differently, and the same page reports different problems
    // depending on how wide the reviewer's window happens to be.
    unzoomed(() => {
    for (const [index, page] of pages.entries()) {
      const horizontal = page.scrollWidth > page.clientWidth + 1;
      const vertical = page.scrollHeight > page.clientHeight + 1;
      if (horizontal || vertical) {
        const axes = [horizontal ? "width" : null, vertical ? "height" : null].filter((value) => value !== null).join(" and ");
        addError(`page ${index + 1} exceeds the ${state.artifact.layout} ${axes}`, page);
      }
      // Templates clip their content box (overflow: hidden), so page-level measurement
      // cannot see content spilling into the chrome (top/bottom bars). A template marks
      // its content area with data-layout-guard, and overflow inside it is an error.
      for (const guard of page.querySelectorAll("[data-layout-guard]")) {
        const gh = guard.scrollHeight > guard.clientHeight + 1;
        const gw = guard.scrollWidth > guard.clientWidth + 1;
        if (gh || gw) {
          const axes = [gw ? "width" : null, gh ? "height" : null].filter((value) => value !== null).join(" and ");
          const over = gh ? ` by ${guard.scrollHeight - guard.clientHeight}px` : "";
          addError(`page ${index + 1} content overflows its content area (${axes}${over})`, guard);
        }
      }
      // A block whose last line holds only a few characters wastes a full line
      // of height. Prose normally ends with a partial line, so only a very short
      // tail (a few characters wide) is flagged. Scope: any block-level element
      // that directly contains text because a tag whitelist missed styled divs.
      // Container elements hold only child elements, so they filter out here.
      for (const block of page.querySelectorAll("[data-layout-guard] *")) {
        const style = doc.defaultView.getComputedStyle(block);
        if (!/^(block|list-item|table-cell)$/.test(style.display)) continue;
        const hasDirectText = Array.from(block.childNodes).some(
          (node) => node.nodeType === Node.TEXT_NODE && node.nodeValue.trim() !== "");
        if (!hasDirectText) continue;
        const fontSize = parseFloat(style.fontSize) || 16;
        // A block one line tall has no last line to waste. Its rects can still fall into
        // two groups when an inline box sits well below the baseline, which a subscript or
        // one of KaTeX's own boxes does, and that reported one-line bullets as wasteful.
        const lineHeight = parseFloat(style.lineHeight) || fontSize * 1.2;
        if (Math.round(block.getBoundingClientRect().height / lineHeight) < 2) continue;
        const range = doc.createRange();
        range.selectNodeContents(block);
        const lines = groupLines(Array.from(range.getClientRects()), fontSize);
        if (lines.length < 2) continue;
        const widths = lines.map((l) => l.right - l.left);
        const last = widths[widths.length - 1];
        const widest = Math.max(...widths.slice(0, -1));
        // A tail is wasteful when it is tiny in absolute terms (a few characters)
        // or tiny relative to the block's own line width (a wide block whose
        // last line carries a fraction of what the lines above carry).
        if (last <= Math.max(fontSize * 6, widest * 0.25)) {
          const label = readableText(block).slice(0, 24);
          // The tail's own width is the amount to trim (or the room to fill): fitting it
          // took a fix-rebuild-inspect round before, just to learn how far off it was.
          addError(`page ${index + 1} ${block.tagName.toLowerCase()} "${label}…" wastes its last line `
            + `on a ${Math.round(last)}px tail`, block);
        }
      }
      // An SVG viewport hides whatever falls outside its viewBox, and no box-model
      // measurement sees it: the element reports the same scroll and client size
      // either way. getBBox holds the drawing's geometry, which is what the viewBox has
      // to cover; a stroke or an arrow head bleeds a sliver past it that no reader sees,
      // and that paint stays out of the comparison.
      for (const svg of Array.from(page.querySelectorAll("svg")).map((element) => {
        const view = element.viewBox?.baseVal;
        if (!view || view.width === 0 || view.height === 0) return null;
        let box;
        try {
          box = element.getBBox();
        } catch {
          return null;
        }
        if (box.width === 0 && box.height === 0) return null;
        return { element, view, box };
      }).filter((entry) => entry !== null)) {
        const { view, box } = svg;
        const drawn = {
          left: box.x,
          top: box.y,
          right: box.x + box.width,
          bottom: box.y + box.height,
        };
        const cut = {
          left: view.x - drawn.left,
          top: view.y - drawn.top,
          right: drawn.right - (view.x + view.width),
          bottom: drawn.bottom - (view.y + view.height),
        };
        const tolerance = {
          x: Math.max(1, view.width * 0.005),
          y: Math.max(1, view.height * 0.005),
        };
        const sides = Object.entries(cut)
          .filter(([side, amount]) => amount > (side === "top" || side === "bottom" ? tolerance.y : tolerance.x))
          .map(([side, amount]) => `${side} by ${Math.round(amount)}`);
        if (sides.length > 0) {
          addError(
            `page ${index + 1} ${describeElement(svg.element)} draws outside its viewBox and is cut off (${sides.join(", ")})`,
            svg.element);
        }
        // The opposite mistake: page space the drawing does not use. It comes from two
        // places at once. A viewBox roomier than the drawing leaves space inside, and an
        // element box of a different shape from the viewBox leaves a band above and below
        // or at both sides, because the rendering keeps the viewBox's proportions. The page
        // pays for the element box either way, so the strips are measured from it to the
        // drawing, in the pixels the strip actually occupies.
        const room = svg.element.getBoundingClientRect();
        const placed = placeViewBox(svg.element, view, room);
        const empty = {
          left: placed.x + (box.x - view.x) * placed.scaleX,
          top: placed.y + (box.y - view.y) * placed.scaleY,
          right: room.width - (placed.x + (box.x + box.width - view.x) * placed.scaleX),
          bottom: room.height - (placed.y + (box.y + box.height - view.y) * placed.scaleY),
        };
        const idle = Object.entries(empty)
          .filter(([side, pixels]) => {
            const across = side === "top" || side === "bottom";
            const share = pixels / (across ? room.height : room.width);
            return share >= 0.25 && pixels >= 100;
          })
          .map(([side, pixels]) => {
            const across = side === "top" || side === "bottom";
            const whole = across ? room.height : room.width;
            return `${side} ${Math.round((pixels / whole) * 100)}%, ${Math.round(pixels)}px of ${Math.round(whole)}`;
          });
        if (idle.length > 0) {
          addError(
            `page ${index + 1} ${describeElement(svg.element)} reserves space it does not draw in (${idle.join("; ")})`,
            svg.element);
        }
        // Two labels printed over each other are unreadable, and nothing else in this
        // file sees it: both sit inside the viewBox and the drawing fills its box.
        // Only labels are compared, because text over a shape or a line is normal.
        // A label box carries glyph padding, so neighbouring lines touch by a few
        // pixels as a matter of course; a collision covers much of both boxes.
        const labels = Array.from(svg.element.querySelectorAll("text"))
          .filter((text) => text.closest("defs, symbol, clipPath, mask, pattern, marker") === null)
          .map((text) => ({ text, box: safeBBox(text) }))
          .filter((label) => label.box !== null && label.box.width > 0 && label.box.height > 0);
        const collisions = [];
        for (let first = 0; first < labels.length; first++) {
          for (let second = first + 1; second < labels.length; second++) {
            const a = labels[first].box;
            const b = labels[second].box;
            const across = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
            const down = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
            if (across <= 0 || down <= 0) continue;
            if (across < Math.min(a.width, b.width) * 0.25) continue;
            if (down < Math.min(a.height, b.height) * 0.5) continue;
            collisions.push([labels[first].text, labels[second].text]);
          }
        }
        for (const [first, second] of collisions.slice(0, 3)) {
          const name = (node) => `"${node.textContent.trim().replace(/\s+/g, " ").slice(0, 30)}"`;
          addError(
            `page ${index + 1} ${describeElement(svg.element)} prints two labels over each other (${name(first)} / ${name(second)})`,
            svg.element);
        }
      }
      // In-flow siblings never overlap in normal flow, so any real overlap
      // (negative margins, transforms, oversized absolute children) covers
      // content and is reported as an error.
      for (const guard of page.querySelectorAll("[data-layout-guard]")) {
        const byParent = new Map();
        for (const el of guard.querySelectorAll("*")) {
          const style = doc.defaultView.getComputedStyle(el);
          if (style.display === "none" || style.visibility === "hidden") continue;
          if (style.position === "absolute" || style.position === "fixed") continue;
          if (!/^(block|list-item|table|flex|grid)$/.test(style.display)) continue;
          const rect = el.getBoundingClientRect();
          if (rect.width === 0 || rect.height === 0) continue;
          if (!byParent.has(el.parentElement)) byParent.set(el.parentElement, []);
          byParent.get(el.parentElement).push({ el, rect });
        }
        for (const siblings of byParent.values()) {
          for (let i = 0; i < siblings.length; i++) {
            for (let j = i + 1; j < siblings.length; j++) {
              const a = siblings[i];
              const b = siblings[j];
              const x = Math.min(a.rect.right, b.rect.right) - Math.max(a.rect.left, b.rect.left);
              const y = Math.min(a.rect.bottom, b.rect.bottom) - Math.max(a.rect.top, b.rect.top);
              if (x > 4 && y > 4) {
                addError(`page ${index + 1} ${describeElement(a.el)} overlaps its sibling ${describeElement(b.el)}`, b.el);
              }
            }
          }
        }
      }
    }
    });
    return errors;
  }
  
  function updateLayoutUi() {
    const status = $("#artifact-status");
    const layoutCheck = state.artifact.layout_check;
    const checked = layoutCheck.checked_revision === state.revision;
    const errors = checked ? layoutCheck.errors : [];
    status.textContent = checked ? (errors.length === 0 ? "ready" : "layout error") : "checking";
    status.classList.toggle("error", errors.length > 0);
    renderProblems(checked, errors);
  }
  
  // The Problems tab mirrors what the agent sees in inspect(): the build error,
  // then the layout errors for the current revision.
  function renderProblems(checked, errors) {
    const list = $("#problems-list");
    const count = $("#problems-count");
    if (list === null) return;
    clear(list);
    const problems = [];
    if (state.artifact.build_error) problems.push({ kind: "build", text: state.artifact.build_error });
    // A check that cannot be reported is worse than one that finds something: the tab said
    // only that nothing had been checked yet, which reads as "wait a moment" forever.
    if (state.layoutCheckError) problems.push({ kind: "check", text: state.layoutCheckError });
    for (const error of errors) problems.push({ kind: "layout", text: error });
    if (!checked && !state.artifact.build_error && problems.length === 0) {
      list.appendChild(h("p", { class: "placeholder", text: "Layout not checked yet for the current revision." }));
    } else if (problems.length === 0) {
      list.appendChild(h("p", { class: "placeholder", text: "No problems." }));
    } else {
      for (const problem of problems) {
        const item = h("div", { class: "problem" });
        item.appendChild(h("span", { class: "problem-kind", text: problem.kind }));
        item.appendChild(h("span", { text: problem.text }));
        if (problem.kind === "layout") {
          item.classList.add("clickable");
          item.addEventListener("click", () => revealProblem(problem.text));
        }
        list.appendChild(item);
      }
    }
    count.textContent = String(problems.length);
    count.classList.toggle("hidden", problems.length === 0);
  }
  
  // Scrolls the artifact to the element behind a layout error and flashes an
  // outline on it. When the error came from a check run in another browser the
  // element map is empty, so the page number in the text is the fallback.
  function revealProblem(text) {
    let target = problemTargets.get(text);
    if (!target || !target.isConnected) {
      const match = text.match(/^page (\d+)/);
      target = match ? artifactPages()[Number(match[1]) - 1] : null;
    }
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    const previous = target.style.outline;
    target.style.outline = "3px solid #e0955a";
    target.style.outlineOffset = "2px";
    setTimeout(() => {
      target.style.outline = previous;
      target.style.outlineOffset = "";
    }, 1500);
  }
  
  async function checkArtifactLayout() {
    if (state.slideShow) return;
    const revision = state.revision;
    const body = JSON.stringify({
      revision,
      errors: artifactLayoutErrors(),
      // Space is reported in page pixels, so it is read at the page's own scale too.
      space: unzoomed(() => measureArtifactSpace(frameDocument())),
    });
    let payload;
    try {
      payload = await fetchJson(`${artifactBase()}/layout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      });
    } catch (error) {
      state.layoutCheckError =
        `the layout check ran but could not be reported (${String(error.message || error)}); `
        + `the measurement was ${Math.round(body.length / 1024)}KB`;
      updateLayoutUi();
      throw error;
    }
    state.layoutCheckError = null;
    if (state.revision !== revision) return;
    state.artifact = payload;
    updateLayoutUi();
  }
  
  function scheduleLayoutCheck() {
    if (state.slideShow) return;
    const win = frameWindow();
    if (state.layoutFrame !== null) win.cancelAnimationFrame(state.layoutFrame);
    state.layoutFrame = win.requestAnimationFrame(() => {
      state.layoutFrame = null;
      win.requestAnimationFrame(() => {
        if (!state.slideShow) checkArtifactLayout().catch((error) => console.error(error));
      });
    });
  };
  

  return { scheduleLayoutCheck, updateLayoutUi };
}
