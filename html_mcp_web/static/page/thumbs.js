// Slide previews: a second frame of the same artifact, drawn small in a column at the pane's left,
// so a preview is the page itself. A click goes to that page, the arrow and page keys step the
// deck from the column, and the page being read is marked and kept in view. The column follows
// each revision as the deck does. The first button in the bar shows or hides it, and the browser
// keeps the choice. This module keeps the column's frames and how far it is carried.
//
// createThumbs takes project (alias(), revision(), url()); pages (current(), setCurrent(number)),
// the page being read; and searchKey(event), the search's key in the column. It gives open(on),
// the column shown or hidden; restore(), shown as the reader left it; follow(), the column brought to the artifact shown; mark(), the page
// being read marked and kept in view; and attach().

import { $ } from "../shared/dom.js";
import { PAGE, deckPages, scrollToRepaint, showInFrame } from "./deck-dom.js";
import { changePages, updateFrame } from "./frame-update.js";

// How many previews stay wholly in sight above and below the marked one. Counted in previews
// rather than as a share of the column, so a short screen and a tall one both show the same
// neighbours.
const THUMB_NEIGHBOURS = 2;

// What the browser keeps the choice under.
const KEPT = "htmlMcpThumbsOpen";

const isOpen = () => $("#artifact-pane").classList.contains("thumbs-open");

