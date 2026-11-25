// The size the pages are drawn at: fitted to the pane, times the reader's zoom, or in the slide
// show the one page fitted to the screen. Two fingers, a trackpad's pinch or a wheel held with
// ctrl (command on a Mac) zoom the artifact alone: about the fingers or the pointer over the
// artifact, and about its middle anywhere else on the page, where left to the browser the same
// pinch zoomed the whole page, comments and all, while the artifact kept a zoom of its own. Fit
// in the bar gives the fitted size back. This module keeps the reader's zoom, each artifact's as
// it was left, and the gesture under way.
//
// createZoom takes showing(), whether the slide show is on. It gives fit(), the pages drawn at
// the size they should be; apply(), the reader's zoom applied and Fit shown when there is one;
// reset(), the zoom given back about the window's middle; pinching(), whether a gesture carries
// the deck; scrolled(win), told of each scroll of the deck, which puts back what the browser
// moved on its own just after a gesture; keep(alias) and restore(alias), an artifact's zoom kept
// as the reader leaves it and given back as they return; install(doc), the gestures in a
// document; attach(), the gestures over the rest of the page and the Fit button; and what
// happens to the deck, each of which hands in a function called when it does:
// carrying(listener), as a gesture starts to carry it; settled(listener), once a gesture has
// ended and the scrolls it caused have stopped; and applied(listener), once the pages are drawn
// at the reader's zoom.

import { $ } from "../shared/dom.js";
import { pageIsZoomed } from "../shared/page-zoom.js";
import { frameDocument, frameWindow, pageNear } from "./deck-dom.js";
import { createListeners } from "../shared/listeners.js";

