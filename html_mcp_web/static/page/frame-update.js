// A frame brought to a new revision of its artifact by changing only the pages that differ. An
// edit changes a page or a few. The pages of the new revision that differ from those of the
// document a frame shows are put in their place, and the rest of the document is left as it is.
// Loading the whole deck again parsed and drew every page and ran the deck's scripts over all of
// them, on the thread the review page runs on: the page, scrolling included, was held for seconds
// on every edit, and twice with the previews open. A change outside the pages (the head, the
// deck's scripts), or a document whose scripts do not say how they set up one page, loads the
// whole document as before.
//
// updateFrame(frame, url, canPatch, patch, whole) brings `frame` to the document at `url`: it
// reads the document shown and the one wanted, and hands both to patch(doc, shown, next) while
// canPatch() still holds, or calls whole() when the frame has to load the document whole. One
// update runs at a time in a frame, and one with a later revision waiting behind it is passed
// over. changePages(doc, shown, next) puts the pages of `next` that differ from those of `shown`
// into `doc`, the document made from `shown`, and gives { removed, added }, or null, with the
// document untouched, when it has to be loaded whole. This module keeps the documents it read and
// each frame's updates.

// Each frame's updates, as { wanted, chain }: the address it was last asked for, and the update
// that runs last.
const updates = new WeakMap();

export function updateFrame(frame, url, canPatch, patch, whole) {
  const update = updates.get(frame) ?? { wanted: null, chain: Promise.resolve() };
  updates.set(frame, update);
  update.wanted = url;
  update.chain = update.chain.then(async () => {
    if (update.wanted !== url) return;
    const doc = frame.contentDocument;
    // A document served without its digest, by a server on earlier code, cannot be read back.
    if (doc?.documentElement.dataset.htmlMcpServed === undefined) {
      whole();
      return;
    }
    let patched = false;
    try {
      const [shown, next] = await Promise.all([shownSource(doc, url), sourceAt(url)]);
      if (update.wanted !== url) return;
      patched = canPatch() && frame.contentDocument === doc && patch(doc, shown, next);
    } catch (error) {
      console.error(error);
    }
    if (!patched) whole();
  });
}

// The documents served to this page, read for comparing, by the digest the server gives each:
// the pages, each with the speaker script block after it, and the rest of the document.
const sources = new Map();

async function readSource(url) {
  const response = await fetch(url);
  if (!response.ok) return null;
  const doc = new DOMParser().parseFromString(await response.text(), "text/html");
  const holder = doc.querySelector("body > main.pages");
  const served = doc.documentElement.dataset.htmlMcpServed;
  if (holder === null || served === undefined) return null;
  doc.documentElement.removeAttribute("data-html-mcp-served");
  const units = Array.from(holder.children);
  for (const unit of units) unit.remove();
  const source = { served, outside: doc.documentElement.outerHTML, html: units.map((unit) => unit.outerHTML) };
  sources.set(served, source);
  // What the deck and the column show, and the revisions coming.
  while (sources.size > 4) sources.delete(sources.keys().next().value);
  return source;
}

// Each revision is read once, though the deck and the column both ask for it.
const sourceRequests = new Map();

function sourceAt(url) {
  if (!sourceRequests.has(url)) {
    sourceRequests.set(url, readSource(url));
    while (sourceRequests.size > 2) sourceRequests.delete(sourceRequests.keys().next().value);
  }
  return sourceRequests.get(url);
}

function shownSource(doc, url) {
  const served = doc.documentElement.dataset.htmlMcpServed;
  return sources.get(served) ?? sourceAt(`${url.split("?")[0]}?served=${served}&shared=1`);
}

export function changePages(doc, shown, next) {
  if (shown === null || next === null || shown.outside !== next.outside) return null;
  const holder = doc.querySelector("body > main.pages");
  const live = holder === null ? [] : Array.from(holder.children);
  const setups = doc.defaultView.htmlMcpPageSetup;
  if (live.length !== shown.html.length || (doc.scripts.length > 0 && !Array.isArray(setups))) return null;
  let start = 0;
  while (start < shown.html.length && start < next.html.length && shown.html[start] === next.html[start]) start += 1;
  let end = 0;
  while (end < shown.html.length - start && end < next.html.length - start
         && shown.html[shown.html.length - 1 - end] === next.html[next.html.length - 1 - end]) end += 1;
  const template = doc.createElement("template");
  template.innerHTML = next.html.slice(start, next.html.length - end).join("\n");
  // A script put in by script does not run: the page needs the document loaded whole.
  if (template.content.querySelector("script") !== null) return null;
  const removed = live.slice(start, live.length - end);
  const added = Array.from(template.content.children);
  const before = removed[0] ?? live[live.length - end] ?? null;
  for (const node of added) holder.insertBefore(node, before);
  for (const node of removed) node.remove();
  doc.documentElement.dataset.htmlMcpServed = next.served;
  for (const node of added) {
    for (const setup of setups ?? []) setup(node);
  }
  return { removed, added };
}
