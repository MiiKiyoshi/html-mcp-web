// The Source pane: the artifact's edit file in an editor (Ace), saved with Ctrl+S (Cmd+S) and
// read again when it changes on disk, with the comments on it marked (source-marks.js) and Vim
// keys when the reader turns them on (vim-keys.js). Words selected there take a comment, show
// where the Preview prints them (→ Preview), and open the comment the cursor is on (K, or
// Ctrl+Alt+K). The bar sets the type size, the wrapping of long lines and Vim keys, each kept for
// next time. The editor is made the first time the Source is shown. This module keeps the editor,
// the file it holds with its revision, and whether it holds changes not yet saved.
//
// createSourceEditor takes base(), the route of the artifact's calls; cursorAt(), where Settings
// holds the cursor's line, or undefined; marked(), the open comments to mark; commentOn(anchor),
// which opens a new comment; refreshComments(); showComment(id), which opens a comment in the
// panel with the keys taken there; focusComment(id), which opens it and leaves the keys; and
// showWherePrinted(shown), which shows on the pages the words the server says a stretch of the
// file shows. It gives load(force), the file read into the editor, answering whether it holds it;
// path(); revision(); mayLeave(), whether changes not yet saved may go, as the reader answers;
// forget(), the file let go for another artifact's; changedOnDisk(path, reload), told of a file
// the watcher saw change; showAnchor(anchor, focus) and showPlace(place), a comment's words or a
// place of the file selected; markComments(); clearSelection(); resize(); setTheme();
// holdCursorLine(); and attach(), the bar.

import { $ } from "../shared/dom.js";
import { fetchJson, refusalText } from "./fetch-json.js";
import { displayPath, fileName } from "./path-display.mjs";
import { servedStatic } from "./project.js";
import { createSourceMarks } from "./source-marks.js";
import { createVimKeys } from "./vim-keys.js";

const homePath = document.querySelector('meta[name="html-mcp-home"]')?.content ?? "";

