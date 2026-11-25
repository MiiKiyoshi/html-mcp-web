// The review page of an HTML artifact. Its own parts are modules in page/, each of which says at
// its head what it does and what it takes and gives; the parts the review pages share are in
// shared/. This file wires them: it creates the page's parts and then the shared ones, each given
// the hooks it takes, connects the parts that follow each other once all of them exist, and
// starts them in order once the page has loaded.

import { createSettings } from "./shared/settings.js";
import { $, showMacKeyNames } from "./shared/dom.js";
import { createCommentPanel } from "./shared/comment-panel.js";
import { createTabStrip } from "./shared/tab-strip.js";
import { createHelp } from "./shared/help.js";
import { createUpdate } from "./shared/update.js";
import { holdZoomOnFields, holdPinchOutside } from "./shared/page-zoom.js";
import { attachPanelGrips } from "./shared/panel-grips.js";
import { attachEscapeKey } from "./shared/page-keys.js";
import { attachSidebarToggle } from "./shared/sidebar.js";
import { createSocket } from "./shared/socket.js";
import { fetchJson } from "./page/fetch-json.js";
import { createProject } from "./page/project.js";
import { createReloadPlace } from "./page/reload-place.js";
import { createPages } from "./page/pages.js";
import { createPresentation } from "./page/presentation.js";
import { createZoom } from "./page/zoom.js";
import { createAnchors } from "./page/anchors.js";
import { createPageMarks } from "./page/page-marks.js";
import { createSelection } from "./page/selection.js";
import { createArea } from "./page/area.js";
import { createSearch } from "./page/search.js";
import { createThumbs } from "./page/thumbs.js";
import { createLayoutResults } from "./page/layout-results.js";
import { createScripts } from "./page/scripts.js";
import { createSourceEditor } from "./page/source-editor.js";
import { createWorkspace } from "./page/workspace.js";
import { createPlaces } from "./page/places.js";
import { createDeckSetup } from "./page/deck-setup.js";
import { createDeck } from "./page/deck.js";
import { createArtifactTabs } from "./page/artifact-tabs.js";
import { createPanelRoom } from "./page/panel-room.js";
import { anchorLabel, commentQuote, composeAnchorText } from "./page/comment-places.js";
import { attachExport } from "./page/export.js";
import { attachMenu } from "./page/menu.js";
import { attachFrameTheme, markFrameThemes } from "./page/frame-theme.js";

// What the browser keeps this page's shared choices under, named once, in index.html.
const PREFIX = document.querySelector("script[data-prefix]").dataset.prefix;

// The open comments of the artifact shown, as the panel last read them, which the pages and the
// editor mark.
let markedComments = [];

// ----- The page's own parts -----

const project = createProject();

const pages = createPages({ showing: () => presentation.showing(), commentOn });

const presentation = createPresentation({ pages, layout: () => project.artifact().layout });

const zoom = createZoom({ showing: presentation.showing });

const anchors = createAnchors({ digest: () => project.artifact().artifact_digest });

const marks = createPageMarks({ marked: () => markedComments, anchors });

const area = createArea({ layer: marks.layer, commentOn });

const search = createSearch({
  showing: presentation.showing,
  current: pages.current,
  movePage: presentation.movePage,
  frameOf: marks.frameOf,
});

const thumbs = createThumbs({ project, pages, searchKey: search.handleKeydown });

const layout = createLayoutResults({ project, showing: presentation.showing });

const scripts = createScripts();

const source = createSourceEditor({
  base: project.base,
  cursorAt: () => settings.cursorAt(),
  marked: () => markedComments,
  commentOn,
  refreshComments: () => panel.refreshComments(),
  showComment: (id) => places.takeComment(id),
  focusComment: (id) => places.openComment(id),
  showWherePrinted: (shown) => places.showWherePrinted(shown),
});

const workspace = createWorkspace({ source });

const places = createPlaces({
  workspace,
  source,
  marks,
  anchors,
  showComment: (id) => panel.showComment(id),
  ringed: () => panel.ringed(),
  showTab: (name) => strip.show(name),
});

const selection = createSelection({
  base: project.base,
  captureTextAnchor: anchors.captureTextAnchor,
  pinching: zoom.pinching,
  inFullscreen: presentation.inFullscreen,
  commentOn,
  showInSource: places.showInSource,
});

