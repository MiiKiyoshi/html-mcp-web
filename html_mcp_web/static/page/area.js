// The box tool. While its button is down, a drag on a page draws a box instead of selecting text,
// and the comment written for it opens when the drag ends. The box is kept in the page's own
// pixels. This module keeps whether the tool is on.
//
// createArea takes layer(page), the layer of marks in a page, which the box is drawn in while it
// is dragged; and commentOn(anchor), which opens a new comment on the box. It gives install(doc),
// the drag in a document, and attach(), the button.

import { $ } from "../shared/dom.js";
import { deckPages, frameDocument, frameWindow, pageTitle } from "./deck-dom.js";

export function createArea({ layer, commentOn }) {
  let areaMode = false;

  function set(on) {
    areaMode = on;
    const button = $("#area-btn");
    button.classList.toggle("active", on);
    button.setAttribute("aria-pressed", String(on));
    frameDocument()?.documentElement.classList.toggle("html-mcp-area-mode", on);
    if (on) frameWindow()?.getSelection()?.removeAllRanges();
  }

  function install(doc) {
    doc.documentElement.classList.toggle("html-mcp-area-mode", areaMode);
    let drawing = null;
    const pointOn = (page, event) => {
      const rect = page.getBoundingClientRect();
      const ratio = page.offsetWidth > 0 ? rect.width / page.offsetWidth : 1;
      return {
        x: Math.min(page.offsetWidth, Math.max(0, (event.clientX - rect.left) / ratio)),
        y: Math.min(page.offsetHeight, Math.max(0, (event.clientY - rect.top) / ratio)),
      };
    };
    const boxOf = ({ start, end }) => ({
      left: Math.min(start.x, end.x), top: Math.min(start.y, end.y),
      width: Math.abs(end.x - start.x), height: Math.abs(end.y - start.y),
    });
    doc.addEventListener("pointerdown", (event) => {
      if (!areaMode || event.button !== 0) return;
      const page = event.target.closest?.("body > main.pages > section.page");
      if (!page) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const start = pointOn(page, event);
      const mark = doc.createElement("div");
      mark.className = "html-mcp-area";
      layer(page).appendChild(mark);
      drawing = { page, start, end: start, mark, pointer: event.pointerId };
      event.target.setPointerCapture?.(event.pointerId);
    }, true);
    doc.addEventListener("pointermove", (event) => {
      if (drawing === null || event.pointerId !== drawing.pointer) return;
      event.preventDefault();
      drawing.end = pointOn(drawing.page, event);
      const box = boxOf(drawing);
      Object.assign(drawing.mark.style, {
        left: `${box.left}px`, top: `${box.top}px`, width: `${box.width}px`, height: `${box.height}px`,
      });
    }, true);
    const finish = (event) => {
      if (drawing === null || event.pointerId !== drawing.pointer) return;
      const done = drawing;
      drawing = null;
      done.mark.remove();
      event.stopImmediatePropagation();
      const box = boxOf(done);
      // A click, not a box.
      if (event.type !== "pointerup" || box.width < 4 || box.height < 4) return;
      const index = deckPages().indexOf(done.page);
      set(false);
      commentOn({
        kind: "area",
        number: index + 1,
        title: pageTitle(done.page, index),
        bbox: [box.left, box.top, box.left + box.width, box.top + box.height].map((value) => Math.round(value)),
      });
    };
    doc.addEventListener("pointerup", finish, true);
    doc.addEventListener("pointercancel", finish, true);
  }

  return {
    install,
    attach() {
      $("#area-btn").addEventListener("click", () => set(!areaMode));
    },
  };
}
