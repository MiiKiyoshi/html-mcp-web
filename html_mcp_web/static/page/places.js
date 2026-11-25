// A place of the artifact shown in the views, the Preview and the Source, which Split shows side
// by side: where a comment is, shown from its card; words of the file found on the pages; and a
// place in the file words on the pages come from. Each kind of place has its rule for which view
// brings it into sight. A comment shown from its mark opens in the panel, which opens first.
//
// createPlaces takes workspace (view(), show(view)); source (load(force), showAnchor(anchor,
// focus), showPlace(place)); marks (flash(id), showRange(range)); anchors (resolveAnchor(anchor),
// rangeFromShown(shown)); showComment(id), which opens a comment's card in the panel; and
// showTab(name), which shows a tab of the sidebar. It gives showComment(comment), a comment's
// place shown with the keys left in the list; enterComment(comment), for K, which takes the keys to
// a comment's words in the source; openComment(id), a comment opened from its mark; takeComment(id),
// a comment opened from the editor with the keys taken to the list; showInSource(place); and
// showWherePrinted(shown).

import { $ } from "../shared/dom.js";
import { setSidebarCollapsed } from "../shared/sidebar.js";
import { deckPages, frameDocument } from "./deck-dom.js";

export function createPlaces({ workspace, source, marks, anchors, showComment, showTab }) {
  // A comment's words in the source, selected, the editor taking the keys unless told to leave
  // them where they are.
  async function openSourceLocation(anchor, focus = true) {
    if (workspace.view() === "preview") await workspace.show("source");
    else await source.load(false);
    source.showAnchor(anchor, focus);
  }

  // Where a comment is, shown from the comments: the page scrolls to it, or the source selects its
  // words, and the keys stay with the comments, where the reader clicked or pressed Space.
  async function showCommentPlace(comment) {
    const id = comment.id;
    if (comment.anchor.kind === "source") {
      await openSourceLocation(comment.anchor, false);
    } else if (comment.anchor.kind === "page") {
      deckPages()[comment.anchor.number - 1]?.scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (comment.anchor.kind === "area") {
      frameDocument().querySelector(`.html-mcp-area[data-comment-id="${CSS.escape(id)}"]`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
      marks.flash(id);
    } else if (comment.anchor.kind === "text") {
      const range = anchors.resolveAnchor(comment.anchor);
      // A comment whose text is gone is not stranded: the page carries a dashed mark where it was
      // written, and the card opens there like any other.
      const element = range === null
        ? frameDocument().querySelector(`.html-mcp-lost[data-comment-id="${CSS.escape(id)}"]`)
        : (range.startContainer.nodeType === Node.ELEMENT_NODE
          ? range.startContainer
          : range.startContainer.parentElement);
      element?.scrollIntoView({ behavior: "smooth", block: "center" });
      marks.flash(id);
    }
    // The keys come back to the list, unless a box in it took them while the jump went on, as r
    // pressed right after Space opens the reply box.
    if (!document.activeElement?.matches?.("#comments-list textarea")) {
      $("#comments-list").focus({ preventScroll: true });
    }
  }

  // From its mark on a page or beside a line a card opens the same way it does from the list:
  // whole, and at the foot of the box when it sits at the foot of the list (panel-room.js).
  // Centred, a tall card at the foot was cut off below and the reader scrolled after every open.
  // The sidebar opens first, so the card is measured where it shows.
  function openComment(id) {
    if ($(".layout").classList.contains("sidebar-collapsed")) setSidebarCollapsed(false);
    return showComment(id);
  }

  return {
    showComment: showCommentPlace,
    // Words on the page take no keys from K: the page shows them, and the keys stay with the list.
    enterComment(comment) {
      if (comment.anchor.kind === "source") {
        openSourceLocation(comment.anchor).catch((error) => alert(`Could not open source: ${error.message}`));
      } else {
        showCommentPlace(comment).catch((error) => console.error(error));
      }
    },
    openComment,
    takeComment(id) {
      showTab("comments");
      openComment(id).catch((error) => console.error(error));
      $("#comments-list").focus({ preventScroll: true });
    },
    // The place in the edit file the selected words come from, selected in the editor beside the
    // Preview, in Split.
    async showInSource(place) {
      if (workspace.view() !== "split") await workspace.show("split");
      if (!(await source.load(false))) return;
      source.showPlace(place);
    },
    // The words a stretch of the file shows, found on the pages beside the editor in Split,
    // scrolled to and marked a moment.
    async showWherePrinted(shown) {
      if (workspace.view() !== "split") {
        await workspace.show("split");
        // The Preview takes its new width before it is scrolled and marked.
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      }
      const found = anchors.rangeFromShown(shown);
      if (found === null) throw new Error("the pages do not show these words or the words around them");
      const node = found.startContainer;
      // At once: a smooth scroll in Safari came late, or stopped short, when one place followed
      // another.
      (node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement)
        ?.scrollIntoView({ behavior: "instant", block: "center" });
      marks.showRange(found);
    },
  };
}
