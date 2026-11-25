// The frames the artifacts are shown in, and which one is on screen. Each artifact the reader has
// opened keeps a frame of its own, with its document: a tab shows its own frame and hides the
// others. Loading the next artifact into the one frame there was fetched and parsed the whole
// deck again, fonts and all, ran the layout check over it again, and started it at the top; a
// switch took seconds and lost the place. A revision of the artifact on screen changes the pages
// that differ (frame-update.js), or loads whole in a frame under the one on screen, which covers
// it until the new document is set up at the reader's place. This module keeps the frames, the
// revision the frame on screen shows, and the place each artifact's next document opens at.
//
// createDeck takes project (alias(), revision(), url()); showing(), whether the slide show is
// on, which keeps its own page; and pagesChanged(), which holds the show's page within the pages
// an edit leaves. It gives open(alias), the artifact's frame made ready to show; shows(revision),
// whether the frame on screen shows that revision; showOrLoad(); load(preserveView); forget(),
// the frame on screen counted as showing nothing; pendingView(alias), the place an artifact's
// next document opens at, as { page, y }, or undefined; and what happens to the frame on screen,
// each of which hands in a function called when it does: following(listener), as it is brought
// to the artifact shown; revising(listener), as it goes to another revision; loaded(listener),
// with the document and the window it has loaded, before the place an edit left the reader at
// is put back in it; shown(listener), as a frame set up already is shown again or changed in
// place; and changed(listener), with the document and the images of the pages put in, as its
// pages change in place, before the reader's place on them is put back.

import { $ } from "../shared/dom.js";
import { PAGE, deckPages, frameDocument, frameWindow, keepReadingPlace, readingPlace, scrollToRepaint, showInFrame } from "./deck-dom.js";
import { changePages, updateFrame } from "./frame-update.js";
import { createListeners } from "../shared/listeners.js";

