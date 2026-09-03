export function createComments(dependencies) {
  const {
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
  } = dependencies;

  // Enter writes a new line, as it does in any box of text. What sends it is shift with
  // enter, which keeps the hand on the keyboard, or the command or control key with it,
  // which is the same key a comment is sent with elsewhere.
  function sendOn(input, send) {
    input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      if (!(event.shiftKey || event.metaKey || event.ctrlKey) || event.altKey) return;
      event.preventDefault();
      send();
    });
  }

  function filteredCommentsPath() {
    const status = $("#comment-filter").value;
    return status === "all" ? `${artifactBase()}/comments` : `${artifactBase()}/comments?status=${encodeURIComponent(status)}`;
  }
  
  function captureCommentUi() {
    const list = $("#comments-list");
    const active = document.activeElement;
    const focus = active?.classList.contains("comment-form-input") ? {
      id: active.closest("[data-comment-id]").dataset.commentId,
      start: active.selectionStart,
      end: active.selectionEnd,
    } : null;
    return { scrollTop: list.scrollTop, focus };
  }
  
  function restoreCommentUi(snapshot) {
    const list = $("#comments-list");
    list.scrollTop = snapshot.scrollTop;
    if (snapshot.focus === null) return;
    const card = Array.from(document.querySelectorAll("[data-comment-id]")).find(
      (node) => node.dataset.commentId === snapshot.focus.id,
    );
    const input = card?.querySelector(".comment-form-input");
    if (input === null || input === undefined) return;
    input.focus({ preventScroll: true });
    input.setSelectionRange(snapshot.focus.start, snapshot.focus.end);
  }
  
  async function refreshComments() {
    const ui = captureCommentUi();
    const payload = await fetchJson(filteredCommentsPath());
    state.comments = payload.comments;
    renderComments();
    renderHighlights();
    restoreCommentUi(ui);
  }
  
  function formatTime(value) {
    // Show the stored ISO 8601 string verbatim. A locale-formatted time cannot be matched against logs and MCP output.
    return value;
  }
  
  function anchorSummary(anchor) {
    if (anchor.kind === "artifact") return { label: "artifact", quote: "Whole artifact" };
    if (anchor.kind === "text") return { label: "", quote: anchor.quote };
    if (anchor.kind === "page") return { label: `p${anchor.number}`, quote: anchor.title };
    throw new Error(`unknown anchor kind: ${anchor.kind}`);
  }
  
  function actionButton(label, handler, className = "") {
    return h("button", { type: "button", class: className, onclick: handler, text: label });
  }
  
  function setActiveForm(commentId, mode) {
    state.activeForm = { commentId, mode, draft: "" };
    state.expanded.add(commentId);
    renderComments();
    const card = Array.from(document.querySelectorAll("[data-comment-id]")).find((node) => node.dataset.commentId === commentId);
    card?.querySelector(".comment-form-input")?.focus({ preventScroll: true });
  }
  
  const formConfig = {
    reply: { placeholder: "Reply", key: "text", label: "Post reply" },
  };
  
  function renderForm(comment) {
    if (state.activeForm === null || state.activeForm.commentId !== comment.id) return null;
    const active = state.activeForm;
    const config = formConfig[active.mode];
    const input = h("textarea", { class: "comment-form-input", rows: "3", placeholder: config.placeholder });
    input.value = active.draft;
    input.addEventListener("input", () => {
      if (state.activeForm === active) active.draft = input.value;
    });
    let submitting = false;
    const submit = async () => {
      const value = input.value.trim();
      if (!value || submitting) return;
      submitting = true;
      input.disabled = true;
      submitButton.disabled = true;
      try {
        await mutateComment(comment.id, active.mode, { [config.key]: value });
        state.activeForm = null;
        await refreshComments();
      } catch (error) {
        alert(`Could not save: ${error.message}`);
        submitting = false;
        input.disabled = false;
        submitButton.disabled = false;
        input.focus();
      }
    };
    const submitButton = actionButton(config.label, submit);
    sendOn(input, submit);
    return h("div", { class: "comment-form" }, input,
      h("div", { class: "form-actions" },
        submitButton,
        actionButton("Cancel", () => { state.activeForm = null; renderComments(); })));
  }
  
  function startEntryEdit(commentId, index, text) {
    state.editingEntry = { commentId, index, draft: text };
    renderComments();
    const card = Array.from(document.querySelectorAll("[data-comment-id]")).find(
      (node) => node.dataset.commentId === commentId,
    );
    card?.querySelector(".entry-edit-input")?.focus({ preventScroll: true });
  }

  // Editing rewrites the entry in place: the author and time stay, so a typo fix
  // does not read as a new message in the thread.
  function renderEntryEditor(commentId, index) {
    const editing = state.editingEntry;
    const input = h("textarea", { class: "comment-form-input entry-edit-input", rows: "3" });
    input.value = editing.draft;
    input.addEventListener("input", () => {
      if (state.editingEntry === editing) editing.draft = input.value;
    });
    const save = async () => {
      const value = input.value.trim();
      if (!value) return;
      input.disabled = true;
      try {
        await fetchJson(`${artifactBase()}/comments/${commentId}/edit`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ index, text: value }),
        });
      } catch (error) {
        alert(`Could not save: ${error.message}`);
        input.disabled = false;
        input.focus();
        return;
      }
      state.editingEntry = null;
      await refreshComments();
    };
    sendOn(input, save);
    return h("div", { class: "comment-form" }, input,
      h("div", { class: "form-actions" },
        actionButton("Save", save),
        actionButton("Cancel", () => { state.editingEntry = null; renderComments(); })));
  }

  function renderComment(comment) {
    const anchor = anchorSummary(comment.anchor);
    const expanded = state.expanded.has(comment.id);
    const card = h("article", {
      class: `comment-card${state.focusedCommentId === comment.id ? " focused" : ""}${state.unattached.has(comment.id) ? " unattached" : ""}`,
      data: { commentId: comment.id },
    });
    const box = h("input", { class: "comment-pick", type: "checkbox",
                             title: "Pick this comment" });
    box.checked = state.picked.has(comment.id);
    // The box is inside the summary, which opens the card: picking is not opening.
    box.addEventListener("click", (event) => event.stopPropagation());
    box.addEventListener("change", () => {
      if (box.checked) state.picked.add(comment.id);
      else state.picked.delete(comment.id);
      renderPickedActions();
    });
    card.appendChild(h("div", { class: "comment-summary", onclick: () => {
      state.focusedCommentId = comment.id;
      const opening = !state.expanded.has(comment.id);
      if (opening) state.expanded.add(comment.id);
      else state.expanded.delete(comment.id);
      renderComments();
      if (opening) revealCard(comment.id);
      jumpToComment(comment.id);
    } },
    h("div", { class: "anchor-label" },
      box,
      h("span", { class: "comment-id", text: comment.id }),
      h("span", { class: `status-pill ${comment.status}`, text: `[${comment.status}]` }),
      state.unattached.has(comment.id) ? h("span", { class: "stale-pill", text: "[stale]" }) : null,
      anchor.label === "" ? null : h("span", { class: "anchor-kind", text: anchor.label })),
    // Collapsed cards show the comment text. To see what it is attached to, click the card to jump to the source.
    expanded ? null : h("div", { class: "comment-preview", text: comment.thread[0].text })));
    if (!expanded) return card;
    const body = h("div", { class: "comment-body" });
    if (comment.anchor.kind !== "artifact") {
      body.appendChild(h("div", { class: "anchor-quote", text: anchor.quote.length > 180 ? `${anchor.quote.slice(0, 177)}…` : anchor.quote }));
    }
    for (const [index, entry] of comment.thread.entries()) {
      const editing = state.editingEntry !== null
        && state.editingEntry.commentId === comment.id
        && state.editingEntry.index === index;
      body.appendChild(h("div", { class: "thread-entry" },
        h("div", { class: "thread-meta" },
          h("span", { text: `${entry.author} · ${formatTime(entry.at)}` }),
          entry.author === "human" && !editing
            ? actionButton("Edit", () => startEntryEdit(comment.id, index, entry.text), "link")
            : null),
        editing ? renderEntryEditor(comment.id, index)
          : (entry.text === "" ? null : h("div", { class: "thread-text", text: entry.text })),
        entry.edits === undefined || entry.edits.length === 0 ? null : h("ul", { class: "thread-edits" },
          entry.edits.map((edit) => h("li", { text: edit })))));
    }
    const actions = h("div", { class: "comment-actions" });
    if (comment.status === "open") {
      actions.append(
        actionButton("Reply", () => setActiveForm(comment.id, "reply")),
        actionButton("Resolve", () => flipStatus(comment.id, "resolve", "summary")),
      );
    } else {
      // Reopening is a one-click status flip like closing: the status says what happened,
      // and anything more belongs in a reply, which is a click away either way.
      actions.appendChild(actionButton("Reopen", () => flipStatus(comment.id, "reopen", "text")));
    }
    actions.appendChild(actionButton("Delete", () => deleteComment(comment.id), "danger"));
    body.appendChild(actions);
    const form = renderForm(comment);
    if (form !== null) body.appendChild(form);
    card.appendChild(body);
    return card;
  }
  
  function renderComments() {
    const list = $("#comments-list");
    const scrollTop = list.scrollTop;
    clear(list);
    if (state.comments.length === 0) list.appendChild(h("p", { class: "placeholder", text: "No comments in this view." }));
    else for (const comment of state.comments) list.appendChild(renderComment(comment));
    list.scrollTop = scrollTop;
    renderPickedActions();
    renderFoldAction();
    const open = state.comments.filter((comment) => comment.status === "open").length;
    const count = $("#open-count");
    count.textContent = String(open);
    count.classList.toggle("hidden", open === 0);
  }
  
  // What the picked comments can be sent to, which is decided by the state they are in:
  // open ones close, closed ones reopen. Both buttons show a count, so a mixed pick says
  // exactly what each press will touch, and neither appears with nothing to touch.
  function renderPickedActions() {
    const picked = state.comments.filter((comment) => state.picked.has(comment.id));
    const open = picked.filter((comment) => comment.status === "open").map((comment) => comment.id);
    const closed = picked.filter((comment) => comment.status !== "open").map((comment) => comment.id);
    const shown = state.comments.length;
    const all = $("#pick-all-btn");
    all.classList.toggle("hidden", shown === 0);
    all.textContent = picked.length === shown && shown > 0 ? "Clear" : "Select all";
    const resolve = $("#resolve-picked-btn");
    resolve.classList.toggle("hidden", open.length === 0);
    resolve.textContent = `Resolve ${open.length}`;
    resolve.dataset.ids = open.join(" ");
    const reopen = $("#reopen-picked-btn");
    reopen.classList.toggle("hidden", closed.length === 0);
    reopen.textContent = `Reopen ${closed.length}`;
    reopen.dataset.ids = closed.join(" ");
  }

  // Every card in the view opened, or every one closed: which of the two the button does
  // is read off the cards, so it always offers the one that changes something.
  function renderFoldAction() {
    const shown = state.comments.map((comment) => comment.id);
    const button = $("#fold-all-btn");
    button.classList.toggle("hidden", shown.length === 0);
    button.textContent = shown.length > 0 && shown.every((id) => state.expanded.has(id))
      ? "Collapse all" : "Expand all";
  }

  function foldAll() {
    const shown = state.comments.map((comment) => comment.id);
    const allOpen = shown.every((id) => state.expanded.has(id));
    for (const id of shown) {
      if (allOpen) state.expanded.delete(id);
      else state.expanded.add(id);
    }
    renderComments();
  }

  function pickAll() {
    const shown = state.comments.map((comment) => comment.id);
    const already = shown.every((id) => state.picked.has(id));
    for (const id of shown) {
      if (already) state.picked.delete(id);
      else state.picked.add(id);
    }
    renderComments();
  }

  async function setPickedStatus(ids, status) {
    await fetchJson(`${artifactBase()}/comments/update`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment_ids: ids, status, author: "human" }),
    });
    for (const id of ids) state.picked.delete(id);
    await refreshComments();
  }

  function switchSidebarTab(name) {
    for (const button of document.querySelectorAll(".tab-btn")) {
      button.classList.toggle("active", button.dataset.tab === name);
    }
    for (const pane of document.querySelectorAll(".tab-pane")) {
      pane.classList.toggle("active", pane.id === `tab-${name}`);
    }
  }
  
  async function mutateComment(commentId, action, body) {
    await fetchJson(`${artifactBase()}/comments/${commentId}/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }
  
  // A status change is one click: content lives in replies, so resolve and reopen send
  // an empty text and the store records no extra thread entry.
  async function flipStatus(commentId, action, key) {
    try {
      await mutateComment(commentId, action, { [key]: "" });
    } catch (error) {
      alert(`Could not save: ${error.message}`);
      return;
    }
    if (state.activeForm?.commentId === commentId) state.activeForm = null;
    await refreshComments();
  }

  async function deleteComment(commentId) {
    if (!confirm("Delete this comment thread?")) return;
    await fetchJson(`${artifactBase()}/comments/${commentId}`, { method: "DELETE" });
    state.expanded.delete(commentId);
    if (state.activeForm?.commentId === commentId) state.activeForm = null;
    if (state.editingEntry?.commentId === commentId) state.editingEntry = null;
    await refreshComments();
  }
  
  // A card opened at the foot of the list unfolds below the fold, and the reader had to
  // scroll after every open to read what they had just asked for. The list scrolls by
  // what the card overhangs, so the whole of it shows; a card taller than the list is
  // brought to the top instead, which is as much of it as there is room for.
  // The opened card is brought into the list's box: its foot at the box's foot when it
  // fits, its head at the box's head when it does not. Done at once, then again a frame
  // later and once more shortly after: the measurement taken inside the click is not
  // always the one the engine paints (Safari laid the list out again after the click),
  // and the reader was left to scroll after opening the last card of the list.
  function revealCard(commentId) {
    const settle = () => {
      const list = $("#comments-list");
      const card = Array.from(list.querySelectorAll("[data-comment-id]")).find(
        (node) => node.dataset.commentId === commentId);
      if (card === undefined || !state.expanded.has(commentId)) return;
      const margin = 8;
      growPanelFor(card.getBoundingClientRect().height + margin * 2);
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
      window.htmlMcpTrace?.(`reveal ${commentId} card=${Math.round(cardBox.top)}..${Math.round(cardBox.bottom)}`
        + ` list=${Math.round(listBox.top)}..${Math.round(listBox.bottom)} over=${Math.round(overhang)}`
        + ` scroll=${Math.round(list.scrollTop)}/${list.scrollHeight - list.clientHeight}`);
    };
    settle();
    requestAnimationFrame(settle);
    setTimeout(settle, 150);
  }

  // Under the artifact, the comments get a slice of a phone's screen, and a thread opened
  // there is usually taller than the slice: scrolling cannot show what does not fit, so
  // the reader was left scrolling after every open. The panel takes the room the card
  // needs instead, up to what the drag bar itself allows, and the artifact keeps the
  // rest. Beside the artifact it is already full height, so there is nothing to take.
  function growPanelFor(wanted) {
    const layout = $(".layout");
    const sidebar = $("#sidebar");
    const list = $("#comments-list");
    const stacked = Math.abs(sidebar.getBoundingClientRect().width
      - layout.getBoundingClientRect().width) < 2;
    if (!stacked) return;
    const shortfall = wanted - list.getBoundingClientRect().height;
    if (shortfall <= 0) return;
    const height = sidebar.getBoundingClientRect().height + shortfall;
    const limited = Math.round(Math.max(90, Math.min(height, window.innerHeight - 140)));
    layout.style.setProperty("--html-mcp-panel-height", `${limited}px`);
  }

  function jumpToComment(commentId) {
    const comment = state.comments.find((value) => value.id === commentId);
    if (comment === undefined || comment.anchor.kind !== "text") return;
    const range = resolveAnchor(comment.anchor);
    if (range === null) return;
    const element = range.startContainer.nodeType === Node.ELEMENT_NODE
      ? range.startContainer
      : range.startContainer.parentElement;
    element?.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => {
      const marks = frameDocument().querySelectorAll(`[data-comment-id="${CSS.escape(commentId)}"]`);
      marks.forEach((mark) => mark.classList.add("flash"));
      setTimeout(() => marks.forEach((mark) => mark.classList.remove("flash")), 1000);
    }, 350);
  }
  
  // From its badge on the page a card opens the same way it does from the list: whole,
  // and at the foot of the box when it sits at the foot of the list. Centred, a tall card
  // at the foot was cut off below and the reader scrolled after every open.
  function focusComment(commentId) {
    state.focusedCommentId = commentId;
    state.expanded.add(commentId);
    renderComments();
    revealCard(commentId);
  }
  
  function composeAnchorText(anchor) {
    if (anchor.kind === "text") return anchor.quote;
    if (anchor.kind === "page") return `Page ${anchor.number}: ${anchor.title}`;
    return "Whole artifact";
  }
  
  function openCompose(anchor) {
    state.pendingAnchor = anchor;
    $("#compose-anchor").textContent = composeAnchorText(anchor);
    $("#compose-text").value = "";
    $("#compose-dialog").showModal();
    $("#compose-text").focus();
  }
  
  function installComposeKeys() {
    sendOn($("#compose-text"), () => $("#compose-form").requestSubmit());
  }

  async function submitCompose(event) {
    event.preventDefault();
    if (state.composeSubmitting || state.pendingAnchor === null) return;
    const text = $("#compose-text").value.trim();
    if (!text) return;
    state.composeSubmitting = true;
    const submit = $("#compose-submit");
    submit.disabled = true;
    submit.textContent = "Posting…";
    try {
      await fetchJson(`${artifactBase()}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ anchor: state.pendingAnchor, text }),
      });
      $("#compose-dialog").close();
      state.pendingAnchor = null;
      state.selectionAnchor = null;
      frameWindow().getSelection()?.removeAllRanges();
      hideSelectionButton();
      await refreshComments();
    } catch (error) {
      alert(`Could not save comment: ${error.message}`);
    } finally {
      state.composeSubmitting = false;
      submit.disabled = false;
      submit.textContent = "Post";
    }
  }
  

  return {
    actionButton,
    captureCommentUi,
    focusComment,
    openCompose,
    foldAll,
    pickAll,
    refreshComments,
    renderComments,
    renderPickedActions,
    setPickedStatus,
    restoreCommentUi,
    installComposeKeys,
    submitCompose,
    switchSidebarTab,
  };
}
