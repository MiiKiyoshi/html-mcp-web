// The page being read, and the Pages tab, which lists the artifact's pages by their titles with the
// one being read marked, each going to its page on a click and taking a comment on it with
// + comment. Out of the slide show the page being read is the one the window shows most of, read
// again a frame after each scroll; in it, the one the show shows. This module keeps that page.
//
// createPages takes showing(), whether the slide show is on, and commentOn(anchor), which opens a
// new comment on a page. It gives current(), the page's number, or null; setCurrent(number);
// visible(), the page the window shows; render(), the tab drawn again; update(), the page read
// again from the window; schedule(), update() at the frame's next frame; and changed(listener),
// which hands in a function called when the page read from the window changes.

import { $, h, clear } from "../shared/dom.js";
import { deckPages, frameWindow, pageTitle } from "./deck-dom.js";
import { createListeners } from "../shared/listeners.js";

export function createPages({ showing, commentOn }) {
  const changed = createListeners();
  let currentPage = null;
  let pageFrame = null;

  function visible() {
    const pages = deckPages();
    if (showing()) {
      return pages.length === 0 ? null : currentPage || 1;
    }
    const viewportHeight = frameWindow().innerHeight;
    let visibleNumber = pages.length === 0 ? null : 1;
    let visibleHeight = -1;
    for (const [index, page] of pages.entries()) {
      const rect = page.getBoundingClientRect();
      const height = Math.max(0, Math.min(rect.bottom, viewportHeight) - Math.max(rect.top, 0));
      if (height > visibleHeight) {
        visibleHeight = height;
        visibleNumber = index + 1;
      }
    }
    return visibleNumber;
  }

  function jumpTo(number) {
    deckPages()[number - 1]?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function render() {
    const list = $("#pages-list");
    clear(list);
    for (const [index, page] of deckPages().entries()) {
      const number = index + 1;
      const title = pageTitle(page, index);
      list.appendChild(h("div", { class: `page-nav-row${currentPage === number ? " active" : ""}` },
        h("button", {
          type: "button",
          class: "page-nav-item",
          data: { page: String(number) },
          title: `Go to page ${number}`,
          onclick: () => jumpTo(number),
        },
        h("span", { class: "page-number", text: String(number) }),
        h("span", { class: "page-title", text: title })),
        h("button", { type: "button", class: "comment-page-btn", text: "+ comment",
                      onclick: () => commentOn({ kind: "page", number, title }) })));
    }
  }

  function update() {
    const number = visible();
    if (number === currentPage) return;
    currentPage = number;
    render();
    changed.tell();
  }

  function schedule() {
    const win = frameWindow();
    if (pageFrame !== null) win.cancelAnimationFrame(pageFrame);
    pageFrame = win.requestAnimationFrame(() => {
      pageFrame = null;
      update();
    });
  }

  return {
    current: () => currentPage,
    setCurrent(number) {
      currentPage = number;
    },
    visible,
    render,
    update,
    schedule,
    changed: changed.add,
  };
}
