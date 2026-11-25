// The comments' marks on the pages: the words an open comment is on, drawn over in yellow with
// the comment's number beside them, a box drawn on a page, and a dashed mark where words a comment
// quotes stood before an edit took them away. The words of the source shown on the page by
// → Preview are marked in blue for a moment. The marks lie in a layer inside each page, in the
// page's own pixels, so they move and scale with it. A click on a number opens its comment, and a
// second click on the ringed one's hides the comments. This module keeps the words shown and the
// comments whose words the page no longer finds, which their cards mark stale.
//
// createPageMarks takes marked(), the open comments to mark; anchors (resolveAnchor(anchor),
// lastKnownPlace(anchor)); ringed(), the ringed comment's id; showComment(id), which opens a
// comment in the panel; and staleChanged(), told when the comments whose words are gone change.
// It gives render(); schedule(), render() at the frame's next frame; showRange(range), words shown
// for a moment; lost(id), whether a comment's words are gone; forget(), none of them gone, for
// another artifact; flash(id), a comment's marks flashed; layer(page), the layer of marks in a
// page; and frameOf(node), the page or script block a node is in, with its box and scale.

import { $, clear } from "../shared/dom.js";
import { setSidebarCollapsed } from "../shared/sidebar.js";
import { deckPages, frameDocument, frameWindow } from "./deck-dom.js";
import { selectionRects } from "./selection-rects.js";

