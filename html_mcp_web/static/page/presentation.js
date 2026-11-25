// Full screen, and the slide show a deck becomes in it: one page at a time, fitted to the screen,
// stepped by the keys, a click, a swipe, the wheel and the controls along its foot. Where a
// browser gives a page no full screen, as Safari on an iPhone does, the pane is laid over the
// whole page instead. This module keeps whether the show is on, the page held for a reload as the
// show ends, and the wheel's and the finger's run.
//
// createPresentation takes pages (current(), setCurrent(number), visible(), render()), the page
// being read; fit(), which fits the pages to the pane; hideSelection(); scheduleLayoutCheck();
// layout(), the shown artifact's layout; and entering(), told as the reader asks for full screen.
// It gives showing(), whether the show is on; heldPage(), the page the show shows, or the one it
// ended on until the deck is scrolled back to it, or null; inFullscreen(); mark(doc), a document told whether it is
// in full screen; install(doc), the show's keys, clicks, swipes and wheel in a document; resume(),
// the show taken up again in a document loaded in full screen; markCurrent(), the page being read
// marked as the shown one; pagesChanged(), the page held within the pages an edit left; and
// attach(), the controls, the keys and the full screen's changes.

import { $ } from "../shared/dom.js";
import { deckPages, frameDocument, frameWindow } from "./deck-dom.js";

