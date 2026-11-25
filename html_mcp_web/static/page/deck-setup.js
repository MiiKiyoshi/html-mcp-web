// What the page sets up for the document the frame on screen shows: its size, its speaker
// scripts, the page being read, and the box tool, the selection, the zoom, the slide show and the
// search in it, with the scroll and resize of its window; then the comments' marks, the search's
// matches and the layout check's result on it, and the slide show again in full screen. A
// document the page set up once, shown again or changed in place, needs the page alone set up.
//
// createDeckSetup takes the parts it sets up: project (artifact()); zoom (fit(), apply(),
// install(doc), scrolled(win)); scripts (apply()); presentation (showing(), mark(doc),
// install(doc), resume()); pages (visible(), setCurrent(number), render(), schedule()); area,
// selection and search, each installed in the document (install(doc), hide(), handleKeydown,
// refresh()); marks (render(), schedule()); layout (show(), schedule(), watch(doc, images)); and
// dragging(), whether a grip is being dragged. It gives loaded(doc, win), for a document just
// loaded, and shown(), for one the page set up before.

import { frameWindow, keepReadingPlace, readingPlace, scrollToRepaint } from "./deck-dom.js";

export function createDeckSetup({
  project, zoom, scripts, presentation, pages, area, selection, search, marks, layout, dragging,
}) {
  function loaded(doc, win) {
    // Page geometry exists before anchors are measured.
    if (doc.documentElement.dataset.htmlMcpLayout !== project.artifact().layout) {
      throw new Error("artifact layout does not match project configuration");
    }
    zoom.fit();
    scripts.apply();
    presentation.mark(doc);
    pages.setCurrent(pages.visible());
    pages.render();
    area.install(doc);
    selection.install(doc);
    zoom.install(doc);
    presentation.install(doc);
    doc.addEventListener("keydown", (event) => search.handleKeydown(event), true);
    win.addEventListener("scroll", () => {
      zoom.scrolled(win);
      selection.hide();
      pages.schedule();
    }, { passive: true });
    win.addEventListener("resize", () => {
      // A wider or narrower artifact draws every page at another size, and the scroll position
      // left as it was showed some other page: hiding the comments took the reader from page 12 to
      // page 8, and showing them took the reader back. What sits at the top of the window stays
      // there. The top, not the middle: a window that also grows taller moves its middle, and the
      // deck read from its first line was pushed down by the difference.
      const place = presentation.showing() ? null : readingPlace();
      zoom.fit();
      keepReadingPlace(place);
      // Dragging the split resizes the artifact on every frame. Measuring the fit of all pages and
      // redrawing the highlight boxes that often is the work that made the bar lag behind the
      // finger; the drag ends with one of each.
      if (dragging()) return;
      marks.schedule();
      layout.schedule();
      pages.schedule();
    });
    // The zoom the document is shown at is the artifact's own, and the reset control follows it; a
    // scroll put back means the same only at the zoom it was taken at.
    zoom.apply();
    marks.render();
    search.refresh();
    layout.show();
    presentation.resume();
    layout.schedule();
    layout.watch(doc, doc.images);
  }

  // A frame shown again is already loaded: what the switch has to do is set the page up for it.
  // The check schedules itself only for a frame not yet measured with its fonts in.
  function shown() {
    zoom.apply();
    marks.render();
    pages.setCurrent(pages.visible());
    pages.render();
    layout.show();
    layout.schedule();
    search.refresh();
    scrollToRepaint(frameWindow());
  }

  return { loaded, shown };
}
