// The artifact on screen as its frame holds it: the frame's window and document, its pages and
// a page's title, the page nearest a point, and the reader's place as a page and a point on it.
// Each function reads the frame on screen, #artifact-frame, when it is called, and none keeps
// anything: deck.js decides which frame that is.

import { $ } from "../shared/dom.js";

// A page of an artifact, as every template lays it out.
export const PAGE = "body > main.pages > section.page";

export function frameWindow() {
  return $("#artifact-frame").contentWindow;
}

export function frameDocument() {
  return $("#artifact-frame").contentDocument;
}

export function deckPages() {
  return Array.from(frameDocument().querySelectorAll(PAGE));
}

// What a page is called: its data-title, else its first heading, else its number.
export function pageTitle(page, index) {
  const heading = page.querySelector("h1, h2, h3");
  const title = page.dataset.title || heading?.textContent || "";
  return title.trim().replace(/\s+/g, " ") || `Page ${index + 1}`;
}

// The page under a point, or the nearest one when the point is in a gap.
export function pageNear(point) {
  const hit = frameDocument().elementFromPoint(point.x, point.y);
  const under = hit === null ? null : hit.closest(PAGE);
  if (under !== null) return under;
  let nearest = null;
  let distance = Infinity;
  for (const page of deckPages()) {
    const box = page.getBoundingClientRect();
    const away = Math.max(box.top - point.y, point.y - box.bottom, 0);
    if (away < distance) {
      distance = away;
      nearest = page;
    }
  }
  return nearest;
}

// The page at the top of the window, and the point on it there, in the page's own pixels.
export function readingPlace() {
  const page = pageNear({ x: frameDocument().documentElement.clientWidth / 2, y: 0 });
  if (page === null) return null;
  const box = page.getBoundingClientRect();
  return { page, y: -box.top / (box.height / page.offsetHeight) };
}

export function keepReadingPlace(place) {
  if (place === null) return;
  const win = frameWindow();
  const box = place.page.getBoundingClientRect();
  win.scrollTo(win.scrollX, win.scrollY + box.top + place.y * (box.height / place.page.offsetHeight));
}

// Safari draws a frame come back from underneath in part or not at all until it is scrolled,
// whatever the frame's visibility or layer meanwhile. So the scroll is done here: one pixel,
// and back at the next frame, which leaves the reader where they were. A scroll made before that
// frame is the reader's and stays: put back where the nudge started, it was undone, and on a
// machine slow to draw the reader who scrolled just after an edit was taken back up.
export function scrollToRepaint(win) {
  const { scrollX, scrollY } = win;
  win.scrollTo({ left: scrollX, top: scrollY + (scrollY > 0 ? -1 : 1), behavior: "instant" });
  const nudged = win.scrollY;
  requestAnimationFrame(() => {
    if (win.scrollX === scrollX && win.scrollY === nudged) win.scrollTo({ left: scrollX, top: scrollY, behavior: "instant" });
  });
}

// Each revision replaces the frame's history entry rather than adding one: setting src added an
// entry to the review page's history for every edit the agent made.
export function showInFrame(frame, url) {
  frame.contentWindow.location.replace(url);
}