export function createPresentation({ pages, fit, hideSelection, scheduleLayoutCheck, layout, entering }) {
  let slideShow = false;
  let leftSlideShowAt = null;
  let pointer = null;
  let wheelEvents = [];
  let lastWheelStep = 0;
  let suppressClick = false;

  function updateControls() {
    const count = deckPages().length;
    const number = count === 0 ? 0 : Math.min(Math.max(pages.current() || 1, 1), count);
    $("#presentation-page").textContent = `${number} / ${count}`;
    $("#presentation-prev-btn").disabled = number <= 1;
    $("#presentation-next-btn").disabled = number >= count;
  }

  function markCurrent() {
    for (const [index, page] of deckPages().entries()) {
      page.classList.toggle("html-mcp-current-page", index + 1 === pages.current());
    }
    updateControls();
  }

  function setPage(number) {
    const count = deckPages().length;
    if (count === 0) {
      pages.setCurrent(null);
      updateControls();
      return false;
    }
    const previous = pages.current();
    pages.setCurrent(Math.min(Math.max(number, 1), count));
    markCurrent();
    fit();
    pages.render();
    return pages.current() !== previous;
  }

  function resetWheelGesture() {
    wheelEvents = [];
    lastWheelStep = 0;
  }

  function movePage(delta) {
    if (!slideShow) return false;
    return setPage((pages.current() || 1) + delta);
  }

  function activate() {
    slideShow = true;
    const pane = $("#artifact-pane");
    pane.classList.add("slide-show");
    frameDocument().documentElement.dataset.htmlMcpPresentation = "slides";
    setPage(pages.current() || pages.visible() || 1);
    $("#artifact-frame").focus({ preventScroll: true });
    frameWindow().focus();
    frameWindow().requestAnimationFrame(() => {
      $("#artifact-frame").focus({ preventScroll: true });
      frameWindow().focus();
    });
  }

  function deactivate() {
    if (!slideShow) return;
    slideShow = false;
    $("#artifact-pane").classList.remove("slide-show");
    resetWheelGesture();
    delete frameDocument().documentElement.dataset.htmlMcpPresentation;
    for (const page of deckPages()) page.classList.remove("html-mcp-current-page");
    fit();
    const number = pages.current();
    if (number !== null) {
      // Until the deck is scrolled back to it, the page just shown is held for a reload: WebKit
      // leaves full screen before the page is hidden, and read from the scroll the place was the
      // first page.
      leftSlideShowAt = number;
      frameWindow().requestAnimationFrame(() => {
        deckPages()[number - 1]?.scrollIntoView({ block: "start" });
        leftSlideShowAt = null;
      });
    }
  }

  // Full screen, or where a browser gives a page none, as Safari on an iPhone does, the pane laid
  // over the whole page.
  function inFullscreen() {
    const pane = $("#artifact-pane");
    return document.fullscreenElement === pane || pane.classList.contains("fills-page");
  }

  function syncFullscreenMode() {
    const fullscreen = inFullscreen();
    $("#fullscreen-btn").setAttribute("aria-pressed", fullscreen ? "true" : "false");
    if (fullscreen) frameDocument().documentElement.dataset.htmlMcpFullscreen = "";
    else delete frameDocument().documentElement.dataset.htmlMcpFullscreen;
    if (fullscreen) hideSelection();
    if (fullscreen && layout() === "slides") {
      activate();
    } else {
      const wasSlideShow = slideShow;
      deactivate();
      fit();
      if (wasSlideShow) scheduleLayoutCheck();
    }
  }

  async function toggleFullscreen() {
    const pane = $("#artifact-pane");
    if (!document.fullscreenEnabled) {
      pane.classList.toggle("fills-page");
      syncFullscreenMode();
    } else if (document.fullscreenElement === pane) {
      await document.exitFullscreen();
    } else {
      await pane.requestFullscreen();
    }
  }

  function targetIsInteractive(target) {
    return typeof target?.closest === "function"
      && target.closest("a, button, input, textarea, select, [contenteditable]") !== null;
  }

  function handleKeydown(event) {
    if (event.key === "Escape" && $("#artifact-pane").classList.contains("fills-page")) {
      event.preventDefault();
      toggleFullscreen();
      return;
    }
    if (!slideShow || event.metaKey || event.ctrlKey || event.altKey) return;
    if (targetIsInteractive(event.target)) return;
    const nextKeys = new Set(["n", "N", "Enter", " ", "PageDown", "ArrowRight", "ArrowDown"]);
    const previousKeys = new Set(["p", "P", "Backspace", "PageUp", "ArrowLeft", "ArrowUp"]);
    if (nextKeys.has(event.key)) {
      event.preventDefault();
      movePage(1);
    } else if (previousKeys.has(event.key)) {
      event.preventDefault();
      movePage(-1);
    } else if (event.key === "Home") {
      event.preventDefault();
      setPage(1);
    } else if (event.key === "End") {
      event.preventDefault();
      setPage(deckPages().length);
    }
  }

  function handleClick(event) {
    if (!slideShow || event.button !== 0) return;
    if (suppressClick) {
      suppressClick = false;
      return;
    }
    if (targetIsInteractive(event.target)) return;
    const selection = frameWindow().getSelection();
    if (selection !== null && !selection.isCollapsed) return;
    movePage(1);
  }

  function handlePointerDown(event) {
    if (!slideShow || event.pointerType !== "touch") return;
    pointer = { id: event.pointerId, x: event.clientX, y: event.clientY };
  }

  function handlePointerUp(event) {
    const start = pointer;
    pointer = null;
    if (!slideShow || start === null || event.pointerId !== start.id) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (Math.abs(dx) < 50 || Math.abs(dx) < Math.abs(dy) * 1.2) return;
    suppressClick = true;
    movePage(dx < 0 ? 1 : -1);
  }

  function handleWheel(event) {
    if (!slideShow) return;
    event.preventDefault();
    const unit = event.deltaMode === WheelEvent.DOM_DELTA_LINE
      ? 40
      : event.deltaMode === WheelEvent.DOM_DELTA_PAGE ? 800 : 1;
    const rawDelta = Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX;
    if (rawDelta === 0) return;
    const wheelEvent = {
      time: performance.now(),
      delta: Math.abs(rawDelta * unit),
      direction: Math.sign(rawDelta),
    };
    const previous = wheelEvents.at(-1);
    wheelEvents.push(wheelEvent);
    if (wheelEvents.length > 2) wheelEvents.shift();
    const newIntent = previous === undefined
      || wheelEvent.direction !== previous.direction
      || wheelEvent.delta > previous.delta
      || wheelEvent.time > previous.time + 150;
    const significant = wheelEvent.delta >= 6;
    const duplicate = significant && wheelEvent.time - lastWheelStep < 60;
    if (newIntent && significant && !duplicate) {
      movePage(wheelEvent.direction);
      lastWheelStep = wheelEvent.time;
    }
  }

  return {
    showing: () => slideShow,
    heldPage: () => (slideShow ? pages.current() || 1 : leftSlideShowAt),
    inFullscreen,
    movePage,
    markCurrent,
    // An edit while the show is on: the page shown stays, held within the pages there are now.
    pagesChanged() {
      pages.setCurrent(Math.min(pages.current() || 1, deckPages().length));
      markCurrent();
    },
    mark(doc) {
      if (inFullscreen()) doc.documentElement.dataset.htmlMcpFullscreen = "";
    },
    install(doc) {
      doc.addEventListener("keydown", handleKeydown, true);
      doc.addEventListener("click", handleClick, true);
      doc.addEventListener("pointerdown", handlePointerDown, true);
      doc.addEventListener("pointerup", handlePointerUp, true);
      doc.addEventListener("wheel", handleWheel, { passive: false });
    },
    resume() {
      if (inFullscreen() && layout() === "slides") activate();
    },
    attach() {
      $("#fullscreen-btn").addEventListener("click", () => {
        // The slide show sizes the current page itself; a reader's zoom held from browsing would
        // put the show off screen.
        entering();
        toggleFullscreen().catch((error) => alert(`Could not enter full screen: ${error.message}`));
      });
      $("#presentation-prev-btn").addEventListener("click", () => movePage(-1));
      $("#presentation-next-btn").addEventListener("click", () => movePage(1));
      $("#presentation-exit-btn").addEventListener("click", () => {
        toggleFullscreen().catch((error) => alert(`Could not exit full screen: ${error.message}`));
      });
      document.addEventListener("wheel", handleWheel, { passive: false });
      document.addEventListener("fullscreenchange", syncFullscreenMode);
      document.addEventListener("keydown", handleKeydown);
    },
  };
}
