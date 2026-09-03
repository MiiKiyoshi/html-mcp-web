import { createPresentation } from "./presentation.js";
import { createLayoutChecks } from "./layout-check.js";
import { createAnchors } from "./anchors.js";
import { createComments } from "./comments.js";

const $ = (selector) => document.querySelector(selector);

const state = {
  project: null,
  artifactId: null,
  artifact: null,
  comments: [],
  revision: null,
  loadedRevision: null,
  pendingAnchor: null,
  selectionAnchor: null,
  composeSubmitting: false,
  expanded: new Set(),
  picked: new Set(),
  focusedCommentId: null,
  activeForm: null,
  editingEntry: null,
  unattached: new Set(),
  pendingView: null,
  ws: null,
  renderFrame: null,
  layoutFrame: null,
  layoutCheckError: null,
  selectionPointerDown: false,
  selectionSettle: null,
  pageFrame: null,
  currentPage: null,
  slideShow: false,
  presentationPointer: null,
  presentationWheelEvents: [],
  presentationLastWheelStep: 0,
  suppressPresentationClick: false,
  draggingPanel: false,
  panelDraggedAt: -Infinity,
  artifactZoom: 1,
  pinch: null,
  pinchSettle: null,
  settledScroll: null,
};

function artifactBase() {
  return `/artifacts/${encodeURIComponent(state.artifactId)}`;
}

function renderArtifactTabs() {
  const tabs = $("#artifact-tabs");
  clear(tabs);
  for (const [artifactId, artifact] of Object.entries(state.project.artifacts)) {
    tabs.appendChild(h("button", {
      type: "button",
      class: `artifact-tab${artifactId === state.artifactId ? " active" : ""}`,
      text: artifact.label,
      onclick: () => selectArtifact(artifactId),
    }));
  }
}

async function selectArtifact(artifactId) {
  if (artifactId === state.artifactId) return;
  state.artifactId = artifactId;
  localStorage.setItem("htmlMcpArtifact", artifactId);
  state.artifact = state.project.artifacts[artifactId];
  state.revision = state.artifact.revision;
  state.loadedRevision = null;
  state.comments = [];
  state.expanded.clear();
  state.unattached.clear();
  state.currentPage = null;
  renderArtifactTabs();
  updateArtifactLinks();
  updateLayoutUi();
  await refreshComments();
  loadArtifact(false);
}

function updateArtifactLinks() {
  $("#main-file").textContent = state.artifact.main_file;
  // The tab carries the file being reviewed, so several projects open at once stay
  // apart in the browser's tab strip.
  document.title = state.artifact.main_file.split("/").pop();
  $("#download-pdf-btn").href = `${artifactBase()}/download/pdf`;
  $("#download-pptx-btn").hidden = state.artifact.layout !== "slides";
}

// The pptx is built on the server while the button shows it is busy; the file then
// downloads like the PDF does. A plain link would leave the button silent for the
// half minute the export takes.
async function downloadPptx() {
  const button = $("#download-pptx-btn");
  if (button.disabled) return;
  button.disabled = true;
  button.classList.add("busy");
  button.textContent = "PPTX\u2026";
  try {
    const response = await fetch(`${artifactBase()}/download/pptx`);
    if (!response.ok) throw new Error(await response.text());
    const blob = await response.blob();
    const name = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "")?.[1] || "slides.pptx";
    const url = URL.createObjectURL(blob);
    const link = h("a", { href: url, download: name });
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    button.textContent = "PPTX";
  } catch (error) {
    // A 404 here means the review server predates the export: restart the MCP process.
    button.textContent = "PPTX failed";
    button.title = String(error.message || error);
    setTimeout(() => { button.textContent = "PPTX"; button.title = "Export the deck as an editable pptx"; }, 6000);
  } finally {
    button.disabled = false;
    button.classList.remove("busy");
  }
}

function h(tag, props = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") element.className = value;
    else if (key === "text") element.textContent = value;
    else if (key === "data") Object.assign(element.dataset, value);
    else if (key.startsWith("on")) element.addEventListener(key.slice(2), value);
    else if (value !== null && value !== undefined) element.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined) continue;
    element.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return element;
}

function clear(node) {
  node.replaceChildren();
}

async function responseError(response) {
  const text = await response.text();
  return text || `${response.status} ${response.statusText}`;
}

async function fetchJson(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(await responseError(response));
  return response.status === 204 ? null : response.json();
}

function frameWindow() {
  return $("#artifact-frame").contentWindow;
}

function frameDocument() {
  return $("#artifact-frame").contentDocument;
}

function artifactPages() {
  return Array.from(frameDocument().querySelectorAll("body > main.pages > section.page"));
}

function pageTitle(page, index) {
  const heading = page.querySelector("h1, h2, h3");
  const title = page.dataset.title || heading?.textContent || "";
  return title.trim().replace(/\s+/g, " ") || `Page ${index + 1}`;
}

function visiblePageNumber() {
  const pages = artifactPages();
  if (state.slideShow) {
    return pages.length === 0 ? null : state.currentPage || 1;
  }
  const viewportHeight = frameWindow().innerHeight;
  let visibleNumber = pages.length === 0 ? null : 1;
  let visibleHeight = -1;
  for (const [index, page] of pages.entries()) {
    const rect = page.getBoundingClientRect();
    const height = Math.max(0, Math.min(rect.bottom, viewportHeight) - Math.max(rect.top, 0));
    if (height > visibleHeight) {
      visibleHeight = height;
      visibleNumber = index + 1;
    }
  }
  return visibleNumber;
}

