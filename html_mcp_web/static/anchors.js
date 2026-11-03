export function createAnchors(dependencies) {
  const { frameDocument, state } = dependencies;

  function ignoredTextNode(node) {
    const parent = node.parentElement;
    return parent === null || Boolean(parent.closest("script, style, noscript, template, .html-mcp-highlight-layer"));
  }
  
  function textSnapshot(doc) {
    const nodes = [];
    const starts = [];
    let text = "";
    // Text from different blocks reads as one word without this: a table row came out as
    // "MetricValue". The stored prefix and suffix are cut from this text, so the
    // break lands in them too, and resolution compares anchors against this same snapshot,
    // which keeps the two sides consistent.
    const blockOf = new Map();
    const nearestBlock = (element) => {
      for (let current = element; current !== null; current = current.parentElement) {
        if (blockOf.has(current)) return blockOf.get(current);
        const display = doc.defaultView.getComputedStyle(current).display;
        if (!display.startsWith("inline") && display !== "contents") {
          for (let walk = element; walk !== current; walk = walk.parentElement) blockOf.set(walk, current);
          blockOf.set(current, current);
          return current;
        }
      }
      return null;
    };
    let previousBlock = null;
    const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (ignoredTextNode(node)) continue;
      const block = nearestBlock(node.parentElement);
      if (previousBlock !== null && block !== previousBlock) text += "\n";
      previousBlock = block;
      starts.push(text.length);
      nodes.push(node);
      text += node.nodeValue;
    }
    return { nodes, starts, text };
  }
  
  function nodePath(node, root) {
    const path = [];
    let current = node;
    while (current !== root) {
      const parent = current.parentNode;
      if (parent === null) throw new Error("selection is outside the artifact body");
      path.push(Array.prototype.indexOf.call(parent.childNodes, current));
      current = parent;
    }
    return path.reverse();
  }
  
  function nodeAtPath(root, path) {
    let current = root;
    for (const index of path) {
      if (index < 0 || index >= current.childNodes.length) return null;
      current = current.childNodes[index];
    }
    return current;
  }
  
  function absoluteTextOffset(snapshot, container, offset) {
    const index = snapshot.nodes.indexOf(container);
    if (index < 0) throw new Error("selection boundary is not artifact text");
    return snapshot.starts[index] + offset;
  }

  function wholeCharacterBoundary(text, offset, side) {
    const previous = text.charCodeAt(offset - 1);
    const next = text.charCodeAt(offset);
    const splitsSurrogate = previous >= 0xD800 && previous <= 0xDBFF
      && next >= 0xDC00 && next <= 0xDFFF;
    return splitsSurrogate ? offset + (side === "after" ? 1 : -1) : offset;
  }

  function wholeCharacterSlice(text, start, end) {
    return text.slice(
      wholeCharacterBoundary(text, start, "after"),
      wholeCharacterBoundary(text, end, "before"),
    );
  }
  
  // A drag does not always stop inside a text node. Released on the edge between two
  // inline boxes, which a rendered formula is full of, the boundary is the element and the
  // offset counts its children: the anchor then has no text node to measure from, and the
  // comment button vanished on a selection the reader could see highlighted. The boundary
  // moves to the nearest text in the direction the reader was dragging.
  function textPoint(snapshot, container, offset, edge) {
    if (container.nodeType === Node.TEXT_NODE) {
      return {
        node: container,
        offset: wholeCharacterBoundary(
          container.nodeValue, offset, edge === "start" ? "before" : "after",
        ),
      };
    }
    const point = frameDocument().createRange();
    point.setStart(container, offset);
    let low = 0;
    let high = snapshot.nodes.length;
    while (low < high) {
      const middle = (low + high) >> 1;
      if (point.comparePoint(snapshot.nodes[middle], 0) < 0) low = middle + 1;
      else high = middle;
    }
    if (edge === "start") {
      const node = snapshot.nodes[low] ?? snapshot.nodes[snapshot.nodes.length - 1];
      if (node === undefined) throw new Error("selection boundary is not artifact text");
      return { node, offset: node === snapshot.nodes[low] ? 0 : node.nodeValue.length };
    }
    const node = snapshot.nodes[low - 1] ?? snapshot.nodes[0];
    if (node === undefined) throw new Error("selection boundary is not artifact text");
    return { node, offset: node === snapshot.nodes[0] && low === 0 ? 0 : node.nodeValue.length };
  }

  function captureTextAnchor(range) {
    const doc = frameDocument();
    const snapshot = textSnapshot(doc);
    const start = textPoint(snapshot, range.startContainer, range.startOffset, "start");
    const end = textPoint(snapshot, range.endContainer, range.endOffset, "end");
    const measured = doc.createRange();
    measured.setStart(start.node, start.offset);
    measured.setEnd(end.node, end.offset);
    const quote = measured.toString();
    if (!quote.trim()) throw new Error("Select artifact text before commenting")
    const startOffset = absoluteTextOffset(snapshot, start.node, start.offset);
    const endOffset = absoluteTextOffset(snapshot, end.node, end.offset);
    return {
      kind: "text",
      quote,
      prefix: wholeCharacterSlice(snapshot.text, Math.max(0, startOffset - 120), startOffset),
      suffix: wholeCharacterSlice(snapshot.text, endOffset, endOffset + 120),
      start: { path: nodePath(start.node, doc.body), offset: start.offset },
      end: { path: nodePath(end.node, doc.body), offset: end.offset },
      artifact_digest: state.artifact.artifact_digest,
    };
  }
  
  
  function normalizeWithMap(text) {
    let normalized = "";
    const map = [];
    let pendingSpace = false;
    let pendingIndex = -1;
    for (let index = 0; index < text.length; index += 1) {
      const character = text[index];
      if (/\s/u.test(character)) {
        if (normalized.length > 0) {
          pendingSpace = true;
          pendingIndex = index;
        }
        continue;
      }
      if (pendingSpace) {
        normalized += " ";
        map.push(pendingIndex);
        pendingSpace = false;
      }
      normalized += character;
      map.push(index);
    }
    return { normalized, map };
  }
  
  function allOccurrences(text, needle) {
    const result = [];
    let position = 0;
    while (position <= text.length - needle.length) {
      const found = text.indexOf(needle, position);
      if (found < 0) break;
      result.push(found);
      position = found + 1;
    }
    return result;
  }
  
  function boundaryAt(snapshot, absolute, endBoundary) {
    for (let index = 0; index < snapshot.nodes.length; index += 1) {
      const start = snapshot.starts[index];
      const length = snapshot.nodes[index].nodeValue.length;
      const limit = start + length;
      if (absolute < limit || (absolute === limit && endBoundary)) {
        return { node: snapshot.nodes[index], offset: Math.max(0, Math.min(length, absolute - start)) };
      }
    }
    const node = snapshot.nodes[snapshot.nodes.length - 1];
    return node === undefined ? null : { node, offset: node.nodeValue.length };
  }
  
  function rangeFromAbsolute(doc, snapshot, start, end) {
    const first = boundaryAt(snapshot, start, false);
    const last = boundaryAt(snapshot, end, true);
    if (first === null || last === null) return null;
    const range = doc.createRange();
    range.setStart(first.node, first.offset);
    range.setEnd(last.node, last.offset);
    return range;
  }
  
  function rangeFromPath(anchor) {
    const doc = frameDocument();
    const start = nodeAtPath(doc.body, anchor.start.path);
    const end = nodeAtPath(doc.body, anchor.end.path);
    if (start === null || end === null) return null;
    try {
      const range = doc.createRange();
      range.setStart(start, anchor.start.offset);
      range.setEnd(end, anchor.end.offset);
      return normalizeWithMap(range.toString()).normalized === normalizeWithMap(anchor.quote).normalized ? range : null;
    } catch (error) {
      return null;
    }
  }
  
  function rangeFromQuote(anchor) {
    const doc = frameDocument();
    const snapshot = textSnapshot(doc);
    const documentText = normalizeWithMap(snapshot.text);
    const quote = normalizeWithMap(anchor.quote).normalized;
    if (!quote) return null;
    const prefix = normalizeWithMap(anchor.prefix).normalized;
    const suffix = normalizeWithMap(anchor.suffix).normalized;
    const occurrences = allOccurrences(documentText.normalized, quote);
    if (occurrences.length === 0) return null;
    // Normalizing drops the space at either end of the stored context, and a selection
    // that starts or ends between words has one there: the document is read past that
    // space the same way, or the context sits one character off and never matches.
    const candidates = occurrences.map((start) => {
      const before = documentText.normalized.slice(0, start).trimEnd().slice(-prefix.length || documentText.normalized.length);
      const after = documentText.normalized.slice(start + quote.length).trimStart().slice(0, suffix.length);
      return {
        start,
        score: Number(prefix.length > 0 && before === prefix) + Number(suffix.length > 0 && after === suffix),
      };
    });
    const bestScore = Math.max(...candidates.map((candidate) => candidate.score));
    const best = candidates.filter((candidate) => candidate.score === bestScore);
    if (best.length !== 1) return null;
    // The original context is the evidence that this is the same spot. When context was
    // stored but no side matches, the quoted text is gone; a same-string match elsewhere
    // must not adopt the comment. It stays unattached and the card shows it as stale.
    if ((prefix.length > 0 || suffix.length > 0) && bestScore === 0) return null;
    const normalizedStart = best[0].start;
    const normalizedEnd = normalizedStart + quote.length - 1;
    const rawStart = documentText.map[normalizedStart];
    const rawEnd = documentText.map[normalizedEnd] + 1;
    return rangeFromAbsolute(doc, snapshot, rawStart, rawEnd);
  }
  
  // The words a stretch of the source shows, found on the pages without spacing, as the
  // server gives them. The words around them pick among repeats. Words the page shows
  // another way, such as math the source writes as TeX, give the place the words before
  // them end, or else the place the words after them begin.
  function rangeFromShown(shown) {
    const doc = frameDocument();
    if (doc === null || doc.body === null) return null;
    const snapshot = textSnapshot(doc);
    // A formula is read as the source writes it, by the TeX in its annotation alone: the
    // glyphs KaTeX draws for it would stand between the words around it and their match.
    const raw = [];
    let text = "";
    snapshot.nodes.forEach((node, index) => {
      const parent = node.parentElement;
      if (parent?.closest(".katex") && !parent.closest('annotation[encoding="application/x-tex"]')) return;
      for (let offset = 0; offset < node.nodeValue.length; offset += 1) {
        if (/\s/.test(node.nodeValue[offset])) continue;
        raw.push(snapshot.starts[index] + offset);
        text += node.nodeValue[offset];
      }
    });
    const score = (at, length) => {
      let matched = 0;
      while (matched < shown.before.length && at - matched - 1 >= 0
        && text[at - matched - 1] === shown.before[shown.before.length - matched - 1]) matched += 1;
      let ahead = 0;
      while (ahead < shown.after.length && at + length + ahead < text.length
        && text[at + length + ahead] === shown.after[ahead]) ahead += 1;
      return matched + ahead;
    };
    const best = (wanted) => {
      if (!wanted) return null;
      const found = allOccurrences(text, wanted);
      if (found.length === 0) return null;
      return found.reduce((top, at) => (score(at, wanted.length) > score(top, wanted.length) ? at : top));
    };
    const at = best(shown.quote);
    if (at !== null) {
      // TeX found in a formula's hidden annotation stands for the formula as drawn.
      const range = rangeFromAbsolute(doc, snapshot, raw[at], raw[at + shown.quote.length - 1] + 1);
      const formula = (node) => (node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement)?.closest(".katex");
      const first = formula(range.startContainer);
      const last = formula(range.endContainer);
      if (first) range.setStartBefore(first);
      if (last) range.setEndAfter(last);
      return range;
    }
    const lead = shown.before.slice(-24);
    const before = best(lead);
    if (before !== null) {
      const end = raw[before + lead.length - 1] + 1;
      return rangeFromAbsolute(doc, snapshot, end, end);
    }
    const trail = shown.after.slice(0, 24);
    const after = best(trail);
    return after === null ? null : rangeFromAbsolute(doc, snapshot, raw[after], raw[after]);
  }

  function resolveAnchor(anchor) {
    return rangeFromPath(anchor) ?? rangeFromQuote(anchor);
  }

  // Where the reader was pointing when they wrote a comment whose text has since gone.
  // The stored path is walked as deep as the page still allows, so a rewritten sentence
  // gives back the paragraph and a rewritten paragraph the block around it; a page that
  // is gone altogether gives back nothing, since a place off the pages is no place.
  function lastKnownPlace(anchor) {
    const doc = frameDocument();
    if (doc === null || doc.body === null) return null;
    for (let depth = anchor.start.path.length; depth > 0; depth--) {
      const node = nodeAtPath(doc.body, anchor.start.path.slice(0, depth));
      if (node === null) continue;
      const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
      if (element !== null && element.closest("section.page") !== null) return element;
    }
    return null;
  }

  return { captureTextAnchor, resolveAnchor, lastKnownPlace, rangeFromShown };
}
