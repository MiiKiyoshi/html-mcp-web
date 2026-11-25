// An opened card brought whole into the comment list. A card opened at the foot of the list
// unfolds below the fold, and the reader had to scroll after every open to read what they had just
// asked for. The list scrolls by what the card overhangs, so the whole of it shows; a card taller
// than the list is brought to the top instead, which is as much of it as there is room for. Under
// the artifact, on a phone, the comments get a slice of the screen, and a thread opened there is
// usually taller than the slice: scrolling cannot show what does not fit, so the panel takes the
// room the card needs instead, up to what its bar allows, and the artifact keeps the rest. Beside
// the artifact it is already full height, so there is nothing to take.
//
// createPanelRoom takes isOpen(id), whether a card is open, and setHeight(pixels), which sets the
// panel's height under the artifact (panel-grips.js). It gives reveal(id).

import { $ } from "../shared/dom.js";

export function createPanelRoom({ isOpen, setHeight }) {
  function growFor(wanted) {
    const layout = $(".layout");
    const sidebar = $("#sidebar");
    const list = $("#comments-list");
    const stacked = Math.abs(sidebar.getBoundingClientRect().width
      - layout.getBoundingClientRect().width) < 2;
    if (!stacked) return;
    const shortfall = wanted - list.getBoundingClientRect().height;
    if (shortfall <= 0) return;
    setHeight(sidebar.getBoundingClientRect().height + shortfall);
  }

  // The opened card is brought into the list's box: its foot at the box's foot when it fits, its
  // head at the box's head when it does not. Done at once, then again a frame later and once more
  // shortly after: the measurement taken inside the click is not always the one the engine paints
  // (Safari laid the list out again after the click), and the reader was left to scroll after
  // opening the last card of the list.
  function reveal(id) {
    const settle = () => {
      const list = $("#comments-list");
      const card = Array.from(list.querySelectorAll("[data-comment-id]")).find(
        (node) => node.dataset.commentId === id);
      if (card === undefined || !isOpen(id)) return;
      const margin = 8;
      growFor(card.getBoundingClientRect().height + margin * 2);
      const listBox = list.getBoundingClientRect();
      const cardBox = card.getBoundingClientRect();
      const overhang = cardBox.bottom - (listBox.bottom - margin);
      const above = listBox.top + margin - cardBox.top;
      if (cardBox.height > listBox.height - margin * 2 || above > 0) {
        list.scrollTop += cardBox.top - listBox.top - margin;
      } else if (overhang > 0) {
        list.scrollTop += overhang;
      }
      // On the record when the page is traced, for a device that cannot be watched.
      window.htmlMcpTrace?.(`reveal ${id} card=${Math.round(cardBox.top)}..${Math.round(cardBox.bottom)}`
        + ` list=${Math.round(listBox.top)}..${Math.round(listBox.bottom)} over=${Math.round(overhang)}`
        + ` scroll=${Math.round(list.scrollTop)}/${list.scrollHeight - list.clientHeight}`);
    };
    settle();
    requestAnimationFrame(settle);
    setTimeout(settle, 150);
  }

  return { reveal };
}