const deckSetup = createDeckSetup({
  project, zoom, scripts, presentation, pages, area, selection, search, marks, layout, dragging: workspace.dragging,
});

const deck = createDeck({ project, showing: presentation.showing, pagesChanged: presentation.pagesChanged });

const reloadPlace = createReloadPlace({
  alias: project.alias,
  heldPage: presentation.heldPage,
  pendingView: deck.pendingView,
});

const tabs = createArtifactTabs({ project, select: selectArtifact });

// ----- The parts shared with the other review pages -----

// The theme, the text size, the key that sends a comment, the key letters and the editor's cursor,
// as Settings keeps them. The review page's own parts follow the theme; the artifact is drawn as
// written, on a ground that follows it.
const settings = createSettings({
  prefix: PREFIX,
  onTheme: () => {
    source.setTheme();
    markFrameThemes();
  },
  onLetters: (shown) => shown || panel.keys.showLetters(false),
  onCursor: () => source.holdCursorLine(),
});

// The comments' width beside the artifact and their height under it. A drag resizes the artifact
// on every frame; measuring the fit of all pages and redrawing the highlight boxes that often is
// the work that made the bar lag behind the finger, so the workspace is told of the drag, and the
// drag ends with one of each, as the split's does.
const grips = attachPanelGrips({
  prefix: PREFIX,
  width: "--html-mcp-sidebar-width",
  height: "--html-mcp-panel-height",
  split: () => workspace.split,
  resizing: () => workspace.drag(true),
  resized: () => workspace.drag(false),
});

const room = createPanelRoom({ isOpen: (id) => panel.isOpen(id), setHeight: (pixels) => grips.setHeight(pixels) });

// The list of comments, the row above it, its search, its cards and its keys are shared with the
// other review pages, in shared/comment-panel.js. What is this page's own goes in by the hooks
// below: the artifact shown, its pages and frames, and the editor.
const panel = createCommentPanel({
  settings,
  // The comments of the artifact shown.
  base: () => project.base(),
  label: anchorLabel,
  quote: commentQuote,
  // Words the page no longer finds, as the marks last found them, or a selection in the source
  // the server no longer finds.
  stale: (comment) => marks.lost(comment.id) || Boolean(comment.stale),
  // An opened card shows whole, and the page or the source shows where the comment is.
  showPlace: (comment) => {
    if (panel.isOpen(comment.id)) room.reveal(comment.id);
    places.showComment(comment).catch((error) => console.error(error));
  },
  // K takes the keys to a comment's words in the source.
  enterPlace: (comment) => places.enterComment(comment),
  marked: (comments) => {
    markedComments = comments;
    marks.render();
    source.markComments();
  },
  whole: () => $("#artifact-comment-btn").click(),
  help: (page) => help.show(page),
  // The bell (shared/agent-bell.js). A press goes to the session listening, or to the agent picked
  // beside the bell with its model and effort.
  bell: {
    call: (lane) => fetchJson("/review-request", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(lane ?? {}),
    }),
  },
  bringIntoView: (id) => room.reveal(id),
  labels: { document: "artifact" },
  tabs: {
    comments: {
      count: "#comments-tab-count",
      hint: "To comment, select words on a page or in the Source, press + comment beside a page in Pages, or draw a box "
        + "with the box tool. Add a note on the whole artifact… in the ⋯ menu comments on the artifact as a whole.",
    },
  },
  compose: {
    // The selection the comment was written on goes.
    posted: (comment, body) => {
      selection.forget();
      if (body.anchor.kind === "source") source.clearSelection();
      else selection.clear();
    },
  },
  // Space shows where a comment is on the page or in the source, and K takes the keys to its words
  // in the source. They rest while the artifact fills the screen, where the slide show has keys of
  // its own.
  keys: {
    rows: () => [
      { keys: ["K", "Ctrl+Alt+K"], does: "Jump to its text in the source and move keyboard focus there; press K (Ctrl+Alt+K without "
        + "Vim keys) to come back. A comment on the page shows its place there instead, and the keys stay here" },
    ],
    rests: () => presentation.inFullscreen(),
  },
});

// The sidebar's tabs: Pages, Comments, which the panel fills, and Problems.
const strip = createTabStrip({ shown: (name, clicked) => panel.showTab(name, clicked) });

