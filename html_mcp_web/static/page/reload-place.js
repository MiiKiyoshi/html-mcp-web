// The reader's place kept through a reload. A reload starts the deck again from its first page:
// the deck's frame is filled by script, so the browser has no scroll of its own to put back.
// Readers were sent back to page 1 by their own refresh and by the reload for newer viewer code.
// The page at the top of the window and the point on it go through any reload in this tab's
// session storage. In the full-screen slide show the page being shown is kept, from its top. They
// are saved when the tab is hidden as well as when it is left: a browser that discards a
// background tab to free memory loads it again on return, and the discarded page ran no pagehide.
// While an edit's view waits to be put back, the place saved is that view's: the deck on screen
// may be the new document still at its top. Skipped instead, a reload for newer viewer code that
// came while an edit was loading saved nothing, and the deck opened on page 1.
//
// createReloadPlace takes alias(), the artifact shown; heldPage(), the page the slide show shows
// or ended on, or null; and pendingView(alias), the place the artifact's next document opens at.
// It gives remember(); putBack(win), the place kept for the artifact shown put back, once, in the
// window of a document just loaded, unless an edit's view waits to be put back there instead;
// and attach(), which remembers it as the tab is hidden or left.

import { deckPages, frameDocument, keepReadingPlace, readingPlace } from "./deck-dom.js";

const KEPT = "htmlMcpReadingPlace";

export function createReloadPlace({ alias, heldPage, pendingView }) {
  function remember() {
    try {
      if (alias() === null || frameDocument() === null) return;
      const held = heldPage();
      const pending = pendingView(alias());
      if (held === null && pending !== undefined) {
        sessionStorage.setItem(KEPT, JSON.stringify({ artifact: alias(), page: pending.page, y: pending.y }));
        return;
      }
      const shown = held === null ? undefined : deckPages()[held - 1];
      const place = held === null ? readingPlace() : (shown === undefined ? null : { page: shown, y: 0 });
      if (place === null) return;
      sessionStorage.setItem(KEPT, JSON.stringify(
        { artifact: alias(), page: deckPages().indexOf(place.page), y: place.y }));
    } catch {
      // Storage refused, as a private window may: the reload starts at the top as before.
    }
  }

  // The place kept for the artifact shown, taken once, or null.
  function recalled() {
    let saved = null;
    try {
      saved = JSON.parse(sessionStorage.getItem(KEPT) ?? "null");
      sessionStorage.removeItem(KEPT);
    } catch {
      return null;
    }
    if (saved === null || saved.artifact !== alias()) return null;
    const page = deckPages()[saved.page];
    return page === undefined ? null : { page, y: saved.y };
  }

  return {
    remember,
    putBack(win) {
      if (pendingView(alias()) !== undefined) return;
      const place = recalled();
      if (place !== null) win.requestAnimationFrame(() => keepReadingPlace(place));
    },
    attach() {
      window.addEventListener("pagehide", remember);
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "hidden") remember();
      });
    },
  };
}