export function createDeck({ project, showing, pagesChanged }) {
  const following = createListeners();
  const revising = createListeners();
  const loaded = createListeners();
  const shown = createListeners();
  const changed = createListeners();
  // One frame per artifact, by alias, and the frame each artifact's next revision is loading in,
  // under the one on screen.
  const frames = {};
  const framesBehind = {};
  // The place each artifact's next document opens at, by alias, kept until it is put back: the
  // page at the top of the window, by its index, and how far into it.
  const pendingViews = {};
  // The revision the frame on screen shows, or null.
  let loadedRevision = null;

  // The frame that holds an artifact. The frame the page starts with is taken by the first
  // artifact shown; every artifact after that gets a frame of its own. The active one carries the
  // id everything else looks the frame up by.
  function frameFor(alias) {
    let frame = frames[alias];
    if (frame !== undefined) return frame;
    const pane = $("#artifact-pane");
    const spare = pane.querySelector(".artifact-frame:not([data-artifact])");
    frame = spare ?? document.createElement("iframe");
    if (spare === null) {
      frame.className = "artifact-frame";
      frame.title = "Agent-generated HTML artifact";
      frame.tabIndex = -1;
      const last = Array.from(pane.querySelectorAll(".artifact-frame")).pop();
      last.after(frame);
    }
    frame.dataset.artifact = alias;
    frame.addEventListener("load", () => setUp(frame));
    frames[alias] = frame;
    return frame;
  }

  // The active frame is raised over the others, which stay painted underneath and are inert
  // there: out of the tab order, out of find-in-page, silent to a screen reader.
  function showFrame(frame) {
    for (const other of Object.values(frames)) {
      const active = other === frame;
      other.classList.toggle("active", active);
      other.toggleAttribute("inert", !active);
      if (active) other.id = "artifact-frame";
      else other.removeAttribute("id");
    }
  }

  // A frame shown again is already loaded: what the switch has to do is set the page up for it.
  function showLoaded(frame) {
    showFrame(frame);
    shown.tell();
  }

  // A document loaded in the frame on screen. A frame that finished loading after the reader had
  // moved to another tab is not the one the page is set up for: it forgets what it shows, so
  // coming back loads it again and sets the page up then.
  function setUp(frame) {
    if (frame.id !== "artifact-frame") {
      delete frame.dataset.revision;
      return;
    }
    const doc = frame.contentDocument;
    const win = frameWindow();
    // The document says which revision it is, so a check knows whether it is looking at the one
    // it would report: a check scheduled on the document before an edit ran after the new
    // revision was announced and reported that document's result under it.
    doc.documentElement.dataset.htmlMcpRevision = frame.dataset.revision;
    loaded.tell(doc, win);
    putBack(doc, win);
  }

  // The place an edit left the reader at, put back as a page and a point on it, not as a scroll
  // offset, and again once the fonts are in: the new document is set first in a fallback face,
  // its script blocks at other heights, and the offset the reader left at fell two pages further
  // on by then.
  function putBack(doc, win) {
    const alias = project.alias();
    const view = pendingViews[alias];
    if (view === undefined) return;
    const put = () => {
      const page = deckPages()[view.page];
      if (frameDocument() === doc && page !== undefined) keepReadingPlace({ page, y: view.y });
    };
    win.requestAnimationFrame(put);
    doc.fonts.ready.then(() => {
      if (pendingViews[alias] !== view) return;
      put();
      delete pendingViews[alias];
    });
  }

  function load(preserveView) {
    const iframe = frameFor(project.alias());
    showFrame(iframe);
    following.tell();
    if (loadedRevision === project.revision()) return;
    revising.tell();
    loadedRevision = project.revision();
    const page = iframe.contentDocument?.URL;
    if (page !== undefined && page !== "about:blank") {
      updateDeck(iframe, preserveView);
      return;
    }
    keepView(iframe, preserveView);
    iframe.dataset.revision = String(project.revision());
    delete iframe.dataset.settled;
    showInFrame(iframe, project.url());
  }

  // A view not yet put back is kept. A hidden tab runs no animation frames, and a second edit
  // made while the reader was in another tab read the top of the document loaded for the first,
  // which sent them back to page 1. The slide show keeps its own page.
  function keepView(iframe, preserveView) {
    const alias = project.alias();
    if (!preserveView || showing() || pendingViews[alias] !== undefined) return;
    if (iframe.id !== "artifact-frame" || iframe.contentDocument?.body == null) return;
    const place = readingPlace();
    if (place !== null) pendingViews[alias] = { page: deckPages().indexOf(place.page), y: place.y };
  }

  // A deck on screen takes a revision by changing the pages that differ, at the reader's place,
  // and is set up as a deck shown again is.
  function updateDeck(frame, preserveView) {
    const alias = frame.dataset.artifact;
    const revision = project.revision();
    const whole = () => {
      // The reader has gone to another artifact meanwhile: the frame forgets what it shows, and
      // is brought up to date when they come back.
      if (project.alias() !== alias) {
        delete frame.dataset.revision;
        return;
      }
      keepView(frame, preserveView);
      loadBehind(frame, project.url());
    };
    // Only a document this page set up takes pages: a browser may put back the address a frame
    // last showed when the review page is reloaded, and a document loaded that way was never set
    // up, so its pages changed and the reader's place was never put back.
    const canPatch = () => framesBehind[alias] === undefined && frame.contentDocument?.readyState === "complete"
      && frame.contentDocument.documentElement.dataset.htmlMcpRevision !== undefined;
    if (!canPatch()) {
      whole();
      return;
    }
    updateFrame(frame, project.url(), canPatch, (doc, before, next) => {
      const active = frame.id === "artifact-frame";
      const place = active && !showing() ? readingPlace() : null;
      const change = changePages(doc, before, next);
      if (change === null) return false;
      frame.dataset.revision = String(revision);
      delete frame.dataset.settled;
      doc.documentElement.dataset.htmlMcpRevision = String(revision);
      // A frame of an artifact the reader has left is set up when they come back to it.
      if (!active) return true;
      if (showing()) pagesChanged();
      changed.tell(doc, change.added.flatMap((node) => Array.from(node.querySelectorAll("img"))));
      // The page the reader was on, or the page that took its place.
      const page = place === null ? undefined
        : place.page.isConnected ? place.page : change.added[change.removed.indexOf(place.page)];
      if (page?.matches(PAGE)) keepReadingPlace({ page, y: place.y });
      showLoaded(frame);
      return true;
    }, whole);
  }

  // A revision of a deck already on screen loads into a frame of its own under it, and the frame
  // on screen stays in view until the new document is set up at the reader's place. Loaded into
  // the frame on screen, the deck went blank while the document loaded and then showed its first
  // page until the scroll was put back, on every edit the agent made. The new frame is given its
  // address as it is made, and a frame still loading is not sent elsewhere: WebKit dropped a
  // second address given to a new frame before its first had loaded, and the deck stayed on the
  // earlier revision under the later one's number while agents' edits came in bursts. The latest
  // address waits on the frame for its load to end.
  function loadBehind(onScreen, url) {
    const alias = onScreen.dataset.artifact;
    let next = framesBehind[alias];
    if (next === undefined) {
      next = document.createElement("iframe");
      next.className = "artifact-frame";
      next.title = onScreen.title;
      next.tabIndex = -1;
      next.toggleAttribute("inert", true);
      next.dataset.artifact = alias;
      next.src = url;
      onScreen.after(next);
      const frame = next;
      // The swap runs first, so the setup that follows finds this frame on screen.
      frame.addEventListener("load", () => { if (frame.contentDocument?.URL !== "about:blank") revealBehind(frame); });
      frame.addEventListener("load", () => { if (frame.id === "artifact-frame") setUp(frame); });
      framesBehind[alias] = next;
    }
    next.dataset.revision = String(project.revision());
    next.dataset.wanted = new URL(url, location.href).href;
    delete next.dataset.settled;
  }

  // The new frame takes the place of the one on screen at once, so the page is set up on it, while
  // the old one covers it until the deck's fonts are in and two frames have been drawn at the
  // reader's place. A frame for a tab the reader has left replaces the old one unseen, and is set
  // up when the reader comes back.
  async function revealBehind(next) {
    if (next.contentDocument.URL !== next.dataset.wanted) {
      showInFrame(next, next.dataset.wanted);
      return;
    }
    const alias = next.dataset.artifact;
    delete framesBehind[alias];
    const old = frames[alias];
    frames[alias] = next;
    if (project.alias() !== alias) {
      old.remove();
      delete next.dataset.revision;
      return;
    }
    old.classList.remove("active");
    old.removeAttribute("id");
    old.toggleAttribute("inert", true);
    old.classList.add("covering");
    showFrame(next);
    const win = next.contentWindow;
    await next.contentDocument.fonts.ready;
    await new Promise((done) => win.requestAnimationFrame(() => win.requestAnimationFrame(done)));
    old.remove();
    // Safari draws a frame come back from underneath as it last drew it, or not at all, until it
    // is scrolled: the deck showed the new document's first page, drawn while it loaded at the
    // top, over the reader's place it had been scrolled to beneath the old one.
    if (next.id === "artifact-frame") scrollToRepaint(win);
  }

  return {
    // The frame says what revision it shows; the artifact says which is current.
    open(alias) {
      const frame = frameFor(alias);
      loadedRevision = frame.dataset.revision === undefined ? null : Number(frame.dataset.revision);
    },
    shows: (revision) => loadedRevision === revision,
    showOrLoad() {
      // A deck rebuilt while the reader was on another tab opens where they left it, as an edit
      // does while it is shown: loading it from the top sent them back to page 1.
      if (loadedRevision !== project.revision()) {
        load(true);
        return;
      }
      showLoaded(frameFor(project.alias()));
      following.tell();
    },
    load,
    forget() {
      loadedRevision = null;
    },
    pendingView: (alias) => pendingViews[alias],
    following: following.add,
    revising: revising.add,
    loaded: loaded.add,
    shown: shown.add,
    changed: changed.add,
  };
}