// Help, with the artifact's own Start here, search story and keys. The Search page's terms in a
// deck's words, as its example about a chart's legend is.
const help = createHelp({ prefix: PREFIX, pages: [], keys: panel.keys, words: {
  both: ["legend", "color"], either: ["chart", "table"], phrase: "title slide", without: "backup" } });

// The ⋯ menu's Update and the version line at its end, and the band under the top bar that says
// what is left once an update is installed.
const update = createUpdate({
  name: "html-mcp-web", server: "html-mcp", menu: $("#more-menu"), before: $("main.layout"),
  how: "https://github.com/MiiKiyoshi/html-mcp-web/blob/main/INSTALL.md",
});

// The server runs inside the agent's process. While it cannot be reached the bell says no agent
// listens and the bar says the page is reconnecting.
const socket = createSocket({
  reconnect: 1500,
  opened: () => {
    announceArtifact();
    layout.show();
    // A server that comes back may be a new version's: the page asks which runs now.
    update.read().catch((error) => console.error(error));
    // The comments may have changed while the page could not hear the server, or before it first
    // could: the socket opens after the first reading and the artifact's load, and an agent's
    // reply written in between was never shown.
    panel.refreshComments().catch((error) => console.error(error));
  },
  heard: handleSocketMessage,
  closed: () => {
    panel.bell.show({ waiters: 0 });
    $("#artifact-status").textContent = "reconnecting";
  },
});

// ----- What the parts follow of each other, once they all exist -----

// The reader's place is kept as the page reloads for newer code.
project.leaving(() => reloadPlace.remember());
// The page read from the window is the one the slide show marks while it is on, and the one the
// previews mark and keep in view.
pages.changed(() => {
  presentation.markCurrent();
  thumbs.mark();
});
// The zoom goes back to the page's own as the reader asks for full screen, and the pages are
// fitted again as full screen, the show or the page it shows changes. The selection's menu goes
// as full screen comes on, and the layout check, which waits out the show, runs once it ends.
presentation.entering(() => zoom.reset());
presentation.changed(() => zoom.fit());
presentation.entered(() => selection.hide());
presentation.ended(() => layout.schedule());
// The selection's menu goes while a gesture carries the deck and comes back once it has settled,
// and the comments' marks are drawn again at each zoom.
zoom.carrying(() => selection.hide());
zoom.settled(() => selection.show());
zoom.applied(() => marks.schedule());
// A press on a comment's number on a page opens its card, and the cards say which comments' words
// the pages no longer find.
marks.pressed((id) => places.markPressed(id));
marks.lostChanged(() => panel.renderComments());
// The search looks in the speaker scripts while they are shown.
scripts.changed(() => search.refresh());
// The pages are fitted again, with what is drawn over them, to the room the Preview is given.
workspace.resized(() => deckSetup.refit());
// The slide previews follow the artifact the frame on screen is brought to, and the selection's
// menu goes as the frame goes to another revision.
deck.following(() => thumbs.follow());
deck.revising(() => selection.hide());
// A document loaded in the frame on screen is set up and put at the place a reload kept; for a
// frame set up before and shown again, the page alone is set up.
deck.loaded((doc, win) => {
  deckSetup.loaded(doc, win);
  reloadPlace.putBack(win);
});
deck.shown(() => deckSetup.shown());
// Pages an edit changes in place are fitted, and checked again as their fonts and images arrive.
deck.changed((doc, images) => {
  zoom.fit();
  layout.watch(doc, images);
});

// The new comment dialog on *anchor*. A comment on the source goes with the revision its words
// were selected in, which the server checks against the file.
function commentOn(anchor) {
  panel.openCompose(anchor, composeAnchorText(anchor),
    anchor.kind === "source" ? { source_revision: source.revision() } : {});
}

// The server is told which artifact the page shows.
function announceArtifact() {
  if (socket.open() && project.alias() !== null) socket.send({ type: "active_artifact", artifact: project.alias() });
}

