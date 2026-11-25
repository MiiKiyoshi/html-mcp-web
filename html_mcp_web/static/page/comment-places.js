// What a comment is on, in words: anchorLabel(anchor), its place as its card names it;
// commentQuote(comment), the words its opened card quotes, which for a page or a box on one is the
// page's title, since a comment the agent made may not carry one, and nothing for the artifact as
// a whole; and composeAnchorText(anchor), what the new comment dialog says it is on.

import { deckPages, frameDocument, pageTitle } from "./deck-dom.js";

export function anchorLabel(anchor) {
  switch (anchor.kind) {
    case "artifact": return "artifact";
    case "text": return "text";
    case "page": return `p${anchor.number}`;
    case "area": return `p${anchor.number} area`;
    case "source": return `${anchor.file}:${anchor.line_start}${anchor.line_end === anchor.line_start ? "" : `-${anchor.line_end}`}`;
    default: throw new Error(`unknown anchor kind: ${anchor.kind}`);
  }
}

export function commentQuote({ anchor }) {
  if (anchor.kind === "artifact") return "";
  if (anchor.kind === "text" || anchor.kind === "source") return anchor.quote;
  if (anchor.title) return anchor.title;
  const page = frameDocument()?.body ? deckPages()[anchor.number - 1] : undefined;
  return page === undefined ? "" : pageTitle(page, anchor.number - 1);
}

export function composeAnchorText(anchor) {
  if (anchor.kind === "text") return anchor.quote;
  if (anchor.kind === "page") return `Page ${anchor.number}: ${anchor.title}`;
  if (anchor.kind === "area") return `A box on page ${anchor.number}: ${anchor.title}`;
  if (anchor.kind === "source") return `${anchor.file}:${anchor.line_start}\n${anchor.quote}`;
  return "Whole artifact";
}
