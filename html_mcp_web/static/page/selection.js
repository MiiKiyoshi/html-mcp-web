// Words selected on a page, and the menu beside them: Comment, which opens a new comment on them,
// and Source, which shows them where the edit file writes them. The menu comes once a selection
// has settled, by a mouse, the keys or a finger, and goes with a scroll, a press elsewhere, a
// gesture that carries the deck, and full screen. This module keeps the anchor the selection
// would be commented on by, and whether a pointer is down.
//
// createSelection takes base(), the route of the artifact's calls; captureTextAnchor(range);
// pinching(), whether a gesture carries the deck; inFullscreen(); commentOn(anchor); and
// showInSource(place), which shows a place of the edit file in the editor. It gives show(), the
// menu placed by the selection or taken away; hide(); forget(), the anchor let go once a comment
// on it is posted; clear(), the selection taken away with its menu; install(doc), the selection
// watched in a document; and attach(), the menu's buttons.

import { $ } from "../shared/dom.js";
import { fetchJson } from "./fetch-json.js";
import { PAGE, deckPages, frameDocument, frameWindow, pageTitle } from "./deck-dom.js";
import { selectionRects, selectionSpan } from "./selection-rects.js";

export function createSelection({ base, captureTextAnchor, pinching, inFullscreen, commentOn, showInSource }) {
  let selectionAnchor = null;
  let pointerDown = false;
  let settle = null;

  function hide() {
    $("#selection-menu").classList.add("hidden");
  }

  function show() {
    const selection = frameWindow().getSelection();
    const menu = $("#selection-menu");
    // While a gesture carries the deck the menu stays out of it: the selection's own settle,
    // timed from before the gesture, would otherwise bring it back mid-way.
    if (pinching()) return;
    if (inFullscreen()) {
      selectionAnchor = null;
      hide();
      return;
    }
    if (selection === null || selection.rangeCount === 0) {
      selectionAnchor = null;
      hide();
      return;
    }
    const range = selectionSpan(selection);
    if (range.collapsed) {
      selectionAnchor = null;
      hide();
      return;
    }
    try {
      selectionAnchor = captureTextAnchor(range);
    } catch (error) {
      selectionAnchor = null;
      hide();
      return;
    }
    // The same geometry the highlight uses, so the menu meets the letters that were grabbed
    // rather than the whole svg label they sit in.
    const marks = selectionRects(range);
    const rect = marks.length === 0 ? range.getBoundingClientRect() : {
      left: Math.min(...marks.map((mark) => mark.left)),
      top: Math.min(...marks.map((mark) => mark.top)),
      bottom: Math.max(...marks.map((mark) => mark.top + mark.height)),
    };
    const iframe = $("#artifact-frame");
    const pane = $("#artifact-pane");
    menu.classList.remove("hidden");
    // Under the selection and lined up with its left edge. The menu's own size is read rather
    // than assumed, so the pane's edges can hold it: a selection near the bottom puts it above
    // instead, and one near a side slides it along until the whole menu fits.
    const gap = 8;
    const width = menu.offsetWidth;
    const height = menu.offsetHeight;
    const under = iframe.offsetTop + rect.bottom + gap;
    const above = iframe.offsetTop + rect.top - height - gap;
    const wanted = under + height > pane.clientHeight - gap && above >= gap ? above : under;
    const left = iframe.offsetLeft + rect.left;
    menu.style.left = `${Math.max(gap, Math.min(left, pane.clientWidth - width - gap))}px`;
    menu.style.top = `${Math.max(gap, Math.min(wanted, pane.clientHeight - height - gap))}px`;
  }

  // A stretch of the page as its source writes it: rendered math as the TeX KaTeX keeps in the
  // formula's annotation, other text as shown.
  function sourceLikeText(range) {
    const doc = frameDocument();
    const walker = doc.createTreeWalker(range.commonAncestorContainer.nodeType === Node.TEXT_NODE
      ? range.commonAncestorContainer.parentNode : range.commonAncestorContainer, NodeFilter.SHOW_TEXT);
    let text = "";
    let formula = null;
    for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
      if (!range.intersectsNode(node) || node.parentElement?.closest(".html-mcp-highlight-layer")) continue;
      const math = node.parentElement?.closest(".katex");
      if (math) {
        if (math === formula) continue;
        formula = math;
        text += ` ${math.querySelector('annotation[encoding="application/x-tex"]')?.textContent ?? ""} `;
        continue;
      }
      const from = node === range.startContainer ? range.startOffset : 0;
      const to = node === range.endContainer ? range.endOffset : node.nodeValue.length;
      text += node.nodeValue.slice(from, to);
    }
    return text;
  }

  // The place in the edit file the selected words come from, found by the server in the file as
  // saved.
  async function openInSource() {
    const selection = frameWindow().getSelection();
    if (selectionAnchor === null || selection === null || selection.rangeCount === 0) return;
    const selected = selectionSpan(selection);
    const start = selected.startContainer;
    const page = (start.nodeType === Node.ELEMENT_NODE ? start : start.parentElement)?.closest(PAGE);
    const title = page ? pageTitle(page, deckPages().indexOf(page)) : "";
    const around = (from, to) => {
      const stretch = frameDocument().createRange();
      stretch.setStart(from.node, from.offset);
      stretch.setEnd(to.node, to.offset);
      return sourceLikeText(stretch);
    };
    const edge = page ?? frameDocument().body;
    const quote = sourceLikeText(selected);
    const prefix = around({ node: edge, offset: 0 }, { node: selected.startContainer, offset: selected.startOffset }).slice(-120);
    const suffix = around({ node: selected.endContainer, offset: selected.endOffset }, { node: edge, offset: edge.childNodes.length }).slice(0, 120);
    const place = await fetchJson(`${base()}/source-place`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quote, prefix, suffix, title }),
    });
    hide();
    await showInSource(place);
  }

  // A phone selects by holding a word and dragging the handles, and sends no mouseup for any of
  // it: the words were highlighted and no button ever came. The selection itself is watched as
  // well, held back while a pointer is down so that a drag on a desktop still settles before the
  // button appears. Holding a word hands that touch to the browser's own selection, and the
  // sequence ends as a cancel rather than a release. A cancel is the end of a touch like any
  // other, so it asks the same question; without that the highlighted words waited for the next
  // pan or pinch to bring the button.
  function install(doc) {
    doc.addEventListener("mouseup", () => setTimeout(show, 0), true);
    doc.addEventListener("keyup", () => setTimeout(show, 0), true);
    for (const kind of ["touchend", "touchcancel"]) {
      doc.addEventListener(kind, () => setTimeout(show, 60), true);
    }
    doc.addEventListener("selectionchange", () => {
      if (pointerDown) return;
      if (settle !== null) clearTimeout(settle);
      settle = setTimeout(() => {
        settle = null;
        show();
      }, 250);
    });
    doc.addEventListener("pointerdown", (event) => {
      pointerDown = true;
      if (!event.target.closest(".html-mcp-highlight-layer")) hide();
    }, true);
    for (const kind of ["pointerup", "pointercancel"]) {
      doc.addEventListener(kind, () => {
        pointerDown = false;
        setTimeout(show, 60);
      }, true);
    }
  }

  return {
    show,
    hide,
    forget() {
      selectionAnchor = null;
    },
    clear() {
      frameWindow().getSelection()?.removeAllRanges();
      hide();
    },
    install,
    attach() {
      $("#selection-comment-btn").addEventListener("click", () => {
        if (selectionAnchor !== null) commentOn(selectionAnchor);
      });
      $("#selection-source-btn").addEventListener("click", () => {
        openInSource().catch((error) => alert(`Could not open the source: ${error.message}`));
      });
    },
  };
}
