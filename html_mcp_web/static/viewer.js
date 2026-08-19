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
  focusedCommentId: null,
  activeForm: null,
  editingEntry: null,
  unattached: new Set(),
  pendingView: null,
  ws: null,
  renderFrame: null,
  layoutFrame: null,
  pageFrame: null,
  currentPage: null,
  slideShow: false,
  presentationPointer: null,
  presentationWheelEvents: [],
  presentationLastWheelStep: 0,
  suppressPresentationClick: false,
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
  $("#download-html-btn").href = `${artifactBase()}/download/html`;
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
  const availableWidth = frameWindow().innerWidth - (state.slideShow ? 0 : 48);
  const widthScale = availableWidth / page.offsetWidth;
  const scale = state.slideShow
    ? Math.min(widthScale, frameWindow().innerHeight / page.offsetHeight)
    : Math.min(1, widthScale);
  frameDocument().documentElement.style.setProperty("--html-mcp-page-scale", String(scale));
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

function showSelectionButton() {
  const selection = frameWindow().getSelection();
  const button = $("#selection-comment-btn");
  if (document.fullscreenElement === $("#artifact-pane")) {
    state.selectionAnchor = null;
    button.classList.add("hidden");
    return;
  }
  if (selection === null || selection.rangeCount !== 1 || selection.isCollapsed) {
    state.selectionAnchor = null;
    button.classList.add("hidden");
    return;
  }
  const range = selection.getRangeAt(0);
  try {
    state.selectionAnchor = captureTextAnchor(range);
  } catch (error) {
    state.selectionAnchor = null;
    button.classList.add("hidden");
    return;
  }
  const rect = range.getBoundingClientRect();
  const iframe = $("#artifact-frame");
  const pane = $("#artifact-pane");
  const left = Math.min(pane.clientWidth - 92, Math.max(8, iframe.offsetLeft + rect.right + 8));
  const top = Math.min(pane.clientHeight - 38, Math.max(8, iframe.offsetTop + rect.top - 36));
  button.style.left = `${left}px`;
  button.style.top = `${top}px`;
  button.classList.remove("hidden");
}

function hideSelectionButton() {
  $("#selection-comment-btn").classList.add("hidden");
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
    const rects = Array.from(range.getClientRects()).filter((rect) => rect.width > 0 && rect.height > 0);
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
  doc.addEventListener("keydown", handlePresentationKeydown, true);
  doc.addEventListener("click", handlePresentationClick, true);
  doc.addEventListener("pointerdown", handlePresentationPointerDown, true);
  doc.addEventListener("pointerup", handlePresentationPointerUp, true);
  doc.addEventListener("wheel", handlePresentationWheel, { passive: false });
  doc.addEventListener("pointerdown", (event) => {
    if (!event.target.closest(".html-mcp-highlight-layer")) hideSelectionButton();
  }, true);
  win.addEventListener("scroll", () => {
    hideSelectionButton();
    scheduleCurrentPage();
  }, { passive: true });
  win.addEventListener("resize", () => {
    updatePageScale();
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
  const remembered = localStorage.getItem("htmlMcpArtifact");
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
const openCompose = comments.openCompose;
const refreshComments = comments.refreshComments;
const renderComments = comments.renderComments;
const restoreCommentUi = comments.restoreCommentUi;
const submitCompose = comments.submitCompose;
const switchSidebarTab = comments.switchSidebarTab;

function printArtifact() {
  frameWindow().focus();
  frameWindow().print();
}

async function handleSocketMessage(message) {
  if (message.type === "config_error") {
    $("#artifact-status").textContent = `config error: ${message.error}`;
    return;
  }
  if (message.type === "state") {
    state.project = message;
    const artifact = message.artifacts[state.artifactId];
    if (artifact !== undefined && state.revision !== artifact.revision) {
      state.artifact = artifact;
      state.revision = artifact.revision;
      updateLayoutUi();
      loadArtifact(true);
    }
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
  if (message.type === "artifact_changed" && message.artifact === state.artifactId) {
    if (state.revision === message.revision) return;
    state.artifact = message;
    state.revision = message.revision;
    updateLayoutUi();
    loadArtifact(true);
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
    toggleFullscreen().catch((error) => alert(`Could not enter full screen: ${error.message}`));
  });
  $("#presentation-prev-btn").addEventListener("click", () => movePresentationPage(-1));
  $("#presentation-next-btn").addEventListener("click", () => movePresentationPage(1));
  $("#presentation-exit-btn").addEventListener("click", () => {
    document.exitFullscreen().catch((error) => alert(`Could not exit full screen: ${error.message}`));
  });
  document.addEventListener("wheel", handlePresentationWheel, { passive: false });
  document.addEventListener("fullscreenchange", syncFullscreenMode);
  $("#compose-form").addEventListener("submit", submitCompose);
  $("#compose-cancel").addEventListener("click", () => {
    $("#compose-dialog").close();
    state.pendingAnchor = null;
  });
  $("#comment-filter").addEventListener("change", () => refreshComments().catch((error) => alert(error.message)));
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
  $("#fullscreen-btn").disabled = !document.fullscreenEnabled;
  if (localStorage.getItem("htmlMcpSidebarCollapsed") === "1") $(".layout").classList.add("sidebar-collapsed");
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