export function createSourceEditor({
  base, cursorAt, marked, commentOn, refreshComments, showComment, focusComment, showWherePrinted,
}) {
  let editor = null;
  // Whether a press in the editor is held down, which moves the cursor with the text in place.
  let editorPointing = false;
  let sourcePath = null;
  let sourceRevision = null;
  let sourceDirty = false;
  let sourceLoading = false;
  const marks = createSourceMarks();
  const vim = createVimKeys({
    save: () => saveSource().catch((error) => alert(`Could not save: ${error.message}`)),
    comment: () => commentSourceSelection(),
    showComment: () => showCommentAtCursor(),
    showInPreview: () => showSelectionOnPage().catch((error) => alert(`Could not show it in the Preview: ${error.message}`)),
  });

  function setStatus(text, kind = "") {
    const status = $("#source-status");
    status.textContent = text;
    status.classList.toggle("dirty", kind === "dirty");
    status.classList.toggle("conflict", kind === "conflict");
  }

  function updateCommentButton() {
    const selected = Boolean(editor?.getSelectedText().trim());
    const button = $("#source-comment-btn");
    button.disabled = !selected || sourceDirty;
    button.title = sourceDirty
      ? "Save source before commenting"
      : selected ? "Comment on the selected source text (Ctrl+Alt+M, gc with Vim keys)" : "Select source text to comment";
    $("#source-page-btn").disabled = !selected;
  }

  // The words selected in the editor, shown where the Preview shows them, beside the editor in
  // Split: the server gives the text the selection shows, and the page finds it.
  async function showSelectionOnPage() {
    if (!editor?.getSelectedText().trim()) return;
    const range = editor.getSelectionRange();
    const shown = await fetchJson(`${base()}/source-shown`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        line_start: range.start.row + 1, column_start: range.start.column,
        line_end: range.end.row + 1, column_end: range.end.column,
      }),
    });
    await showWherePrinted(shown);
  }

  function setDirty(dirty) {
    sourceDirty = dirty;
    $("#source-save-btn").disabled = !dirty;
    if (dirty) {
      setStatus("Unsaved", "dirty");
      if (editor !== null) marks.clear(editor);
    }
    updateCommentButton();
  }

  function markComments() {
    if (editor === null) return;
    marks.sync(editor, sourcePath === null || sourceDirty ? null : sourcePath, marked());
  }

  // The editor's type size, kept for next time. Stepped by a pixel between 10 and 28.
  function fontSize() {
    const stored = Number(localStorage.getItem("htmlMcpSourceFontSize"));
    return stored >= 10 && stored <= 28 ? stored : 13;
  }

  function stepFontSize(step) {
    const size = Math.min(28, Math.max(10, fontSize() + step));
    localStorage.setItem("htmlMcpSourceFontSize", String(size));
    editor?.setFontSize(`${size}px`);
  }

  // Long lines wrap unless the viewer turned it off, kept for next time.
  function wraps() {
    return localStorage.getItem("htmlMcpSourceWrap") !== "0";
  }

  function applyWrap() {
    const on = wraps();
    $("#source-wrap-btn").classList.toggle("active", on);
    $("#source-wrap-btn").setAttribute("aria-pressed", String(on));
    editor?.session.setUseWrapMode(on);
  }

  function theme() {
    return document.documentElement.dataset.theme === "dark" ? "ace/theme/one_dark" : "ace/theme/textmate";
  }

  // The cursor's line held a third or a half of the way down the editor, as the comment keys hold
  // the ringed card in the list, when the viewer chose it in Settings: the keys move the text under
  // the cursor and the eyes stay where they are. A click or a drag leaves the text where it is.
  // The first lines stay at the top and the last ones at the bottom, with no room made above or
  // below the text to hold them there.
  function holdCursorLine() {
    const at = cursorAt();
    if (!editor || at === undefined || editorPointing) return;
    const { row, column } = editor.getCursorPosition();
    const top = editor.session.documentToScreenRow(row, column) * editor.renderer.lineHeight;
    editor.session.setScrollTop(Math.max(0, top - editor.renderer.scroller.clientHeight * at));
  }

  // K with Vim keys, or Ctrl+Alt+K (Cmd+Option+K), opens in the comments the comment the cursor is
  // on, as a click on its mark beside the line does.
  function showCommentAtCursor() {
    const { row, column } = editor.getCursorPosition();
    const chosen = marks.commentAt(row, column);
    if (chosen === undefined) {
      setStatus("No comment here");
      return;
    }
    // The keys go with it to the list, shown first, where K takes them back to these words.
    editor.blur();
    showComment(chosen.id);
  }

  // Ctrl+Alt+M (Cmd+Option+M), or gc with Vim keys. Comments wait for the file to be saved, as the
  // button does, and the bar says so.
  function commentSourceSelection() {
    if (sourceDirty) {
      setStatus("Save before commenting", "dirty");
      return;
    }
    openComment();
  }

  function openComment() {
    if (editor === null || sourcePath === null || sourceDirty) return;
    const range = editor.getSelectionRange();
    const quote = editor.getSelectedText();
    if (!quote.trim() || range.isEmpty()) return;
    // Back in the editor once the comment is sent or dropped, to go on from where it was.
    $("#compose-dialog").addEventListener("close", () => editor.focus(), { once: true });
    commentOn({
      kind: "source",
      file: sourcePath,
      quote,
      line_start: range.start.row + 1,
      line_end: range.end.row + 1,
      column_start: range.start.column,
      column_end: range.end.column,
    });
  }

  async function initialize() {
    if (editor !== null) return;
    if (window.ace === undefined) throw new Error("The source editor did not load");
    window.ace.config.set("basePath", `/static/${servedStatic()}/ace`);
    const made = window.ace.edit("source-editor");
    made.setTheme(theme());
    // Ace restarts its cursor's blinking animation at every move, and Safari redrew the whole
    // editor each time, so the text flickered as the cursor moved. In Safari the cursor holds
    // steady instead. Every browser on an iPhone or iPad is Safari underneath.
    if (/iPhone|iPad|iPod/.test(navigator.userAgent)
      || /^((?!chrome|chromium|android|edg).)*safari/i.test(navigator.userAgent)) {
      made.container.classList.add("steady-cursor");
    }
    made.session.setUseWorker(false);
    made.session.setMode("ace/mode/html");
    made.session.setUseWrapMode(wraps());
    made.setShowPrintMargin(false);
    made.setOptions({ fontSize: `${fontSize()}px`, scrollPastEnd: 0.25 });
    made.session.on("change", () => {
      if (!sourceLoading) setDirty(true);
    });
    made.selection.on("changeSelection", updateCommentButton);
    // A press in the text or beside it moves the cursor itself, before the editor does.
    for (const name of ["mousedown", "guttermousedown"]) made.on(name, () => { editorPointing = true; });
    document.addEventListener("pointerup", () => { editorPointing = false; }, true);
    made.selection.on("changeCursor", holdCursorLine);
    made.commands.addCommand({
      name: "saveSource",
      bindKey: { win: "Ctrl-S", mac: "Command-S" },
      exec: () => saveSource().catch((error) => alert(`Could not save: ${error.message}`)),
    });
    made.commands.addCommand({
      name: "showInPreview",
      bindKey: { win: "Ctrl-Alt-P", mac: "Command-Alt-P" },
      exec: () => showSelectionOnPage().catch((error) => alert(`Could not show it in the Preview: ${error.message}`)),
    });
    made.commands.addCommand({
      name: "showCommentAtCursor",
      bindKey: { win: "Ctrl-Alt-K", mac: "Command-Alt-K" },
      exec: () => showCommentAtCursor(),
    });
    made.commands.addCommand({
      name: "commentSource",
      bindKey: { win: "Ctrl-Alt-M", mac: "Command-Alt-M" },
      exec: commentSourceSelection,
    });
    made.on("guttermousedown", (event) => {
      if (event.domEvent.target.classList.contains("source-comment-line")) {
        const comments = marks.commentsOn(event.getDocumentPosition().row);
        if (comments.length > 0) focusComment(comments[0].id).catch((error) => console.error(error));
      }
    });
    editor = made;
    vim.attachInputMethod(made);
    vim.apply(made);
  }

  async function load(force = false) {
    await initialize();
    if (!force && sourcePath !== null) return true;
    if (sourceDirty) {
      if (!force) {
        setStatus("Changed on disk · reload", "conflict");
        return false;
      }
      if (!confirm(`Discard unsaved changes to ${sourcePath}?`)) return false;
    }
    const source = await fetchJson(`${base()}/source`);
    // The same file with the same text, as the page's own save comes back from the watcher, is
    // left as the editor holds it: set again, it lost the reader's cursor and selection a moment
    // after the save.
    if (source.path !== sourcePath || source.text !== editor.getValue()) {
      sourceLoading = true;
      editor.session.setMode("ace/mode/html");
      editor.setValue(source.text, -1);
      editor.session.getUndoManager().reset();
      sourceLoading = false;
    }
    sourcePath = source.path;
    sourceRevision = source.revision;
    sourceDirty = false;
    // The file's name alone, so the bar keeps its buttons on one row; the path is its title.
    $("#source-file").textContent = fileName(source.path);
    $("#source-file").title = displayPath(source.path, homePath);
    $("#source-save-btn").disabled = true;
    $("#source-reload-btn").disabled = false;
    setStatus("Saved");
    markComments();
    updateCommentButton();
    editor.resize();
    return true;
  }

  async function saveSource() {
    if (editor === null || sourcePath === null || !sourceDirty) return;
    setStatus("Saving…");
    const response = await fetch(`${base()}/source`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: editor.getValue(), revision: sourceRevision }),
    });
    if (response.status === 409) {
      setStatus("Changed on disk · reload", "conflict");
      throw new Error(await refusalText(response));
    }
    if (!response.ok) {
      setStatus("Save failed", "conflict");
      throw new Error(await refusalText(response));
    }
    const saved = await response.json();
    sourceRevision = saved.revision;
    sourceDirty = false;
    $("#source-save-btn").disabled = true;
    setStatus("Saved");
    await refreshComments();
  }

  return {
    load,
    path: () => sourcePath,
    revision: () => sourceRevision,
    mayLeave: () => !sourceDirty || confirm(`Discard unsaved changes to ${sourcePath}?`),
    forget() {
      sourcePath = null;
      sourceRevision = null;
      sourceDirty = false;
    },
    async changedOnDisk(path, reload) {
      if (path !== sourcePath) return;
      if (sourceDirty) setStatus("Changed on disk · reload", "conflict");
      else if (reload) await load(true);
      else {
        sourcePath = null;
        sourceRevision = null;
      }
    },
    // A comment's words, selected, the editor taking the keys unless told to leave them where they
    // are.
    showAnchor(anchor, focus) {
      if (editor === null || sourcePath !== anchor.file) return;
      editor.gotoLine(anchor.line_start, anchor.column_start, true);
      if (!anchor.stale) {
        const Range = window.ace.require("ace/range").Range;
        editor.selection.setRange(new Range(
          anchor.line_start - 1,
          anchor.column_start,
          anchor.line_end - 1,
          anchor.column_end,
        ));
      }
      if (focus) editor.focus();
    },
    // A place the server found in the file, selected and scrolled into the middle.
    showPlace(place) {
      if (sourcePath !== place.path) return;
      const Range = window.ace.require("ace/range").Range;
      editor.selection.setRange(new Range(
        place.line_start - 1, place.column_start, place.line_end - 1, place.column_end));
      editor.scrollToLine(place.line_start - 1, true, true, () => {});
      editor.focus();
    },
    markComments,
    clearSelection() {
      editor?.clearSelection();
    },
    resize() {
      editor?.resize();
    },
    setTheme() {
      editor?.setTheme(theme());
    },
    holdCursorLine,
    attach() {
      window.addEventListener("beforeunload", (event) => {
        if (!sourceDirty) return;
        event.preventDefault();
        event.returnValue = "";
      });
      $("#source-save-btn").addEventListener("click", () => {
        saveSource().catch((error) => alert(`Could not save: ${error.message}`));
      });
      $("#source-reload-btn").addEventListener("click", () => {
        load(true).catch((error) => alert(`Could not reload: ${error.message}`));
      });
      $("#source-page-btn").addEventListener("click", () => {
        showSelectionOnPage().catch((error) => alert(`Could not show it in the Preview: ${error.message}`));
      });
      $("#source-font-smaller-btn").addEventListener("click", () => stepFontSize(-1));
      $("#source-font-larger-btn").addEventListener("click", () => stepFontSize(1));
      $("#source-wrap-btn").addEventListener("click", () => {
        localStorage.setItem("htmlMcpSourceWrap", wraps() ? "0" : "1");
        applyWrap();
      });
      $("#source-vim-btn").addEventListener("click", () => {
        vim.toggle();
        vim.apply(editor);
        editor?.focus();
      });
      applyWrap();
      vim.apply(editor);
      $("#source-comment-btn").addEventListener("click", openComment);
    },
  };
}