export function createPageMarks({ marked, anchors, ringed, showComment, staleChanged }) {
  // Source words shown on the page by → Preview, marked for a moment.
  let shownRange = null;
  // The comments whose words the page no longer finds.
  const unattached = new Set();
  let renderFrame = null;

  function layer(page) {
    const doc = frameDocument();
    let style = doc.querySelector("#html-mcp-highlight-style");
    if (style === null) {
      style = doc.createElement("style");
      style.id = "html-mcp-highlight-style";
      style.textContent = `
      .html-mcp-highlight-layer { position: absolute; left: 0; top: 0; right: 0; bottom: 0; overflow: hidden; z-index: 2147483646; pointer-events: none; }
      .html-mcp-highlight-layer, .html-mcp-highlight-layer * { margin: 0; }
      .html-mcp-highlight { position: absolute; border-radius: 2px; background: rgba(246, 216, 74, .42); box-shadow: inset 0 -1px rgba(171, 139, 0, .28); }
      .html-mcp-highlight-badge { position: absolute; min-width: 18px; height: 18px; padding: 0 4px; border: 1px solid #8b7413; border-radius: 9px; color: #302900; background: #ffe77a; font: 11px/16px system-ui, sans-serif; pointer-events: auto; cursor: pointer; }
      .html-mcp-highlight.flash { background: rgba(255, 177, 60, .68); }
      .html-mcp-lost { position: absolute; border-radius: 2px; border: 1px dashed rgba(150, 122, 8, .8); background: rgba(246, 216, 74, .1); }
      .html-mcp-lost.flash { background: rgba(255, 177, 60, .4); }
      .html-mcp-highlight-badge.lost { border-style: dashed; color: #6d6650; background: #f6f1e2; }
      .html-mcp-area { position: absolute; box-sizing: border-box; border: 2px solid rgba(171, 139, 0, .8); border-radius: 2px; background: rgba(246, 216, 74, .16); }
      .html-mcp-area.flash { background: rgba(255, 177, 60, .4); }
      .html-mcp-shown { position: absolute; border-radius: 2px; background: rgba(181, 213, 255, .75); }
      html.html-mcp-area-mode, html.html-mcp-area-mode * { cursor: crosshair !important; user-select: none !important; -webkit-user-select: none !important; touch-action: none !important; }
    `;
      doc.head.appendChild(style);
    }
    // Keep the layer inside the page. It then inherits the page zoom, so both share one coordinate
    // system.
    let marks = page.querySelector(":scope > .html-mcp-highlight-layer");
    if (marks === null) {
      marks = doc.createElement("div");
      marks.className = "html-mcp-highlight-layer";
      page.appendChild(marks);
    }
    // A scrolling frame (speaker-script block) clips an inset layer to the visible box; size the
    // layer to the full scroll height so marks on scrolled-away lines survive.
    if (page.scrollHeight > page.clientHeight) {
      marks.style.bottom = "auto";
      marks.style.height = `${page.scrollHeight}px`;
    }
    return marks;
  }

  // Browsers disagree on whether the CSS zoom applied to section.page is reflected in
  // getClientRects(), so placing measured coordinates straight onto an unscaled layer misaligns
  // them when zoomed (observed in Safari). Measure the page rect through the same API to derive
  // the effective scale, then convert to page-relative coordinates.
  function frameOf(node) {
    const element = node.nodeType === 1 ? node : node.parentElement;
    // Speaker-script blocks (slides templates) live outside main.pages but take comments through
    // the same anchor path; each block is its own highlight frame. They scroll internally, so
    // content coordinates need the scroll offset added back.
    const page = element?.closest("body > main.pages > section.page, .script-block") ?? null;
    if (page === null) return null;
    const rect = page.getBoundingClientRect();
    const ratio = page.offsetWidth > 0 ? rect.width / page.offsetWidth : 1;
    return {
      page, rect, ratio: ratio > 0 ? ratio : 1,
      scrollTop: page.scrollTop || 0, scrollLeft: page.scrollLeft || 0,
    };
  }

  function render() {
    if (frameDocument() === null || frameDocument().body === null) return;
    const previousUnattached = new Set(unattached);
    for (const marks of frameDocument().querySelectorAll(".html-mcp-highlight-layer")) clear(marks);
    unattached.clear();
    let number = 0;
    // Both rect and page rect are viewport-relative, so scrolling cancels out in the difference.
    const local = (frame, rect) => ({
      left: (rect.left - frame.rect.left) / frame.ratio + frame.scrollLeft,
      top: (rect.top - frame.rect.top) / frame.ratio + frame.scrollTop,
      width: rect.width / frame.ratio,
      height: rect.height / frame.ratio,
    });
    const numberedBadge = (comment, count, box, lost) => {
      const badge = frameDocument().createElement("button");
      badge.type = "button";
      badge.className = lost ? "html-mcp-highlight-badge lost" : "html-mcp-highlight-badge";
      badge.textContent = String(count);
      badge.title = lost ? `${comment.thread[0].text}\n(the text this quotes is gone)` : comment.thread[0].text;
      Object.assign(badge.style, {
        left: `${Math.max(0, box.left - 21)}px`, top: `${Math.max(0, box.top - 1)}px`,
      });
      badge.addEventListener("click", () => {
        if (!$(".layout").classList.contains("sidebar-collapsed") && ringed() === comment.id) {
          setSidebarCollapsed(true);
          return;
        }
        showComment(comment.id).catch((error) => console.error(error));
      });
      return badge;
    };
    for (const comment of marked()) {
      if (comment.status !== "open" || !["text", "area"].includes(comment.anchor.kind)) continue;
      number += 1;
      if (comment.anchor.kind === "area") {
        // The box is in page pixels and the layer lies inside the page, so it is drawn as stored
        // at every zoom.
        const page = deckPages()[comment.anchor.number - 1];
        if (page === undefined) continue;
        const [x1, y1, x2, y2] = comment.anchor.bbox;
        const box = { left: x1, top: y1, width: x2 - x1, height: y2 - y1 };
        const marks = layer(page);
        const mark = frameDocument().createElement("div");
        mark.className = "html-mcp-area";
        mark.dataset.commentId = comment.id;
        Object.assign(mark.style, {
          left: `${box.left}px`, top: `${box.top}px`, width: `${box.width}px`, height: `${box.height}px`,
        });
        marks.appendChild(mark);
        marks.appendChild(numberedBadge(comment, number, box, false));
        continue;
      }
      const range = anchors.resolveAnchor(comment.anchor);
      const frame = range === null ? null : frameOf(range.startContainer);
      if (frame === null) {
        unattached.add(comment.id);
        // The quoted text is gone, so there is nothing to draw over. What the page still has is
        // the place the comment was written at, and a dashed mark stands there: it says the
        // comment was about this much of the page and no closer.
        const place = anchors.lastKnownPlace(comment.anchor);
        const placeFrame = place === null ? null : frameOf(place);
        if (placeFrame === null) continue;
        const box = local(placeFrame, place.getBoundingClientRect());
        const marks = layer(placeFrame.page);
        const mark = frameDocument().createElement("div");
        mark.className = "html-mcp-lost";
        mark.dataset.commentId = comment.id;
        Object.assign(mark.style, {
          left: `${box.left}px`, top: `${box.top}px`, width: `${box.width}px`, height: `${box.height}px`,
        });
        marks.appendChild(mark);
        marks.appendChild(numberedBadge(comment, number, box, true));
        continue;
      }
      const marks = layer(frame.page);
      const rects = selectionRects(range);
      for (const rect of rects) {
        const box = local(frame, rect);
        const mark = frameDocument().createElement("div");
        mark.className = "html-mcp-highlight";
        mark.dataset.commentId = comment.id;
        Object.assign(mark.style, {
          left: `${box.left}px`, top: `${box.top}px`, width: `${box.width}px`, height: `${box.height}px`,
        });
        marks.appendChild(mark);
      }
      const firstRect = rects[0];
      if (firstRect !== undefined) marks.appendChild(numberedBadge(comment, number, local(frame, firstRect), false));
    }
    const shown = shownRange;
    const shownFrame = shown === null ? null : frameOf(shown.startContainer);
    if (shownFrame !== null) {
      const marks = layer(shownFrame.page);
      for (const rect of shown.collapsed ? [shown.getBoundingClientRect()] : selectionRects(shown)) {
        const box = local(shownFrame, rect);
        const mark = frameDocument().createElement("div");
        // The editor's selection blue, apart from the comments' yellow.
        mark.className = "html-mcp-shown";
        Object.assign(mark.style, {
          left: `${box.left}px`, top: `${box.top}px`, width: `${Math.max(2, box.width)}px`, height: `${box.height}px`,
        });
        marks.appendChild(mark);
      }
    }
    const attachmentChanged = previousUnattached.size !== unattached.size
      || Array.from(previousUnattached).some((commentId) => !unattached.has(commentId));
    if (attachmentChanged) staleChanged();
  }

  function schedule() {
    if (renderFrame !== null) frameWindow().cancelAnimationFrame(renderFrame);
    renderFrame = frameWindow().requestAnimationFrame(() => {
      renderFrame = null;
      render();
    });
  }

  return {
    render,
    schedule,
    // Drawn with the comments' marks, so a redraw as the Preview takes its width keeps it.
    showRange(range) {
      shownRange = range;
      schedule();
      setTimeout(() => {
        if (shownRange !== range) return;
        shownRange = null;
        schedule();
      }, 2000);
    },
    lost: (id) => unattached.has(id),
    forget() {
      unattached.clear();
    },
    flash(id) {
      setTimeout(() => {
        const marks = frameDocument().querySelectorAll(`[data-comment-id="${CSS.escape(id)}"]`);
        marks.forEach((mark) => mark.classList.add("flash"));
        setTimeout(() => marks.forEach((mark) => mark.classList.remove("flash")), 1000);
      }, 350);
    },
    layer,
    frameOf,
  };
}