// Another artifact shown, from its tab: its comments, its frame and its zoom, and its file in the
// editor when the Source shows.
async function selectArtifact(alias) {
  if (alias === project.alias()) return;
  if (!source.mayLeave()) return;
  zoom.keep(project.alias());
  project.choose(alias);
  announceArtifact();
  panel.reset();
  marks.forget();
  pages.setCurrent(null);
  source.forget();
  deck.open(alias);
  zoom.restore(alias);
  tabs.render();
  layout.show();
  await panel.refreshComments();
  if (workspace.view() !== "preview") await source.load(true);
  deck.showOrLoad();
}

async function handleSocketMessage(message) {
  if (message.type === "config_error") {
    $("#artifact-status").textContent = `config error: ${message.error}`;
    return;
  }
  if (message.type === "state") {
    if (!project.adopt(message)) return;
    if (message.review !== undefined) panel.bell.show({ waiters: message.review.waiters, lanes: message.review.lanes });
    const artifact = message.artifacts[project.alias()];
    if (artifact !== undefined && project.revision() !== artifact.revision) {
      project.take(artifact);
      layout.show();
      deck.load(true);
    }
    return;
  }
  if (message.type === "review_waiters") {
    panel.bell.show({ waiters: message.waiters });
    return;
  }
  if (message.type === "lanes") {
    panel.bell.show({ lanes: message.lanes });
    return;
  }
  // The server finished its check of a revision: the review page shows that result.
  if (message.type === "layout_checked") {
    if (!project.adopt(message)) return;
    const artifact = project.project().artifacts[project.alias()];
    if (artifact !== undefined && artifact.revision === project.revision()) {
      project.take(artifact);
      layout.show();
    }
    return;
  }
  if (["artifacts_changed", "config_reloaded"].includes(message.type)) {
    if (!project.adopt(message)) return;
    // An edited configuration can name other agents beside the session listening.
    panel.bell.show({ lanes: message.review.lanes });
    // An artifact shown that the configuration no longer names gives way to the first, with its
    // comments.
    const gone = project.project().artifacts[project.alias()] === undefined;
    if (gone) {
      project.show(Object.keys(project.project().artifacts)[0]);
      deck.forget();
      panel.reset();
      marks.forget();
    }
    const artifact = project.project().artifacts[project.alias()];
    const changed = !deck.shows(artifact.revision) || project.revision() !== artifact.revision;
    project.take(artifact);
    tabs.render();
    layout.show();
    if (gone) await panel.refreshComments();
    if (changed) deck.load(true);
    if (message.type === "artifacts_changed") await source.changedOnDisk(message.path, workspace.view() !== "preview");
    return;
  }
  if (["comment_added", "comment_updated", "comments_updated", "comment_deleted"].includes(message.type)
      && message.artifact === project.alias()) {
    await panel.refreshComments();
  }
}

function attachControls() {
  workspace.attach();
  reloadPlace.attach();
  source.attach();
  selection.attach();
  area.attach();
  attachEscapeKey({ own: "#source-editor" });
  attachMenu({ openSettings: () => settings.open() });
  attachFrameTheme();
  $("#artifact-comment-btn").addEventListener("click", () => commentOn({ kind: "artifact" }));
  attachExport({ base: project.base });
  presentation.attach();
  zoom.attach();
  // A device that cannot be watched from where the code is written draws its own touch record
  // over the page when the address carries ?trace.
  if (new URLSearchParams(window.location.search).has("trace")) import("./page/trace.js");
  panel.attach();
  thumbs.attach();
  search.attachControls();
  scripts.attach();
  // On a phone the comments cover the artifact, so they start out of the way until asked for; a
  // wide screen shows both and keeps whatever was chosen last.
  attachSidebarToggle({ key: "htmlMcpSidebarCollapsed", closedUnder: 561 });
}

async function init() {
  holdZoomOnFields();
  // The artifact zooms with a pinch: in its frame about the fingers, and anywhere else on the page
  // about its middle (zoom.js).
  holdPinchOutside("#artifact-frame");
  attachControls();
  if (await project.read()) {
    tabs.render();
    layout.show();
  }
  await panel.refreshComments();
  deck.load(false);
  thumbs.restore();
  await workspace.restore();
  socket.connect();
}

document.addEventListener("DOMContentLoaded", () => {
  // On a Mac the keys go by the Mac's names, in Help too.
  showMacKeyNames("#help-dialog");
  init().catch((error) => {
    console.error(error);
    alert(`html-web failed to start: ${error.message}`);
  });
});