function jumpToPage(number) {
  artifactPages()[number - 1]?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderPages() {
  const list = $("#pages-list");
  clear(list);
  for (const [index, page] of artifactPages().entries()) {
    const number = index + 1;
    const title = pageTitle(page, index);
    list.appendChild(h("div", { class: `page-nav-row${state.currentPage === number ? " active" : ""}` },
      h("button", {
        type: "button",
        class: "page-nav-item",
        data: { page: String(number) },
        title: `Go to page ${number}`,
        onclick: () => jumpToPage(number),
      },
      h("span", { class: "page-number", text: String(number) }),
      h("span", { class: "page-title", text: title })),
      actionButton("+ comment", () => openCompose({ kind: "page", number, title }), "comment-page-btn")));
  }
}

function updateCurrentPage() {
  const number = visiblePageNumber();
  if (number === state.currentPage) return;
  state.currentPage = number;
  if (state.slideShow) {
    for (const [index, page] of artifactPages().entries()) {
      page.classList.toggle("html-mcp-current-page", index + 1 === state.currentPage);
    }
    updatePresentationControls();
  }
  renderPages();
}

function scheduleCurrentPage() {
  const win = frameWindow();
  if (state.pageFrame !== null) win.cancelAnimationFrame(state.pageFrame);
  state.pageFrame = win.requestAnimationFrame(() => {
    state.pageFrame = null;
    updateCurrentPage();
  });
}

function installArtifactLayout() {
  const doc = frameDocument();
  if (doc.documentElement.dataset.htmlMcpLayout !== state.artifact.layout) {
    throw new Error("artifact layout does not match project configuration");
  }
  updatePageScale();
}

function updatePageScale() {
  const doc = frameDocument();
  const page = state.slideShow
    ? doc.querySelector("body > main.pages > section.page.html-mcp-current-page")
    : doc.querySelector("body > main.pages > section.page");
  if (page === null) return;
  // The width the page is actually given, measured rather than guessed from the window:
  // the guess put a phone's margin at 8px where the stylesheet spends 48, so the page was
  // fitted 40px too wide and hung off the right while the left kept its margin.
  const holder = page.parentElement;
  const availableWidth = holder.clientWidth || frameWindow().innerWidth;
  const widthScale = availableWidth / page.offsetWidth;
  const fitted = state.slideShow
    ? Math.min(widthScale, frameWindow().innerHeight / page.offsetHeight)
    : Math.min(1, widthScale);
  const scale = state.slideShow ? fitted : fitted * state.artifactZoom;
  const root = frameDocument().documentElement;
  root.style.setProperty("--html-mcp-page-scale", String(scale));
  root.style.setProperty("--html-mcp-zoom", String(state.slideShow ? 1 : state.artifactZoom));
  // The room a drawn-smaller block gives back depends on its own height, and only the
  // template knows how tall a script block is.
  const script = doc.querySelector("body > main.pages > .script-block");
  if (script !== null) root.style.setProperty("--html-mcp-script-height", `${script.offsetHeight}px`);
}

let scheduleLayoutCheck = () => {};
const presentation = createPresentation(state, {
  $,
  artifactPages,
  frameDocument,
  frameWindow,
  hideSelectionButton,
  renderPages,
  scheduleLayoutCheck: () => scheduleLayoutCheck(),
  updatePageScale,
  visiblePageNumber,
});
const activateSlideShow = presentation.activate;
const handlePresentationClick = presentation.handleClick;
const handlePresentationKeydown = presentation.handleKeydown;
const handlePresentationPointerDown = presentation.handlePointerDown;
const handlePresentationPointerUp = presentation.handlePointerUp;
const handlePresentationWheel = presentation.handleWheel;
const movePresentationPage = presentation.movePage;
const setPresentationPage = presentation.setPage;
const syncFullscreenMode = presentation.syncFullscreenMode;
const toggleFullscreen = presentation.toggleFullscreen;
const updatePresentationControls = presentation.updateControls;

const layoutChecks = createLayoutChecks({
  $,
  artifactBase,
  artifactPages,
  clear,
  fetchJson,
  frameDocument,
  frameWindow,
  h,
  state,
});
scheduleLayoutCheck = layoutChecks.scheduleLayoutCheck;
const updateLayoutUi = layoutChecks.updateLayoutUi;

const anchors = createAnchors({ frameDocument, state });
const captureTextAnchor = anchors.captureTextAnchor;
const resolveAnchor = anchors.resolveAnchor;

// The whole of what the reader dragged over, as one range. A drag usually leaves one, but
// KaTeX draws a fraction or a subscript as an inline table (.vlist is a table-cell), and a
// drag that crosses those cells puts Firefox into cell selection, which leaves one range
// per cell. Taking the outermost boundaries reads that back as the span it looked like.
function selectionSpan(selection) {
  const Range = frameWindow().Range;
  const span = selection.getRangeAt(0).cloneRange();
  for (let index = 1; index < selection.rangeCount; index += 1) {
    const other = selection.getRangeAt(index);
    if (span.compareBoundaryPoints(Range.START_TO_START, other) > 0) {
      span.setStart(other.startContainer, other.startOffset);
    }
    if (span.compareBoundaryPoints(Range.END_TO_END, other) < 0) {
      span.setEnd(other.endContainer, other.endOffset);
    }
  }
  return span;
}

// Two fingers on the artifact zoom the artifact alone; the controls and the comments
// stay their size. Every touch on the artifact is answered here, so the browser cannot
// take a gesture halfway through and turn a pinch into a scroll, which is what made an
// earlier reading of it cut out. A finger that stays put still belongs to the browser,
// because that is a reader holding a word.
function installArtifactZoom() {
  const doc = frameDocument();
  // A gesture on the document this one replaces is over, whatever its fingers do next.
  state.pinch = null;
  for (const kind of ["touchstart", "touchmove", "touchend", "touchcancel"]) {
    doc.addEventListener(kind, handleArtifactTouch, { passive: false, capture: true });
  }
  doc.addEventListener("wheel", handleArtifactWheel, { passive: false, capture: true });
  for (const kind of ["gesturestart", "gesturechange", "gestureend"]) {
    doc.addEventListener(kind, handleArtifactGesture, { passive: false, capture: true });
  }
}

// Safari sends two fingers as a gesture of its own, with the scale since the gesture
// began, and on a Mac that gesture is all a trackpad pinch sends: refused and left at
// that, the pinch zoomed nothing there. So the gesture drives the zoom, unless touches
// already do, as on a phone, where the gesture comes beside them and is only refused.
// Refusing it matters either way: left to run, Safari's own zoom moved the window under
// the settled layout and the deck appeared somewhere else the moment the fingers lifted.
function handleArtifactGesture(event) {
  zoomFromGesture(event, { x: event.clientX, y: event.clientY });
}

function handleViewerGesture(event) {
  if (frameDocument() === null) {
    event.preventDefault();
    return;
  }
  const frame = $("#artifact-frame").getBoundingClientRect();
  zoomFromGesture(event, { x: frame.width / 2, y: frame.height / 2 });
}

function zoomFromGesture(event, point) {
  event.preventDefault();
  if (state.slideShow) return;
  const pinch = state.pinch;
  if (pinch !== null && pinch.driver === "touch") return;
  if (event.type === "gesturestart") {
    if (pinch !== null) settlePinch();
    state.settledScroll = null;
    state.pinch = beginPinch(1, point, "gesture");
    return;
  }
  if (pinch === null || pinch.driver !== "gesture") return;
  if (event.type === "gesturechange") {
    carryPinch(pinch, pinch.startZoom * event.scale, point);
    return;
  }
  settlePinch();
}

// A trackpad pinch reaches the page as a wheel event holding ctrl, which is also what a
// mouse sends under the key each desktop zooms with: ctrl on Windows and Linux, command
// on a Mac. The pointer is the fixed point, as the point between two fingers is.
function handleArtifactWheel(event) {
  zoomFromWheel(event, { x: event.clientX, y: event.clientY });
}

// Over the rest of the viewer, the comments or the bar, the same pinch zooms the artifact
// about its middle. Left to the browser there, it zoomed the whole page, comments and
// all, while the artifact kept a zoom of its own, and the two ran side by side.
function handleViewerWheel(event) {
  if (frameDocument() === null) return;
  const frame = $("#artifact-frame").getBoundingClientRect();
  zoomFromWheel(event, { x: frame.width / 2, y: frame.height / 2 });
}

function zoomFromWheel(event, point) {
  state.settledScroll = null;
  if (!(event.ctrlKey || event.metaKey) || state.slideShow) return;
  event.preventDefault();
  // A gesture that drives the zoom is the whole gesture: a wheel beside it is not a step.
  if (state.pinch !== null && state.pinch.driver === "gesture") return;
  if (state.pinch === null) state.pinch = beginPinch(1, point, "wheel");
  const pinch = state.pinch;
  if (pinch === null) return;
  // Fingers spreading on a trackpad arrive as many small steps, and the size follows the
  // distance they travel, at the rate a browser zooms its own pages by: a pinch here
  // reaches as far as the same pinch anywhere else. A mouse sends one large step per
  // notch, where that rate would multiply the size by e, so a notch has a step of its
  // own. Both multiply, so a step moves the same share of the size at any zoom and
  // zooming in then out by the same amount lands back where it started.
  const notch = event.deltaMode !== WheelEvent.DOM_DELTA_PIXEL || Math.abs(event.deltaY) >= 40;
  const factor = notch
    ? (event.deltaY < 0 ? 1.25 : 1 / 1.25)
    : Math.exp(-event.deltaY / 100);
  carryPinch(pinch, pinch.zoom * factor, point);
  // A wheel has no lift to end on, so the gesture ends where the steps stop.
  if (state.pinchSettle !== null) clearTimeout(state.pinchSettle);
  state.pinchSettle = setTimeout(settlePinch, 150);
}

// The reader's zoom is the page's own size, not a transform laid over it. A transform
// creates no scrollable room, so whatever it pushed past an edge could not be reached:
// zoomed in, the left never came back and the first page lost its top. The factor goes
// into the scale the pages are laid out at, whose margins grow the boxes with it, so the
// document is genuinely larger and scrolls in both directions like any other.
//
// That layout is settled once, when the gesture ends. While it runs, the holder of the
// pages is carried by one transform the compositor applies, which lays nothing out and
// paints nothing anew: laying the pages out again on every step, and rebuilding the
// highlight boxes each time, was work a phone could not finish between two frames, and
// the zoom stuttered in step with it.
//
// One finger is the browser's, whether it holds a word or scrolls: the layout is a
// document of its own size and scrolls like any other, with the browser's smoothness and
// momentum. Scrolling it ourselves, by the finger's movement, stuttered, and doubled the
// distance whenever the browser had begun a scroll of its own before we took over.
function handleArtifactTouch(event) {
  const touches = Array.from(event.touches);
  if (event.type === "touchstart") state.settledScroll = null;
  if (event.type === "touchend" || event.type === "touchcancel") {
    if (touches.length < 2 && state.pinch !== null) settlePinch();
    return;
  }
  if (touches.length < 2) return;
  {
    const [first, second] = touches;
    const span = Math.hypot(first.clientX - second.clientX, first.clientY - second.clientY);
    const middle = { x: (first.clientX + second.clientX) / 2, y: (first.clientY + second.clientY) / 2 };
    if (state.pinch === null || event.type === "touchstart") {
      if (state.pinch !== null) settlePinch();
      state.pinch = beginPinch(span, middle, "touch");
      // A second finger is never a reader holding a word, so this one is taken from the
      // browser at once: told only at the first move, it has already begun a zoom of its
      // own, and two zooms ran on the same fingers.
      if (state.pinch !== null) event.preventDefault();
      return;
    }
    event.preventDefault();
    const pinch = state.pinch;
    carryPinch(pinch, pinch.startZoom * (span / pinch.startSpan), middle);
  }
}

// The holder scaled about its own corner and shifted so that what the gesture started on
// is under the fixed point now, held within what the settled layout can reach: a page
// narrower than its holder sits centred with no scroll to move it, a wider one scrolls
// between its two edges, and the deck scrolls between the document's top and bottom
// margins. Shown anywhere else, the deck jumped to the nearest reachable place the moment
// the gesture ended.
function carryPinch(pinch, zoom, at) {
  pinch.zoom = Math.min(4, Math.max(0.5, zoom));
  pinch.middle = at;
  const grown = pinch.zoom / pinch.startZoom;
  const room = pinch.room;
  // What is visible is measured as it stands, not as it stood: a phone hides its address
  // bar partway through a gesture, and a deck held within the room it had before that
  // was outside the room it had after.
  const view = frameDocument().documentElement;
  room.viewWidth = view.clientWidth;
  room.viewHeight = view.clientHeight;
  const shift = {
    x: at.x - pinch.origin.x - grown * pinch.focal.x,
    y: at.y - pinch.origin.y - grown * pinch.focal.y,
  };
  const pageWidth = grown * room.pageWidth;
  const pageAtZero = room.left - pinch.origin.x - grown * room.pageOffset;
  shift.x = pageWidth <= room.width
    ? pageAtZero + (room.width - pageWidth) / 2
    : Math.min(pageAtZero, Math.max(
        pageAtZero - (room.left + pageWidth + room.right - room.viewWidth), shift.x));
  const holderAtZero = room.top - pinch.origin.y;
  shift.y = Math.min(holderAtZero, Math.max(
    holderAtZero - (room.top + grown * room.height + room.bottom - room.viewHeight), shift.y));
  pinch.holder.style.transform = `translate(${shift.x}px, ${shift.y}px) scale(${grown})`;
}

// What the gesture keeps of its start: the holder's corner and the point between the
// fingers relative to it, for carrying the holder; that point in the coordinates of the
// page it lies on, which no zoom changes, for putting it back under the fingers once the
// layout is settled; and the room the settled layout will have, read off the document
// now, since the holder grows by the zoom alone and the margins around it not at all.
function beginPinch(span, middle, driver) {
  if (span === 0 || state.slideShow) return null;
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
  // The document's scrollable size follows the carried holder, and shrunk by a zoom out
  // it let the browser pull the scroll position back in the middle of the gesture. A dot
  // pinned at the document's far corner holds that size until the layout settles.
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
  // The comment button is placed by the selection and stays where it was placed while
  // the deck under it is carried; it is placed again once the deck has settled.
  hideSelectionButton();
  return {
    driver,
    startSpan: span,
    startZoom: state.artifactZoom,
    zoom: state.artifactZoom,
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
  const pinch = state.pinch;
  state.pinch = null;
  if (state.pinchSettle !== null) clearTimeout(state.pinchSettle);
  state.pinchSettle = null;
  pinch.holder.style.transform = "";
  pinch.holder.style.transformOrigin = "";
  pinch.holder.style.willChange = "";
  if (pinch.zoom === pinch.startZoom) {
    pinch.keeper.remove();
    setTimeout(showSelectionButton, 60);
    return;
  }
  const win = frameWindow();
  const page = pinch.page;
  state.artifactZoom = pinch.zoom;
  applyArtifactZoom();
  page.getBoundingClientRect();
  // Safari keeps the scroll position anchored to an element and, after a layout, moves
  // the position by what that element moved. A layout that changes transforms is left
  // alone, so the zoom above leaves the anchor's recorded place where the old layout had
  // it, and the next layout of any kind moved the deck by the zoom's whole displacement:
  // the highlight boxes redrawn a frame later sent it somewhere else after the fingers
  // had lifted. The dot's removal is that next layout, made here, before the position is
  // set; and it is set absolutely, so nothing already applied is applied again. The
  // property that turns the anchoring off is not implemented there.
  pinch.keeper.remove();
  frameDocument().body.getBoundingClientRect();
  const box = page.getBoundingClientRect();
  const ratio = box.width / page.offsetWidth;
  win.scrollTo(win.scrollX + box.left + pinch.local.x * ratio - pinch.middle.x,
               win.scrollY + box.top + pinch.local.y * ratio - pinch.middle.y);
  // What the browser moves on its own in the moment after is put back; the reader's own
  // next touch or wheel ends the watch.
  state.settledScroll = { x: win.scrollX, y: win.scrollY, until: performance.now() + 400 };
  // After the scroll that follows, which hides the button as any scroll does.
  setTimeout(showSelectionButton, 60);
}

// The page under a point, or the nearest one when the point is in a gap.
function pageNear(point) {
  const hit = frameDocument().elementFromPoint(point.x, point.y);
  const under = hit === null ? null : hit.closest("body > main.pages > section.page");
  if (under !== null) return under;
  let nearest = null;
  let distance = Infinity;
  for (const page of artifactPages()) {
    const box = page.getBoundingClientRect();
    const away = Math.max(box.top - point.y, point.y - box.bottom, 0);
    if (away < distance) {
      distance = away;
      nearest = page;
    }
  }
  return nearest;
}

function applyArtifactZoom() {
  $("#zoom-reset-btn").classList.toggle("hidden", Math.abs(state.artifactZoom - 1) < 0.01);
  updatePageScale();
  scheduleHighlights();
}

// The way back from a zoom keeps the reader's place: laid out again with the scroll
// position left as it was, the deck showed some other part of itself, further down after
// a zoom in and further up after a zoom out. What sits at the middle of the window is
// the fixed point, and the settle a pinch ends with puts it back there.
function resetArtifactZoom() {
  if (state.pinch !== null) settlePinch();
  if (state.artifactZoom === 1) return;
  const view = frameDocument().documentElement;
  const middle = { x: view.clientWidth / 2, y: view.clientHeight / 2 };
  const pinch = beginPinch(1, middle, "wheel");
  if (pinch === null) {
    state.artifactZoom = 1;
    applyArtifactZoom();
    return;
  }
  pinch.zoom = 1;
  state.pinch = pinch;
  settlePinch();
}

function showSelectionButton() {
  const selection = frameWindow().getSelection();
  const button = $("#selection-comment-btn");
  // While a gesture carries the deck the button stays out of it: the selection's own
  // settle, timed from before the gesture, would otherwise bring it back mid-way.
  if (state.pinch !== null) return;
  if (document.fullscreenElement === $("#artifact-pane")) {
    state.selectionAnchor = null;
    button.classList.add("hidden");
    return;
  }
  if (selection === null || selection.rangeCount === 0) {
    state.selectionAnchor = null;
    button.classList.add("hidden");
    return;
  }
  const range = selectionSpan(selection);
  if (range.collapsed) {
    state.selectionAnchor = null;
    button.classList.add("hidden");
    return;
  }
  try {
    state.selectionAnchor = captureTextAnchor(range);
  } catch (error) {
    state.selectionAnchor = null;
    button.classList.add("hidden");
    return;
  }
  // The same geometry the highlight uses, so the button meets the letters that were
  // grabbed rather than the whole svg label they sit in.
  const marks = selectionRects(range);
  const rect = marks.length === 0 ? range.getBoundingClientRect() : {
    left: Math.min(...marks.map((mark) => mark.left)),
    top: Math.min(...marks.map((mark) => mark.top)),
    bottom: Math.max(...marks.map((mark) => mark.top + mark.height)),
  };
  const iframe = $("#artifact-frame");
  const pane = $("#artifact-pane");
  button.classList.remove("hidden");
  // Under the selection and lined up with its left edge. The button's own size is read
  // rather than assumed, so the pane's edges can hold it: a selection near the bottom puts
  // it above instead, and one near a side slides it along until the whole button fits.
  const gap = 8;
  const width = button.offsetWidth;
  const height = button.offsetHeight;
  const under = iframe.offsetTop + rect.bottom + gap;
  const above = iframe.offsetTop + rect.top - height - gap;
  const wanted = under + height > pane.clientHeight - gap && above >= gap ? above : under;
  const left = iframe.offsetLeft + rect.left;
  button.style.left = `${Math.max(gap, Math.min(left, pane.clientWidth - width - gap))}px`;
  button.style.top = `${Math.max(gap, Math.min(wanted, pane.clientHeight - height - gap))}px`;
}

function hideSelectionButton() {
  $("#selection-comment-btn").classList.add("hidden");
}

// A Range inside an <svg> does not report the characters it holds. Selecting nine letters
// of a label gave the whole <text> element's box (218px wide where the letters were 143),
// and selecting from the middle gave an empty rect, so a highlight covered the whole label
// and the comment button sat away from what was grabbed. The element numbers its own
// characters and can place each one, which is where the letters actually are. The shapes a
// touch screen's long press and handle drag produce are wider than one text node: element
// containers and spans across tspans, and the first cut of this handled neither, so those
// fell back to the misplaced native box. A character belongs to the selection when the
// range intersects its node and its offset lies inside; the owning <text> indexes every
// descendant character, so one element places them all, line by line.
function svgSelectionRects(range) {
  let ancestor = range.commonAncestorContainer;
  if (ancestor.nodeType === Node.TEXT_NODE) ancestor = ancestor.parentElement;
  if (ancestor === null || ancestor.namespaceURI !== "http://www.w3.org/2000/svg") return null;
  const enclosing = ancestor.closest("text");
  const roots = enclosing !== null ? [enclosing]
    : Array.from(ancestor.querySelectorAll("text")).filter((text) => range.intersectsNode(text));
  if (roots.length === 0) return null;
  const rects = [];
  for (const root of roots) {
    if (typeof root.getExtentOfChar !== "function") return null;
    const unit = extentUnit(root);
    const toScreen = textMapping(root);
    if (unit === null || toScreen === null) return null;
    const walker = frameDocument().createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let base = 0;
    let band = null;
    let node;
    while ((node = walker.nextNode()) !== null) {
      const length = node.nodeValue.length;
      if (range.intersectsNode(node)) {
        const from = range.startContainer === node ? Math.min(range.startOffset, length) : 0;
        const to = range.endContainer === node ? Math.min(range.endOffset, length) : length;
        for (let index = from; index < to; index += 1) {
          let box;
          try {
            box = root.getExtentOfChar(base + index);
          } catch (error) {
            return null;
          }
          let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
          for (const [x, y] of [[box.x, box.y], [box.x + box.width, box.y],
                                [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]]) {
            const [screenX, screenY] = toScreen(x * unit, y * unit);
            left = Math.min(left, screenX); right = Math.max(right, screenX);
            top = Math.min(top, screenY); bottom = Math.max(bottom, screenY);
          }
          // One rect per line: a character on a new tspan line starts a new band rather
          // than stretching the previous one down and across. Lines set tight overlap by
          // a sliver, so joining takes half the character's height, not a mere touch.
          if (band !== null
              && Math.min(bottom, band.bottom) - Math.max(top, band.top) > (bottom - top) / 2) {
            band.left = Math.min(band.left, left);
            band.right = Math.max(band.right, right);
            band.top = Math.min(band.top, top);
            band.bottom = Math.max(band.bottom, bottom);
          } else {
            band = { left, top, right, bottom };
            rects.push(band);
          }
        }
      }
      base += length;
    }
  }
  if (rects.length === 0) return null;
  return rects.map((box) => ({ ...box, width: box.right - box.left, height: box.bottom - box.top }));
}

// Where a point of a text's user space falls on screen. Two boxes of the text are right
// in every engine: its own box in user space (getBBox) and its box on screen
// (getBoundingClientRect). The screen matrix is used where it carries the one onto the
// other, which keeps a turned label right; where it does not, as in Safari, whose matrix
// leaves out the CSS scale the page is drawn at and so put the box further off the more
// the page was zoomed, the two boxes give the mapping themselves.
function textMapping(root) {
  const box = root.getBBox();
  const rect = root.getBoundingClientRect();
  const ctm = root.getScreenCTM();
  if (ctm !== null) {
    const through = (x, y) => [ctm.a * x + ctm.c * y + ctm.e, ctm.b * x + ctm.d * y + ctm.f];
    let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
    for (const [x, y] of [[box.x, box.y], [box.x + box.width, box.y],
                          [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]]) {
      const [screenX, screenY] = through(x, y);
      left = Math.min(left, screenX); right = Math.max(right, screenX);
      top = Math.min(top, screenY); bottom = Math.max(bottom, screenY);
    }
    if (Math.abs(left - rect.left) < 1.5 && Math.abs(top - rect.top) < 1.5
        && Math.abs(right - rect.right) < 1.5 && Math.abs(bottom - rect.bottom) < 1.5) {
      return through;
    }
  }
  if (box.width === 0 || box.height === 0) return null;
  const scaleX = rect.width / box.width;
  const scaleY = rect.height / box.height;
  return (x, y) => [rect.left + (x - box.x) * scaleX, rect.top + (y - box.y) * scaleY];
}

// How many user-space units one unit of a character extent is: the height the extents
// of all the characters span, against the height of the text's own box. Chromium hands
// the extents back divided by the scale the page is drawn at (a label at user-space y
// 282 on a page scaled by 0.76 came back at 369); the factor is 1 where they agree.
function extentUnit(root) {
  const total = root.getNumberOfChars();
  const box = root.getBBox();
  if (total === 0 || box.height === 0) return 1;
  let top = Infinity, bottom = -Infinity;
  for (let index = 0; index < total; index += 1) {
    let extent;
    try {
      extent = root.getExtentOfChar(index);
    } catch (error) {
      return null;
    }
    top = Math.min(top, extent.y);
    bottom = Math.max(bottom, extent.y + extent.height);
  }
  return bottom > top ? box.height / (bottom - top) : 1;
}

function selectionRects(range) {
  return svgSelectionRects(range)
    ?? Array.from(range.getClientRects()).filter((rect) => rect.width > 0 && rect.height > 0);
}

function ensureHighlightLayer(page) {
  const doc = frameDocument();
  let style = doc.querySelector("#html-mcp-highlight-style");
  if (style === null) {
    style = doc.createElement("style");
    style.id = "html-mcp-highlight-style";
    style.textContent = `
      .html-mcp-highlight-layer { position: absolute; left: 0; top: 0; right: 0; bottom: 0; overflow: hidden; z-index: 2147483646; pointer-events: none; }
      .html-mcp-highlight { position: absolute; border-radius: 2px; background: rgba(246, 216, 74, .42); box-shadow: inset 0 -1px rgba(171, 139, 0, .28); }
      .html-mcp-highlight-badge { position: absolute; min-width: 18px; height: 18px; padding: 0 4px; border: 1px solid #8b7413; border-radius: 9px; color: #302900; background: #ffe77a; font: 11px/16px system-ui, sans-serif; pointer-events: auto; cursor: pointer; }
      .html-mcp-highlight.flash { background: rgba(255, 177, 60, .68); }
    `;
    doc.head.appendChild(style);
  }
  // Keep the layer inside the page. It then inherits the page zoom, so both share one coordinate system.
  let layer = page.querySelector(":scope > .html-mcp-highlight-layer");
  if (layer === null) {
    layer = doc.createElement("div");
    layer.className = "html-mcp-highlight-layer";
    page.appendChild(layer);
  }
  // A scrolling frame (speaker-script block) clips an inset layer to the visible box;
  // size the layer to the full scroll height so marks on scrolled-away lines survive.
  if (page.scrollHeight > page.clientHeight) {
    layer.style.bottom = "auto";
    layer.style.height = `${page.scrollHeight}px`;
  }
  return layer;
}

// Browsers disagree on whether the CSS zoom applied to section.page is reflected in
// getClientRects(), so placing measured coordinates straight onto an unscaled layer
// misaligns them when zoomed (observed in Safari). Measure the page rect through the
// same API to derive the effective scale, then convert to page-relative coordinates.
function pageFrameFor(node) {
  const element = node.nodeType === 1 ? node : node.parentElement;
  // Speaker-script blocks (slides templates) live outside main.pages but take comments
  // through the same anchor path; each block is its own highlight frame. They scroll
  // internally, so content coordinates need the scroll offset added back.
  const page = element?.closest("body > main.pages > section.page, .script-block") ?? null;
  if (page === null) return null;
  const rect = page.getBoundingClientRect();
  const ratio = page.offsetWidth > 0 ? rect.width / page.offsetWidth : 1;
  return {
    page, rect, ratio: ratio > 0 ? ratio : 1,
    scrollTop: page.scrollTop || 0, scrollLeft: page.scrollLeft || 0,
  };
}

function renderHighlights() {
  if (frameDocument() === null || frameDocument().body === null) return;
  const previousUnattached = new Set(state.unattached);
  for (const layer of frameDocument().querySelectorAll(".html-mcp-highlight-layer")) clear(layer);
  state.unattached.clear();
  let number = 0;
  for (const comment of state.comments) {
    if (comment.status !== "open" || comment.anchor.kind !== "text") continue;
    number += 1;
    const range = resolveAnchor(comment.anchor);
    if (range === null) {
      state.unattached.add(comment.id);
      continue;
    }
    const frame = pageFrameFor(range.startContainer);
    if (frame === null) {
      state.unattached.add(comment.id);
      continue;
    }
    // Both rect and page rect are viewport-relative, so scrolling cancels out in the difference.
    const local = (rect) => ({
      left: (rect.left - frame.rect.left) / frame.ratio + frame.scrollLeft,
      top: (rect.top - frame.rect.top) / frame.ratio + frame.scrollTop,
      width: rect.width / frame.ratio,
      height: rect.height / frame.ratio,
    });
    const layer = ensureHighlightLayer(frame.page);
    const rects = selectionRects(range);
    for (const rect of rects) {
      const box = local(rect);
      const mark = frameDocument().createElement("div");
      mark.className = "html-mcp-highlight";
      mark.dataset.commentId = comment.id;
      Object.assign(mark.style, {
        left: `${box.left}px`, top: `${box.top}px`, width: `${box.width}px`, height: `${box.height}px`,
      });
      layer.appendChild(mark);
    }
    const firstRect = rects[0];
    if (firstRect !== undefined) {
      const box = local(firstRect);
      const badge = frameDocument().createElement("button");
      badge.type = "button";
      badge.className = "html-mcp-highlight-badge";
      badge.textContent = String(number);
      badge.title = comment.thread[0].text;
      Object.assign(badge.style, {
        left: `${Math.max(0, box.left - 21)}px`, top: `${Math.max(0, box.top - 1)}px`,
      });
      badge.addEventListener("click", () => focusComment(comment.id));
      layer.appendChild(badge);
    }
  }
  const attachmentChanged = previousUnattached.size !== state.unattached.size
    || Array.from(previousUnattached).some((commentId) => !state.unattached.has(commentId));
  if (attachmentChanged) {
    const ui = captureCommentUi();
    renderComments();
    restoreCommentUi(ui);
  }
}

function scheduleHighlights() {
  if (state.renderFrame !== null) frameWindow().cancelAnimationFrame(state.renderFrame);
  state.renderFrame = frameWindow().requestAnimationFrame(() => {
    state.renderFrame = null;
    renderHighlights();
  });
}

function scriptsHidden() {
  return localStorage.getItem("htmlMcpScriptsHidden") === "1";
}

// Speaker scripts are blocks a slides template emits after each page. The choice to
// hide them is a viewer setting, applied to the artifact document as an attribute the
// viewer stylesheet reads, so it survives artifact reloads and tab switches.
function applyScriptVisibility() {
  const hidden = scriptsHidden();
  const doc = frameDocument();
  if (doc?.documentElement) {
    if (hidden) doc.documentElement.dataset.htmlMcpScriptsHidden = "";
    else delete doc.documentElement.dataset.htmlMcpScriptsHidden;
  }
  const button = $("#scripts-btn");
  button.classList.toggle("active", !hidden);
  button.setAttribute("aria-pressed", hidden ? "false" : "true");
  const hasScripts = doc?.querySelector("main.pages > .script-block") !== null;
  button.disabled = !hasScripts;
}

function attachArtifactEvents() {
  const doc = frameDocument();
  const win = frameWindow();
  // Page geometry exists before anchors are measured.
  installArtifactLayout();
  applyScriptVisibility();
  if (document.fullscreenElement === $("#artifact-pane")) {
    doc.documentElement.dataset.htmlMcpFullscreen = "";
  }
  state.currentPage = visiblePageNumber();
  renderPages();
  doc.addEventListener("mouseup", () => setTimeout(showSelectionButton, 0), true);
  doc.addEventListener("keyup", () => setTimeout(showSelectionButton, 0), true);
  // A phone selects by holding a word and dragging the handles, and sends no mouseup for
  // any of it: the words were highlighted and no button ever came. The selection itself is
  // watched as well, held back while a pointer is down so that a drag on a desktop still
  // settles before the button appears.
  // Holding a word hands that touch to the browser's own selection, and the sequence ends
  // as a cancel rather than a release. A cancel is the end of a touch like any other, so
  // it asks the same question; without that the highlighted words waited for the next pan
  // or pinch to bring the button.
  for (const kind of ["touchend", "touchcancel"]) {
    doc.addEventListener(kind, () => setTimeout(showSelectionButton, 60), true);
  }
  installArtifactZoom();
  doc.addEventListener("selectionchange", () => {
    if (state.selectionPointerDown) return;
    if (state.selectionSettle !== null) clearTimeout(state.selectionSettle);
    state.selectionSettle = setTimeout(() => {
      state.selectionSettle = null;
      showSelectionButton();
    }, 250);
  });
  doc.addEventListener("keydown", handlePresentationKeydown, true);
  doc.addEventListener("click", handlePresentationClick, true);
  doc.addEventListener("pointerdown", handlePresentationPointerDown, true);
  doc.addEventListener("pointerup", handlePresentationPointerUp, true);
  doc.addEventListener("wheel", handlePresentationWheel, { passive: false });
  doc.addEventListener("pointerdown", (event) => {
    state.selectionPointerDown = true;
    if (!event.target.closest(".html-mcp-highlight-layer")) hideSelectionButton();
  }, true);
  for (const kind of ["pointerup", "pointercancel"]) {
    doc.addEventListener(kind, () => {
      state.selectionPointerDown = false;
      setTimeout(showSelectionButton, 60);
    }, true);
  }
  win.addEventListener("scroll", () => {
    const settled = state.settledScroll;
    if (settled !== null) {
      state.settledScroll = null;
      if (performance.now() < settled.until
          && (Math.abs(win.scrollX - settled.x) > 1 || Math.abs(win.scrollY - settled.y) > 1)) {
        win.scrollTo(settled.x, settled.y);
      }
    }
    hideSelectionButton();
    scheduleCurrentPage();
  }, { passive: true });
  win.addEventListener("resize", () => {
    updatePageScale();
    // Dragging the split resizes the artifact on every frame. Measuring the fit of all pages
    // and redrawing the highlight boxes that often is the work that made the bar lag behind
    // the finger; the drag ends with one of each.
    if (state.draggingPanel) return;
    scheduleHighlights();
    scheduleLayoutCheck();
    scheduleCurrentPage();
  });
  if (state.pendingView !== null) {
    const view = state.pendingView;
    state.pendingView = null;
    win.requestAnimationFrame(() => win.scrollTo(view.x, view.y));
  }
  renderHighlights();
  updateLayoutUi();
  if (document.fullscreenElement === $("#artifact-pane") && state.artifact.layout === "slides") activateSlideShow();
  scheduleLayoutCheck();
  doc.fonts.ready.then(scheduleLayoutCheck);
  // An image that finishes loading after the check changes the layout the
  // check measured, so each pending image re-triggers it.
  for (const img of doc.images) {
    if (!img.complete) {
      img.addEventListener("load", scheduleLayoutCheck, { once: true });
      img.addEventListener("error", scheduleLayoutCheck, { once: true });
    }
  }
}

function loadArtifact(preserveView) {
  if (state.loadedRevision === state.revision) return;
  const iframe = $("#artifact-frame");
  if (preserveView && iframe.contentWindow !== null) {
    state.pendingView = { x: iframe.contentWindow.scrollX, y: iframe.contentWindow.scrollY };
  }
  hideSelectionButton();
  state.loadedRevision = state.revision;
  iframe.src = `${artifactBase()}/artifact?v=${encodeURIComponent(state.revision)}`;
}

async function refreshState() {
  state.project = await fetchJson("/state");
  const ids = Object.keys(state.project.artifacts);
  // ?artifact= names the artifact to open: a shareable link, and how the server's own
  // headless browser is pointed at the artifact whose layout it has to check.
  const asked = new URLSearchParams(location.search).get("artifact");
  const remembered = asked !== null ? asked : localStorage.getItem("htmlMcpArtifact");
  state.artifactId = remembered !== null && ids.includes(remembered) ? remembered : ids[0];
  state.artifact = state.project.artifacts[state.artifactId];
  state.revision = state.artifact.revision;
  renderArtifactTabs();
  updateArtifactLinks();
  updateLayoutUi();
}

const comments = createComments({
  $,
  artifactBase,
  clear,
  fetchJson,
  frameDocument,
  frameWindow,
  h,
  hideSelectionButton,
  renderHighlights,
  resolveAnchor,
  state,
});
const actionButton = comments.actionButton;
const captureCommentUi = comments.captureCommentUi;
const focusComment = comments.focusComment;
const installComposeKeys = comments.installComposeKeys;
const openCompose = comments.openCompose;
const foldAll = comments.foldAll;
const pickAll = comments.pickAll;
const renderPickedActions = comments.renderPickedActions;
const setPickedStatus = comments.setPickedStatus;
const refreshComments = comments.refreshComments;
const renderComments = comments.renderComments;
const restoreCommentUi = comments.restoreCommentUi;
const submitCompose = comments.submitCompose;
const switchSidebarTab = comments.switchSidebarTab;

function printArtifact() {
  frameWindow().focus();
  frameWindow().print();
}

// The green dot beside Call agent: an agent is parked on wait_review right now, so a
// press reaches it at once rather than waiting to be picked up.
function showAgentWaiting(waiters) {
  $("#agent-waiting-dot").classList.toggle("hidden", !(waiters > 0));
}

async function handleSocketMessage(message) {
  if (message.type === "config_error") {
    $("#artifact-status").textContent = `config error: ${message.error}`;
    return;
  }
  if (message.type === "state") {
    state.project = message;
    if (message.review !== undefined) showAgentWaiting(message.review.waiters);
    const artifact = message.artifacts[state.artifactId];
    if (artifact !== undefined && state.revision !== artifact.revision) {
      state.artifact = artifact;
      state.revision = artifact.revision;
      updateLayoutUi();
      loadArtifact(true);
    }
    return;
  }
  if (message.type === "review_waiters") {
    showAgentWaiting(message.waiters);
    return;
  }
  if (["artifacts_changed", "config_reloaded"].includes(message.type)) {
    state.project = message;
    if (state.project.artifacts[state.artifactId] === undefined) {
      state.artifactId = Object.keys(state.project.artifacts)[0];
      state.loadedRevision = null;
    }
    const artifact = state.project.artifacts[state.artifactId];
    const changed = state.loadedRevision !== artifact.revision || state.revision !== artifact.revision;
    state.artifact = artifact;
    state.revision = artifact.revision;
    renderArtifactTabs();
    updateArtifactLinks();
    updateLayoutUi();
    if (changed) loadArtifact(true);
    return;
  }
  if (["comment_added", "comment_updated", "comments_updated", "comment_deleted"].includes(message.type)
      && message.artifact === state.artifactId) {
    await refreshComments();
  }
}

function connectWebSocket() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${location.host}/ws`);
  state.ws = socket;
  socket.onopen = updateLayoutUi;
  socket.onmessage = (event) => {
    handleSocketMessage(JSON.parse(event.data)).catch((error) => console.error(error));
  };
  socket.onclose = () => {
    $("#artifact-status").textContent = "reconnecting";
    setTimeout(connectWebSocket, 1500);
  };
}

function attachControls() {
  $("#artifact-frame").addEventListener("load", attachArtifactEvents);
  $("#selection-comment-btn").addEventListener("click", () => {
    if (state.selectionAnchor !== null) openCompose(state.selectionAnchor);
  });
  $("#artifact-comment-btn").addEventListener("click", () => openCompose({ kind: "artifact" }));
  $("#print-btn").addEventListener("click", printArtifact);
  $("#download-pptx-btn").addEventListener("click", downloadPptx);
  $("#fullscreen-btn").addEventListener("click", () => {
    // The slide show sizes the current page itself; a reader's zoom held from browsing
    // would put the show off screen.
    resetArtifactZoom();
    toggleFullscreen().catch((error) => alert(`Could not enter full screen: ${error.message}`));
  });
  $("#presentation-prev-btn").addEventListener("click", () => movePresentationPage(-1));
  $("#presentation-next-btn").addEventListener("click", () => movePresentationPage(1));
  $("#presentation-exit-btn").addEventListener("click", () => {
    document.exitFullscreen().catch((error) => alert(`Could not exit full screen: ${error.message}`));
  });
  document.addEventListener("wheel", handlePresentationWheel, { passive: false });
  document.addEventListener("wheel", handleViewerWheel, { passive: false });
  for (const kind of ["gesturestart", "gesturechange", "gestureend"]) {
    document.addEventListener(kind, handleViewerGesture, { passive: false });
  }
  document.addEventListener("fullscreenchange", syncFullscreenMode);
  // A device that cannot be watched from where the code is written draws its own touch
  // record over the page when the address carries ?trace.
  if (new URLSearchParams(window.location.search).has("trace")) import("/static/trace.js");
  $("#compose-form").addEventListener("submit", submitCompose);
  installComposeKeys();
  $("#compose-cancel").addEventListener("click", () => {
    $("#compose-dialog").close();
    state.pendingAnchor = null;
  });
  $("#comment-filter").addEventListener("change", () => refreshComments().catch((error) => alert(error.message)));
  $("#fold-all-btn").addEventListener("click", foldAll);
  $("#pick-all-btn").addEventListener("click", pickAll);
  // Picking is the reviewer's own act, and closing what was picked is the sign-off on a
  // batch the agent answered and deliberately left open. The buttons carry the ids they
  // were drawn with, so a press acts on what its label counted.
  for (const [id, status] of [["#resolve-picked-btn", "resolved"], ["#reopen-picked-btn", "open"]]) {
    $(id).addEventListener("click", async () => {
      const button = $(id);
      const ids = button.dataset.ids === "" ? [] : button.dataset.ids.split(" ");
      if (ids.length === 0) return;
      button.disabled = true;
      try {
        await setPickedStatus(ids, status);
      } catch (error) {
        alert(`Could not save: ${error.message}`);
      } finally {
        button.disabled = false;
      }
    });
  }
  $("#call-agent-btn").addEventListener("click", async () => {
    const button = $("#call-agent-btn");
    const word = $("#call-agent-word");
    button.disabled = true;
    try {
      const reply = await fetchJson("/review-request", { method: "POST" });
      // Delivered went straight to a parked agent; queued is kept by the server and
      // answers the agent's next wait at once. The word shows beside the bell for a
      // moment, which is the only time the button carries one.
      word.textContent = reply.delivered ? "Called" : "Queued";
    } catch (error) {
      word.textContent = "Failed";
      console.error(error);
    } finally {
      setTimeout(() => { word.textContent = ""; button.disabled = false; }, 2000);
    }
  });
  for (const button of document.querySelectorAll(".tab-btn")) {
    button.addEventListener("click", () => switchSidebarTab(button.dataset.tab));
  }
  $("#sidebar-toggle-btn").addEventListener("click", () => {
    const collapsed = $(".layout").classList.toggle("sidebar-collapsed");
    localStorage.setItem("htmlMcpSidebarCollapsed", collapsed ? "1" : "0");
  });
  $("#scripts-btn").addEventListener("click", () => {
    localStorage.setItem("htmlMcpScriptsHidden", scriptsHidden() ? "0" : "1");
    applyScriptVisibility();
  });
  document.addEventListener("keydown", (event) => {
    handlePresentationKeydown(event);
    if (event.defaultPrevented) return;
    if (event.key !== "\\" || event.metaKey || event.ctrlKey || event.altKey) return;
    if (["TEXTAREA", "INPUT", "SELECT"].includes(event.target.tagName)) return;
    event.preventDefault();
    $("#sidebar-toggle-btn").click();
  });
  // On a phone the comments sit under the artifact, and the bar along their top drags the
  // split so either can be given the screen without the other going away.
  const grip = $("#sidebar-grip");
  const layout = $(".layout");
  const setPanelHeight = (pixels) => {
    const limited = Math.round(Math.max(90, Math.min(pixels, window.innerHeight - 140)));
    layout.style.setProperty("--html-mcp-panel-height", `${limited}px`);
    return limited;
  };
  const savedHeight = Number(localStorage.getItem("htmlMcpPanelHeight"));
  if (savedHeight > 0) layout.style.setProperty("--html-mcp-panel-height", `${savedHeight}px`);
  // The tab row sits directly under the bar, and dragging moves the panel's edge out from
  // under the finger: on release the tabs were where the finger now was, and the tap that
  // ends a drag landed on one of them. A drag is not a tap, so clicks in the comments are
  // ignored for a moment after one, at the capture phase, before any tab sees them. A
  // window rather than a one-shot: the drag itself leaves a click behind, and a one-shot
  // was spent on that one and let the offender through.
  const dragQuietFor = 400;
  $("#sidebar").addEventListener("click", (event) => {
    if (performance.now() - state.panelDraggedAt >= dragQuietFor) return;
    event.preventDefault();
    event.stopPropagation();
  }, true);
  grip.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    grip.setPointerCapture(event.pointerId);
    // A finger sends more moves than the screen draws, and each one resized the artifact and
    // wrote the new height to storage, so the bar answered late and the drag read as stuck.
    // One height per frame is all a drag can show, and the height is kept once, on release.
    // The edge the height is measured from cannot move during the drag, so it is read once.
    const bottom = layout.getBoundingClientRect().bottom;
    let pointerY = null;
    let frame = null;
    let height = null;
    const apply = () => {
      frame = null;
      height = setPanelHeight(bottom - pointerY);
    };
    const move = (moved) => {
      pointerY = moved.clientY;
      if (frame === null) frame = requestAnimationFrame(apply);
    };
    const done = (ended) => {
      if (frame !== null) cancelAnimationFrame(frame);
      if (pointerY !== null) height = setPanelHeight(bottom - pointerY);
      if (ended?.cancelable) ended.preventDefault();
      if (pointerY !== null) state.panelDraggedAt = performance.now();
      state.draggingPanel = false;
      grip.removeEventListener("pointermove", move);
      grip.removeEventListener("pointerup", done);
      grip.removeEventListener("pointercancel", done);
      if (height !== null) localStorage.setItem("htmlMcpPanelHeight", String(height));
      updatePageScale();
      scheduleHighlights();
      scheduleLayoutCheck();
    };
    state.draggingPanel = true;
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", done);
    grip.addEventListener("pointercancel", done);
  });
  $("#zoom-reset-btn").addEventListener("click", () => {
    resetArtifactZoom();
  });
  $("#fullscreen-btn").disabled = !document.fullscreenEnabled;
  // On a phone the comments cover the artifact, so they start out of the way until asked
  // for; a wide screen shows both and keeps whatever was chosen last.
  const stored = localStorage.getItem("htmlMcpSidebarCollapsed");
  const collapsed = stored === null ? window.innerWidth <= 560 : stored === "1";
  if (collapsed) $(".layout").classList.add("sidebar-collapsed");
}

async function init() {
  attachControls();
  await refreshState();
  await refreshComments();
  loadArtifact(false);
  connectWebSocket();
}

document.addEventListener("DOMContentLoaded", () => {
  init().catch((error) => {
    console.error(error);
    alert(`html-web failed to start: ${error.message}`);
  });
});
