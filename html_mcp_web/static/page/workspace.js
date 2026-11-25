// The workspace shows the Preview, the Source or Split, the two side by side, or stacked at 950px
// wide or less, parted by a grip dragged, or moved by the arrow keys, to share the room between
// them. The view tabs choose the view; on a touch screen they sit in the artifact's bar by the
// previews button, where a thumb reaches them, and with a mouse on the left of the top bar. The
// browser keeps the view and the share for next time. This module keeps the view, the share and
// whether a grip is being dragged, the panel's included.
//
// createWorkspace takes source (load(force), resize()), the editor, which the Source and Split
// show. It gives view(); show(view); restore(), the view the reader last chose; dragging(),
// whether a grip is being dragged, which the artifact leaves its fitting to the end of; drag(on),
// told by the panel's grips as a drag starts and once they have set the panel's size; split, how
// the panel's grips hold the split stacked above the panel (panel-grips.js); resized(listener),
// which hands in a function called once the Preview's room has changed: a view that shows it
// shown, or the split or the panel's size set; and attach().

import { $ } from "../shared/dom.js";
import { createListeners } from "../shared/listeners.js";

const VIEWS = ["preview", "source", "split"];
// What the browser keeps the view under.
const KEPT = "htmlMcpWorkspaceView";

export function createWorkspace({ source }) {
  const resized = createListeners();
  let view = "preview";
  let dragging = false;
  const grip = $("#split-grip");
  const workspace = $("#workspace");
  const stacked = matchMedia("(max-width: 950px)");
  let ratio = Number(localStorage.getItem("htmlMcpSplitRatio")) || 0.5;

  async function show(wanted) {
    if (!VIEWS.includes(wanted)) return;
    if (wanted !== "preview") await source.load(false);
    view = wanted;
    const layout = $(".layout");
    layout.classList.remove("view-preview", "view-source", "view-split");
    layout.classList.add(`view-${wanted}`);
    for (const button of document.querySelectorAll(".view-tab")) {
      button.classList.toggle("active", button.dataset.view === wanted);
    }
    localStorage.setItem(KEPT, wanted);
    requestAnimationFrame(() => {
      source.resize();
      if (wanted !== "source") resized.tell();
    });
  }

  const apply = (value) => {
    ratio = Math.max(0.15, Math.min(0.85, value));
    workspace.style.setProperty("--split-first", `${ratio}fr`);
    workspace.style.setProperty("--split-second", `${1 - ratio}fr`);
    grip.setAttribute("aria-valuenow", String(Math.round(ratio * 100)));
    source.resize();
  };

  const finish = () => {
    dragging = false;
    localStorage.setItem("htmlMcpSplitRatio", String(ratio));
    source.resize();
    resized.tell();
  };

  function attach() {
    const orientation = () => {
      grip.setAttribute("aria-orientation", stacked.matches ? "horizontal" : "vertical");
      requestAnimationFrame(finish);
    };
    apply(ratio);
    orientation();
    stacked.addEventListener("change", orientation);
    grip.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      dragging = true;
      grip.setPointerCapture(event.pointerId);
      const move = (moved) => {
        const rect = workspace.getBoundingClientRect();
        const size = stacked.matches ? rect.height : rect.width;
        const position = stacked.matches ? moved.clientY - rect.top : moved.clientX - rect.left;
        apply((position - 5) / Math.max(1, size - 10));
      };
      const done = () => {
        grip.removeEventListener("pointermove", move);
        grip.removeEventListener("lostpointercapture", done);
        finish();
      };
      grip.addEventListener("pointermove", move);
      grip.addEventListener("lostpointercapture", done);
    });
    grip.addEventListener("keydown", (event) => {
      const decrease = stacked.matches ? "ArrowUp" : "ArrowLeft";
      const increase = stacked.matches ? "ArrowDown" : "ArrowRight";
      if (![decrease, increase, "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      apply(event.key === "Home" ? 0.15 : event.key === "End" ? 0.85
        : ratio + (event.key === decrease ? -0.05 : 0.05));
      finish();
    });
    for (const button of document.querySelectorAll(".view-tab")) {
      button.addEventListener("click", () => {
        show(button.dataset.view).catch((error) => alert(error.message));
      });
    }
    const touch = window.matchMedia("(pointer: coarse)");
    const placeViewTabs = () => {
      if (touch.matches) $("#thumbs-btn").after($(".view-tabs"));
      else $("#artifact-tabs").before($(".view-tabs"));
    };
    touch.addEventListener("change", placeViewTabs);
    placeViewTabs();
  }

  return {
    view: () => view,
    show,
    // The view the reader last chose, when it shows the Source.
    async restore() {
      const kept = localStorage.getItem(KEPT);
      if (["source", "split"].includes(kept)) await show(kept);
    },
    dragging: () => dragging,
    drag(on) {
      dragging = on;
      if (!on) resized.tell();
    },
    // With the panes stacked, the comments' bar under them changes the height the split divides,
    // and a ratio kept through that drag carried the split's bar up the screen with it. The drag
    // holds the bar where it was by moving the ratio instead.
    split: {
      holdable: () => stacked.matches && $(".layout").classList.contains("view-split"),
      centerY: () => {
        const box = grip.getBoundingClientRect();
        return box.top + box.height / 2;
      },
      holdAt: (y) => {
        const top = $("#artifact-pane").getBoundingClientRect().top;
        const rows = workspace.getBoundingClientRect().bottom - top - 10;
        apply((y - top - 5) / Math.max(1, rows));
      },
      keep: () => localStorage.setItem("htmlMcpSplitRatio", String(ratio)),
    },
    resized: resized.add,
    attach,
  };
}