export function createZoom({ showing }) {
  const carrying = createListeners();
  const settled = createListeners();
  const applied = createListeners();
  let artifactZoom = 1;
  // The zoom each artifact was left at. The frame keeps its own scroll and the scale it is drawn
  // at; the number the zoom handlers and the reset control work from is this one, and it is put
  // back with the frame.
  const zooms = {};
  let pinch = null;
  // Two fingers that began while the page itself was zoomed belong to the browser until they
  // lift: see pageIsZoomed.
  let pageGesture = false;
  let pageTouch = false;
  let pinchSettle = null;
  let settledScroll = null;
  // A settled pinch is told 60 ms after the last scroll it causes.
  let placeAfterSettle = null;

  function fit() {
    const doc = frameDocument();
    const page = showing()
      ? doc.querySelector("body > main.pages > section.page.html-mcp-current-page")
      : doc.querySelector("body > main.pages > section.page");
    if (page === null) return;
    // The width the page is actually given, measured rather than guessed from the window: the
    // guess put a phone's margin at 8px where the stylesheet spends 48, so the page was fitted
    // 40px too wide and hung off the right while the left kept its margin.
    const holder = page.parentElement;
    const availableWidth = holder.clientWidth || frameWindow().innerWidth;
    const widthScale = availableWidth / page.offsetWidth;
    const fitted = showing()
      ? Math.min(widthScale, frameWindow().innerHeight / page.offsetHeight)
      : Math.min(1, widthScale);
    const scale = showing() ? fitted : fitted * artifactZoom;
    const root = frameDocument().documentElement;
    root.style.setProperty("--html-mcp-page-scale", String(scale));
    root.style.setProperty("--html-mcp-zoom", String(showing() ? 1 : artifactZoom));
    // The room a drawn-smaller block gives back depends on its own height, and only the template
    // knows how tall a script block is.
    const script = doc.querySelector("body > main.pages > .script-block");
    if (script !== null) root.style.setProperty("--html-mcp-script-height", `${script.offsetHeight}px`);
  }

  // Every touch on the artifact is answered here, so the browser cannot take a gesture halfway
  // through and turn a pinch into a scroll, which is what made an earlier reading of it cut out.
  // A finger that stays put still belongs to the browser, because that is a reader holding a word.
  function install(doc) {
    // A gesture on the document this one replaces is over, whatever its fingers do next.
    pinch = null;
    for (const kind of ["touchstart", "touchmove", "touchend", "touchcancel"]) {
      doc.addEventListener(kind, handleArtifactTouch, { passive: false, capture: true });
    }
    doc.addEventListener("wheel", handleArtifactWheel, { passive: false, capture: true });
    for (const kind of ["gesturestart", "gesturechange", "gestureend"]) {
      doc.addEventListener(kind, handleArtifactGesture, { passive: false, capture: true });
    }
  }

  // Safari sends two fingers as a gesture of its own, with the scale since the gesture began, and
  // on a Mac that gesture is all a trackpad pinch sends: refused and left at that, the pinch zoomed
  // nothing there. So the gesture drives the zoom, unless touches already do, as on a phone, where
  // the gesture comes beside them and is only refused. Refusing it matters either way: left to
  // run, Safari's own zoom moved the window under the settled layout and the deck appeared
  // somewhere else the moment the fingers lifted.
  function handleArtifactGesture(event) {
    if (leftToPage(event)) return;
    zoomFromGesture(event, { x: event.clientX, y: event.clientY });
  }

  // The page itself can be zoomed: by a field that took the cursor on a phone, or by a pinch made
  // before this listened. Two fingers then have to reach the browser, or nothing brings the page
  // back, and every pinch went to the artifact with the sidebar cut off. It is decided when they
  // land and kept until they lift, so a zoom-out that passes the mark on its way down is not taken
  // over short of the end.
  function leftToPage(event) {
    if (event.type === "gesturestart") pageGesture = pageIsZoomed();
    if (!pageGesture) return false;
    if (event.type === "gestureend") pageGesture = false;
    return true;
  }

  function handleViewerGesture(event) {
    if (leftToPage(event)) return;
    if (frameDocument() === null) {
      event.preventDefault();
      return;
    }
    const frame = $("#artifact-frame").getBoundingClientRect();
    zoomFromGesture(event, { x: frame.width / 2, y: frame.height / 2 });
  }

  function zoomFromGesture(event, point) {
    event.preventDefault();
    if (showing()) return;
    if (pinch !== null && pinch.driver === "touch") return;
    if (event.type === "gesturestart") {
      if (pinch !== null) settlePinch();
      settledScroll = null;
      pinch = beginPinch(1, point, "gesture");
      return;
    }
    if (pinch === null || pinch.driver !== "gesture") return;
    if (event.type === "gesturechange") {
      carryPinch(pinch, pinch.startZoom * event.scale, point);
      return;
    }
    settlePinch();
  }

  // A trackpad pinch reaches the page as a wheel event holding ctrl, which is also what a mouse
  // sends under the key each desktop zooms with: ctrl on Windows and Linux, command on a Mac. The
  // pointer is the fixed point, as the point between two fingers is.
  function handleArtifactWheel(event) {
    keepSidewaysWheel(event);
    zoomFromWheel(event, { x: event.clientX, y: event.clientY });
  }

  // Safari starts its swipe back or forward on the first wheel event of a gesture that is mostly
  // sideways when nothing under the pointer scrolls that way, and is told not to at that event
  // alone, by the event being taken. There is no page to go back to here, and a deck fitted to its
  // width scrolls sideways nowhere, so two fingers that set off a little sideways left the
  // artifact for the page before: a sideways wheel that nothing under the pointer can follow is
  // taken, and the fingers stay in the artifact.
  function keepSidewaysWheel(event) {
    if (Math.abs(event.deltaX) <= Math.abs(event.deltaY)) return;
    for (let node = event.target; node !== null && node.nodeType === 1; node = node.parentElement) {
      if (scrollsSideways(node, event.deltaX)) return;
    }
    event.preventDefault();
  }

  function scrollsSideways(node, deltaX) {
    const doc = node.ownerDocument;
    if (node !== doc.scrollingElement) {
      const overflow = doc.defaultView.getComputedStyle(node).overflowX;
      if (overflow !== "auto" && overflow !== "scroll") return false;
    }
    return deltaX < 0 ? node.scrollLeft > 0 : node.scrollLeft + node.clientWidth < node.scrollWidth - 1;
  }

  // Over the rest of the viewer, the comments or the bar, the same pinch zooms the artifact about
  // its middle.
  function handleViewerWheel(event) {
    keepSidewaysWheel(event);
    if (frameDocument() === null) return;
    const frame = $("#artifact-frame").getBoundingClientRect();
    zoomFromWheel(event, { x: frame.width / 2, y: frame.height / 2 });
  }

  function zoomFromWheel(event, point) {
    settledScroll = null;
    if (!(event.ctrlKey || event.metaKey) || showing()) return;
    event.preventDefault();
    // A gesture that drives the zoom is the whole gesture: a wheel beside it is not a step.
    if (pinch !== null && pinch.driver === "gesture") return;
    if (pinch === null) pinch = beginPinch(1, point, "wheel");
    const held = pinch;
    if (held === null) return;
    // Fingers spreading on a trackpad arrive as many small steps, and the size follows the
    // distance they travel, at the rate a browser zooms its own pages by: a pinch here reaches as
    // far as the same pinch anywhere else. A mouse sends one large step per notch, where that rate
    // would multiply the size by e, so a notch has a step of its own. Both multiply, so a step
    // moves the same share of the size at any zoom and zooming in then out by the same amount
    // lands back where it started.
    const notch = event.deltaMode !== WheelEvent.DOM_DELTA_PIXEL || Math.abs(event.deltaY) >= 40;
    const factor = notch
      ? (event.deltaY < 0 ? 1.25 : 1 / 1.25)
      : Math.exp(-event.deltaY / 100);
    carryPinch(held, held.zoom * factor, point);
    // A wheel has no lift to end on, so the gesture ends where the steps stop.
    if (pinchSettle !== null) clearTimeout(pinchSettle);
    pinchSettle = setTimeout(settlePinch, 150);
  }

  // The reader's zoom is the page's own size, not a transform laid over it. A transform creates
  // no scrollable room, so whatever it pushed past an edge could not be reached: zoomed in, the
  // left never came back and the first page lost its top. The factor goes into the scale the
  // pages are laid out at, whose margins grow the boxes with it, so the document is genuinely
  // larger and scrolls in both directions like any other.
  //
  // That layout is settled once, when the gesture ends. While it runs, the holder of the pages is
  // carried by one transform the compositor applies, which lays nothing out and paints nothing
  // anew: laying the pages out again on every step, and rebuilding the highlight boxes each time,
  // was work a phone could not finish between two frames, and the zoom stuttered in step with it.
  //
  // One finger is the browser's, whether it holds a word or scrolls: the layout is a document of
  // its own size and scrolls like any other, with the browser's smoothness and momentum.
  // Scrolling it ourselves, by the finger's movement, stuttered, and doubled the distance whenever
  // the browser had begun a scroll of its own before we took over.
  function handleArtifactTouch(event) {
    const touches = Array.from(event.touches);
    // In the slide show the stylesheet fits the page and centres it, and a carried holder has no
    // layout to settle into: two fingers are taken from the browser, as the wheel and the gesture
    // are there, and carry nothing. A gesture still in flight is settled.
    if (showing()) {
      if (pinch !== null) settlePinch();
      if (touches.length >= 2) event.preventDefault();
      return;
    }
    if (event.type === "touchstart") settledScroll = null;
    if (event.type === "touchend" || event.type === "touchcancel") {
      if (touches.length < 2) pageTouch = false;
      if (touches.length < 2 && pinch !== null) settlePinch();
      return;
    }
    if (touches.length < 2) return;
    if (event.type === "touchstart" && pinch === null) pageTouch = pageIsZoomed();
    if (pageTouch) return;
    const [first, second] = touches;
    const span = Math.hypot(first.clientX - second.clientX, first.clientY - second.clientY);
    const middle = { x: (first.clientX + second.clientX) / 2, y: (first.clientY + second.clientY) / 2 };
    if (pinch === null || event.type === "touchstart") {
      if (pinch !== null) settlePinch();
      pinch = beginPinch(span, middle, "touch");
      // A second finger is never a reader holding a word, so this one is taken from the browser
      // at once: told only at the first move, it has already begun a zoom of its own, and two
      // zooms ran on the same fingers.
      if (pinch !== null) event.preventDefault();
      return;
    }
    event.preventDefault();
    carryPinch(pinch, pinch.startZoom * (span / pinch.startSpan), middle);
  }

  // The holder scaled about its own corner and shifted so that what the gesture started on is
  // under the fixed point now, held within what the settled layout can reach: a page narrower
  // than its holder sits centred with no scroll to move it, a wider one scrolls between its two
  // edges, and the deck scrolls between the document's top and bottom margins. Shown anywhere
  // else, the deck jumped to the nearest reachable place the moment the gesture ended.
  function carryPinch(held, zoom, at) {
    held.zoom = Math.min(4, Math.max(0.5, zoom));
    held.middle = at;
    const grown = held.zoom / held.startZoom;
    const room = held.room;
    // What is visible is measured as it stands, not as it stood: a phone hides its address bar
    // partway through a gesture, and a deck held within the room it had before that was outside
    // the room it had after.
    const view = frameDocument().documentElement;
    room.viewWidth = view.clientWidth;
    room.viewHeight = view.clientHeight;
    const shift = {
      x: at.x - held.origin.x - grown * held.focal.x,
      y: at.y - held.origin.y - grown * held.focal.y,
    };
    const pageWidth = grown * room.pageWidth;
    const pageAtZero = room.left - held.origin.x - grown * room.pageOffset;
    shift.x = pageWidth <= room.width
      ? pageAtZero + (room.width - pageWidth) / 2
      : Math.min(pageAtZero, Math.max(
          pageAtZero - (room.left + pageWidth + room.right - room.viewWidth), shift.x));
    const holderAtZero = room.top - held.origin.y;
    shift.y = Math.min(holderAtZero, Math.max(
      holderAtZero - (room.top + grown * room.height + room.bottom - room.viewHeight), shift.y));
    held.holder.style.transform = `translate(${shift.x}px, ${shift.y}px) scale(${grown})`;
  }

  // What the gesture keeps of its start: the holder's corner and the point between the fingers
  // relative to it, for carrying the holder; that point in the coordinates of the page it lies on,
  // which no zoom changes, for putting it back under the fingers once the layout is settled; and
  // the room the settled layout will have, read off the document now, since the holder grows by
  // the zoom alone and the margins around it not at all.
  function beginPinch(span, middle, driver) {
    if (span === 0 || showing()) return null;
    const doc = frameDocument();
    const win = frameWindow();
    const holder = doc.querySelector("body > main.pages");
    const page = pageNear(middle);
    if (holder === null || page === null) return null;
    const corner = holder.getBoundingClientRect();
    const box = page.getBoundingClientRect();
    const ratio = box.width / page.offsetWidth;
    const left = corner.left + win.scrollX;
    const top = corner.top + win.scrollY;
    const room = {
      left,
      top,
      right: doc.documentElement.scrollWidth - (left + corner.width),
      bottom: doc.documentElement.scrollHeight - (top + corner.height),
      width: corner.width,
      height: corner.height,
      pageOffset: box.left - corner.left,
      pageWidth: box.width,
      viewWidth: doc.documentElement.clientWidth,
      viewHeight: doc.documentElement.clientHeight,
    };
    // The document's scrollable size follows the carried holder, and shrunk by a zoom out it let
    // the browser pull the scroll position back in the middle of the gesture. A dot pinned at the
    // document's far corner holds that size until the layout settles.
    const keeper = doc.createElement("div");
    Object.assign(keeper.style, {
      position: "absolute", left: "0px", top: "0px", width: "1px", height: "1px",
      visibility: "hidden", pointerEvents: "none",
    });
    doc.body.appendChild(keeper);
    const placed = keeper.getBoundingClientRect();
    keeper.style.left = `${doc.documentElement.scrollWidth - 1 - (placed.left + win.scrollX)}px`;
    keeper.style.top = `${doc.documentElement.scrollHeight - 1 - (placed.top + win.scrollY)}px`;
    holder.style.transformOrigin = "0 0";
    holder.style.willChange = "transform";
    // What is placed over the deck, as the comment button is, stays where it was placed while the
    // deck under it is carried: the gesture is told as it starts, and again once it has settled.
    carrying.tell();
    return {
      driver,
      startSpan: span,
      startZoom: artifactZoom,
      zoom: artifactZoom,
      middle,
      holder,
      origin: { x: corner.left, y: corner.top },
      focal: { x: middle.x - corner.left, y: middle.y - corner.top },
      page,
      local: { x: (middle.x - box.left) / ratio, y: (middle.y - box.top) / ratio },
      room,
      keeper,
    };
  }

  function settlePinch() {
    const held = pinch;
    pinch = null;
    if (pinchSettle !== null) clearTimeout(pinchSettle);
    pinchSettle = null;
    held.holder.style.transform = "";
    held.holder.style.transformOrigin = "";
    held.holder.style.willChange = "";
    if (held.zoom === held.startZoom) {
      held.keeper.remove();
      setTimeout(() => settled.tell(), 60);
      return;
    }
    const win = frameWindow();
    const page = held.page;
    artifactZoom = held.zoom;
    apply();
    page.getBoundingClientRect();
    // Safari keeps the scroll position anchored to an element and, after a layout, moves the
    // position by what that element moved. A layout that changes transforms is left alone, so the
    // zoom above leaves the anchor's recorded place where the old layout had it, and the next
    // layout of any kind moved the deck by the zoom's whole displacement: the highlight boxes
    // redrawn a frame later sent it somewhere else after the fingers had lifted. The dot's removal
    // is that next layout, made here, before the position is set; and it is set absolutely, so
    // nothing already applied is applied again. The property that turns the anchoring off is not
    // implemented there.
    held.keeper.remove();
    frameDocument().body.getBoundingClientRect();
    const box = page.getBoundingClientRect();
    const ratio = box.width / page.offsetWidth;
    win.scrollTo(win.scrollX + box.left + held.local.x * ratio - held.middle.x,
                 win.scrollY + box.top + held.local.y * ratio - held.middle.y);
    // What the browser moves on its own in the moment after is put back; the reader's own next
    // touch or wheel ends the watch. The moment is 400 ms and three frames, whichever is longer:
    // the browser's move comes with a frame, which a machine slow to draw gave after 400 ms.
    const watch = { x: win.scrollX, y: win.scrollY, until: performance.now() + 400, frames: 0 };
    settledScroll = watch;
    const count = () => {
      watch.frames += 1;
      if (watch.frames < 3) win.requestAnimationFrame(count);
    };
    win.requestAnimationFrame(count);
    // Told after the scrolls that follow, which hide the comment button as any scroll does. Their
    // events come with the frames drawn, later than any fixed delay on a machine slow to draw,
    // where the button came back before the scroll and stayed hidden: the wait starts at the next
    // frame and again at each scroll.
    placeAfterSettle = 0;
    win.requestAnimationFrame(placeAfterScroll);
  }

  function placeAfterScroll() {
    if (placeAfterSettle === null) return;
    clearTimeout(placeAfterSettle);
    placeAfterSettle = setTimeout(() => {
      placeAfterSettle = null;
      settled.tell();
    }, 60);
  }

  function apply() {
    $("#zoom-reset-btn").classList.toggle("hidden", Math.abs(artifactZoom - 1) < 0.01);
    fit();
    applied.tell();
  }

  // The way back from a zoom keeps the reader's place: laid out again with the scroll position
  // left as it was, the deck showed some other part of itself, further down after a zoom in and
  // further up after a zoom out. What sits at the middle of the window is the fixed point, and the
  // settle a pinch ends with puts it back there.
  function reset() {
    if (pinch !== null) settlePinch();
    if (artifactZoom === 1) return;
    const view = frameDocument().documentElement;
    const middle = { x: view.clientWidth / 2, y: view.clientHeight / 2 };
    const held = beginPinch(1, middle, "wheel");
    if (held === null) {
      artifactZoom = 1;
      apply();
      return;
    }
    held.zoom = 1;
    pinch = held;
    settlePinch();
  }

  return {
    fit,
    apply,
    reset,
    pinching: () => pinch !== null,
    scrolled(win) {
      placeAfterScroll();
      const settled = settledScroll;
      if (settled === null) return;
      settledScroll = null;
      if ((performance.now() < settled.until || settled.frames < 3)
          && (Math.abs(win.scrollX - settled.x) > 1 || Math.abs(win.scrollY - settled.y) > 1)) {
        win.scrollTo(settled.x, settled.y);
      }
    },
    keep(alias) {
      if (alias) zooms[alias] = artifactZoom;
    },
    restore(alias) {
      artifactZoom = zooms[alias] ?? 1;
    },
    install,
    carrying: carrying.add,
    settled: settled.add,
    applied: applied.add,
    attach() {
      document.addEventListener("wheel", handleViewerWheel, { passive: false });
      for (const kind of ["gesturestart", "gesturechange", "gestureend"]) {
        document.addEventListener(kind, handleViewerGesture, { passive: false });
      }
      $("#zoom-reset-btn").addEventListener("click", () => {
        reset();
      });
    },
  };
}