export function createThumbs({ project, pages, searchKey }) {
  // The column follows the page being read by moving its previews, not by scrolling. Safari did
  // not draw a frame's scroll set from script while the deck was moving, so in traces the column's
  // scroll position kept up (y=375>252) while the column stayed drawn pages behind and the marked
  // preview slid off its top. A transform is drawn with the frame's next paint. The distance moved
  // is handed to the column's own scroll as soon as the reader turns to the column, so it scrolls
  // on from what is shown.
  let thumbShift = 0;
  let thumbsBehind = null;
  // A run of presses counts from where the last one went: the deck's own page is read from its
  // scroll a frame later, and a quick second press read it unchanged.
  let thumbKey = null;

  function open(on) {
    $("#artifact-pane").classList.toggle("thumbs-open", on);
    $("#thumbs-btn").classList.toggle("active", on);
    $("#thumbs-btn").setAttribute("aria-pressed", String(on));
    localStorage.setItem(KEPT, on ? "1" : "0");
    if (on) load();
  }

  function load() {
    const frame = $("#thumbs-frame");
    const wanted = `${project.alias()}@${project.revision()}`;
    if (frame.dataset.loaded === wanted) {
      mark();
      return;
    }
    // An alias may hold an @ itself: the revision is what follows the last one.
    const loaded = frame.dataset.loaded;
    const sameArtifact = loaded !== undefined && loaded.slice(0, loaded.lastIndexOf("@")) === project.alias();
    frame.dataset.loaded = wanted;
    const url = project.url();
    const shown = frame.contentDocument?.URL;
    if (shown === undefined || shown === "about:blank") {
      showInFrame(frame, url);
      return;
    }
    // The previews of the artifact they show change as the deck does, see frame-update.js.
    const canPatch = () => thumbsBehind === null && frame.id === "thumbs-frame"
      && frame.contentDocument?.readyState === "complete";
    if (sameArtifact && canPatch()) {
      updateFrame(frame, url, canPatch, (doc, previous, next) => {
        if (changePages(doc, previous, next) === null) return false;
        mark();
        return true;
      }, () => loadBehind(url));
      return;
    }
    loadBehind(url);
  }

  // As with the deck, a column already showing previews keeps them in view while the next revision
  // loads whole under it: loaded in place, the column went blank on every edit. And as with the
  // deck, a frame still loading keeps the latest address for when its load ends.
  function loadBehind(url) {
    const frame = $("#thumbs-frame");
    if (thumbsBehind === null) {
      thumbsBehind = document.createElement("iframe");
      thumbsBehind.title = frame.title;
      thumbsBehind.tabIndex = -1;
      thumbsBehind.toggleAttribute("inert", true);
      thumbsBehind.src = url;
      frame.after(thumbsBehind);
      const next = thumbsBehind;
      next.addEventListener("load", () => {
        if (next.contentDocument !== null && next.contentDocument.URL !== "about:blank") reveal(next);
      });
    }
    thumbsBehind.dataset.wanted = new URL(url, location.href).href;
  }

  // The loaded previews take the column at the scroll the old ones had, set up as any load is, and
  // the old frame covers them until two frames have been drawn.
  async function reveal(next) {
    if (next.contentDocument.URL !== next.dataset.wanted) {
      showInFrame(next, next.dataset.wanted);
      return;
    }
    thumbsBehind = null;
    const old = $("#thumbs-frame");
    const at = old.contentWindow.scrollY + thumbShift;
    old.removeAttribute("id");
    old.toggleAttribute("inert", true);
    old.classList.add("covering");
    next.id = "thumbs-frame";
    next.dataset.loaded = old.dataset.loaded;
    next.toggleAttribute("inert", false);
    // Scaled first: the old column's place, as drawn, means the same previews only at the scale
    // they are drawn at. The column then stays where the reader left it, as drawn, so an edit does
    // not pull a column the reader scrolled back to the current page.
    install();
    shift(0);
    next.contentWindow.scrollTo(0, at);
    const win = next.contentWindow;
    await next.contentDocument.fonts.ready;
    await new Promise((done) => win.requestAnimationFrame(() => win.requestAnimationFrame(done)));
    old.remove();
    // As with the deck: Safari left the column empty until the reader clicked in it, which scrolls
    // it, and then drew the previews at once.
    scrollToRepaint(win);
  }

  function thumbPages() {
    const doc = $("#thumbs-frame").contentDocument;
    return doc === null ? [] : Array.from(doc.querySelectorAll(PAGE));
  }

  // The previews take the column's width, less a margin: measured, since the column can be laid
  // out after the frame loads.
  function scale() {
    const doc = $("#thumbs-frame").contentDocument;
    const first = thumbPages()[0];
    if (doc === null || first === undefined || doc.documentElement.clientWidth <= 24) return;
    doc.documentElement.style.setProperty(
      "--html-mcp-page-scale", String((doc.documentElement.clientWidth - 24) / first.offsetWidth));
  }

  function install() {
    const doc = $("#thumbs-frame").contentDocument;
    if (doc === null || thumbPages().length === 0) return;
    doc.documentElement.dataset.htmlMcpScriptsHidden = "";
    scale();
    doc.defaultView.addEventListener("resize", scale);
    const style = doc.createElement("style");
    style.textContent = `
    body > main.pages > section.page { cursor: pointer; }
    body > main.pages > section.page * { pointer-events: none !important; }
    body > main.pages > section.page.html-mcp-thumb-current {
      outline: calc(3px / var(--html-mcp-page-scale)) solid #e0955a !important;
    }`;
    doc.head.appendChild(style);
    // A click marks its preview at once and shows that page. Scrolled there smoothly, the deck
    // passed every page between, and the mark followed the deck down the column through each.
    doc.addEventListener("click", (event) => {
      const page = event.target.closest?.(PAGE);
      if (!page) return;
      const number = thumbPages().indexOf(page) + 1;
      pages.setCurrent(number);
      mark();
      deckPages()[number - 1]?.scrollIntoView({ behavior: "instant", block: "start" });
    });
    doc.addEventListener("keydown", handleKey);
    doc.addEventListener("keydown", searchKey, true);
    // A new document starts unmoved. Not passive, so the browser waits for the hand-over before it
    // scrolls the column on a wheel or a touch.
    thumbShift = 0;
    for (const kind of ["wheel", "touchstart", "pointerdown", "keydown"]) {
      doc.addEventListener(kind, settleShift, { capture: true, passive: false });
    }
    // Under ?trace, every scroll the column takes, so one the viewer did not ask for shows as a
    // line of its own beside the thumb lines.
    doc.defaultView.addEventListener("scroll", () => {
      window.htmlMcpTrace?.(`thumb-scroll y=${Math.round(doc.defaultView.scrollY)}`);
    }, { passive: true });
    mark();
  }

  // With the column focused, the arrow and page keys step the deck a page at a time, and Home and
  // End go to its ends.
  function handleKey(event) {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    const steps = { ArrowUp: -1, ArrowLeft: -1, PageUp: -1, ArrowDown: 1, ArrowRight: 1, PageDown: 1 };
    const count = deckPages().length;
    if (count === 0) return;
    let page;
    if (event.key === "Home") page = 1;
    else if (event.key === "End") page = count;
    else if (event.key in steps) {
      const recent = thumbKey !== null && performance.now() - thumbKey.time < 500;
      page = Math.min(Math.max((recent ? thumbKey.page : pages.current() || 1) + steps[event.key], 1), count);
    } else return;
    event.preventDefault();
    thumbKey = { page, time: performance.now() };
    deckPages()[page - 1].scrollIntoView({ behavior: "instant", block: "start" });
  }

  function shift(distance) {
    thumbShift = distance;
    const holder = $("#thumbs-frame").contentDocument?.querySelector("body > main.pages");
    if (holder) holder.style.transform = distance === 0 ? "" : `translateY(${-distance}px)`;
  }

  function settleShift() {
    const win = $("#thumbs-frame").contentWindow;
    if (thumbShift === 0 || win === null) return;
    const shown = win.scrollY + thumbShift;
    shift(0);
    win.scrollTo(0, shown);
    window.htmlMcpTrace?.(`thumb-settle y=${Math.round(shown)}`);
  }

  function mark() {
    if (!isOpen()) return;
    const current = pages.current();
    const previews = thumbPages();
    for (const [index, page] of previews.entries()) {
      page.classList.toggle("html-mcp-thumb-current", index + 1 === current);
    }
    // The marked preview stays a margin inside the column, not at its edge: scrolled to the
    // nearest edge, it sat at the top whenever the deck was read upward, and the previews of the
    // pages just above it were out of sight.
    const marked = previews[current - 1];
    const win = $("#thumbs-frame").contentWindow;
    if (marked === undefined || win === null) {
      window.htmlMcpTrace?.(`thumb p=${current}/${previews.length} not in the column`);
      return;
    }
    const box = marked.getBoundingClientRect();
    // One preview's step down the column, gap included. A column too short for the neighbours on
    // both sides keeps the marked preview in its middle instead.
    const step = previews.length > 1
      ? previews[1].getBoundingClientRect().top - previews[0].getBoundingClientRect().top : box.height;
    const margin = Math.min(THUMB_NEIGHBOURS * step, (win.innerHeight - box.height) / 2);
    // Where the column is drawn from, and how far it may go: the last preview's bottom, plus the
    // body's padding, ends it. Boxes are read as drawn, so they include the shift.
    const shown = win.scrollY + thumbShift;
    const end = Math.max(0, previews[previews.length - 1].getBoundingClientRect().bottom + shown + 8 - win.innerHeight);
    let wanted = shown;
    if (box.top < margin) wanted = shown + box.top - margin;
    else if (box.bottom > win.innerHeight - margin) wanted = shown + box.bottom - (win.innerHeight - margin);
    wanted = Math.min(Math.max(wanted, 0), end);
    if (wanted !== shown) shift(wanted - win.scrollY);
    // Under ?trace, what the column did for this page: the preview's box before the move, the
    // margin kept, and where the column was drawn from before and after, with the column's own
    // scroll and the frame's state.
    window.htmlMcpTrace?.(`thumb p=${current}/${previews.length} box=${Math.round(box.top)},${Math.round(box.bottom)}`
      + ` in=${win.innerHeight} m=${Math.round(margin)} y=${Math.round(shown)}>${Math.round(wanted)} s=${Math.round(win.scrollY)}`
      + ` ${win.document.readyState} sc=${win.document.documentElement.style.getPropertyValue("--html-mcp-page-scale") || "-"}`);
  }

  return {
    open,
    // The column as the reader last left it.
    restore() {
      open(localStorage.getItem(KEPT) === "1");
    },
    follow() {
      if (isOpen()) load();
    },
    mark,
    attach() {
      $("#thumbs-btn").addEventListener("click", () => open(!isOpen()));
      $("#thumbs-frame").addEventListener("load", install);
    },
  };
}
