export function createPresentation(state, dependencies) {
  const {
    $,
    artifactPages,
    frameDocument,
    frameWindow,
    hideSelectionButton,
    renderPages,
    scheduleLayoutCheck,
    updatePageScale,
    visiblePageNumber,
  } = dependencies;

  function updateControls() {
    const count = artifactPages().length;
    const number = count === 0 ? 0 : Math.min(Math.max(state.currentPage || 1, 1), count);
    $("#presentation-page").textContent = `${number} / ${count}`;
    $("#presentation-prev-btn").disabled = number <= 1;
    $("#presentation-next-btn").disabled = number >= count;
  }

  function setPage(number) {
    const pages = artifactPages();
    if (pages.length === 0) {
      state.currentPage = null;
      updateControls();
      return false;
    }
    const previous = state.currentPage;
    state.currentPage = Math.min(Math.max(number, 1), pages.length);
    for (const [index, page] of pages.entries()) {
      page.classList.toggle("html-mcp-current-page", index + 1 === state.currentPage);
    }
    updateControls();
    updatePageScale();
    renderPages();
    return state.currentPage !== previous;
  }

  function resetWheelGesture() {
    state.presentationWheelEvents = [];
    state.presentationLastWheelStep = 0;
  }

  function movePage(delta) {
    if (!state.slideShow) return false;
    return setPage((state.currentPage || 1) + delta);
  }

  function activate() {
    state.slideShow = true;
    const pane = $("#artifact-pane");
    pane.classList.add("slide-show");
    frameDocument().documentElement.dataset.htmlMcpPresentation = "slides";
    setPage(state.currentPage || visiblePageNumber() || 1);
    $("#artifact-frame").focus({ preventScroll: true });
    frameWindow().focus();
    frameWindow().requestAnimationFrame(() => {
      $("#artifact-frame").focus({ preventScroll: true });
      frameWindow().focus();
    });
  }

  function deactivate() {
    if (!state.slideShow) return;
    state.slideShow = false;
    $("#artifact-pane").classList.remove("slide-show");
    resetWheelGesture();
    delete frameDocument().documentElement.dataset.htmlMcpPresentation;
    for (const page of artifactPages()) page.classList.remove("html-mcp-current-page");
    updatePageScale();
    const number = state.currentPage;
    if (number !== null) {
      frameWindow().requestAnimationFrame(() => artifactPages()[number - 1]?.scrollIntoView({ block: "start" }));
    }
  }

  function syncFullscreenMode() {
    const fullscreen = document.fullscreenElement === $("#artifact-pane");
    $("#fullscreen-btn").setAttribute("aria-pressed", fullscreen ? "true" : "false");
    if (fullscreen) frameDocument().documentElement.dataset.htmlMcpFullscreen = "";
    else delete frameDocument().documentElement.dataset.htmlMcpFullscreen;
    if (fullscreen) hideSelectionButton();
    if (fullscreen && state.artifact.layout === "slides") {
      activate();
    } else {
      const wasSlideShow = state.slideShow;
      deactivate();
      updatePageScale();
      if (wasSlideShow) scheduleLayoutCheck();
    }
  }

  async function toggleFullscreen() {
    if (document.fullscreenElement === $("#artifact-pane")) await document.exitFullscreen();
    else await $("#artifact-pane").requestFullscreen();
  }

  function targetIsInteractive(target) {
    return typeof target?.closest === "function"
      && target.closest("a, button, input, textarea, select, [contenteditable]") !== null;
  }

  function handleKeydown(event) {
    if (!state.slideShow || event.metaKey || event.ctrlKey || event.altKey) return;
    if (targetIsInteractive(event.target)) return;
    const nextKeys = new Set(["n", "N", "Enter", " ", "PageDown", "ArrowRight", "ArrowDown"]);
    const previousKeys = new Set(["p", "P", "Backspace", "PageUp", "ArrowLeft", "ArrowUp"]);
    if (nextKeys.has(event.key)) {
      event.preventDefault();
      movePage(1);
    } else if (previousKeys.has(event.key)) {
      event.preventDefault();
      movePage(-1);
    } else if (event.key === "Home") {
      event.preventDefault();
      setPage(1);
    } else if (event.key === "End") {
      event.preventDefault();
      setPage(artifactPages().length);
    }
  }

  function handleClick(event) {
    if (!state.slideShow || event.button !== 0) return;
    if (state.suppressPresentationClick) {
      state.suppressPresentationClick = false;
      return;
    }
    if (targetIsInteractive(event.target)) return;
    const selection = frameWindow().getSelection();
    if (selection !== null && !selection.isCollapsed) return;
    movePage(1);
  }

  function handlePointerDown(event) {
    if (!state.slideShow || event.pointerType !== "touch") return;
    state.presentationPointer = { id: event.pointerId, x: event.clientX, y: event.clientY };
  }

  function handlePointerUp(event) {
    const start = state.presentationPointer;
    state.presentationPointer = null;
    if (!state.slideShow || start === null || event.pointerId !== start.id) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (Math.abs(dx) < 50 || Math.abs(dx) < Math.abs(dy) * 1.2) return;
    state.suppressPresentationClick = true;
    movePage(dx < 0 ? 1 : -1);
  }

  function handleWheel(event) {
    if (!state.slideShow) return;
    event.preventDefault();
    const unit = event.deltaMode === WheelEvent.DOM_DELTA_LINE
      ? 40
      : event.deltaMode === WheelEvent.DOM_DELTA_PAGE ? 800 : 1;
    const rawDelta = Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX;
    if (rawDelta === 0) return;
    const wheelEvent = {
      time: performance.now(),
      delta: Math.abs(rawDelta * unit),
      direction: Math.sign(rawDelta),
    };
    const previous = state.presentationWheelEvents.at(-1);
    state.presentationWheelEvents.push(wheelEvent);
    if (state.presentationWheelEvents.length > 2) state.presentationWheelEvents.shift();
    const newIntent = previous === undefined
      || wheelEvent.direction !== previous.direction
      || wheelEvent.delta > previous.delta
      || wheelEvent.time > previous.time + 150;
    const significant = wheelEvent.delta >= 6;
    const duplicate = significant && wheelEvent.time - state.presentationLastWheelStep < 60;
    if (newIntent && significant && !duplicate) {
      movePage(wheelEvent.direction);
      state.presentationLastWheelStep = wheelEvent.time;
    }
  }

  return {
    activate,
    handleClick,
    handleKeydown,
    handlePointerDown,
    handlePointerUp,
    handleWheel,
    movePage,
    setPage,
    syncFullscreenMode,
    toggleFullscreen,
    updateControls,
  };
}
