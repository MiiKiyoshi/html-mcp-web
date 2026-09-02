// A record of what the artifact's touches do, drawn over the page for a device that
// cannot be watched from where the code is written. Loaded only when the address carries
// ?trace. Each line: seconds since load, the event, the fingers, whether the page took
// the event (dp), then the artifact window's scroll, zoom, the holder's transform, the
// visual viewport (scale@offset size), the client size and the scroll size.
const lines = [];
const box = document.createElement("pre");
Object.assign(box.style, {
  position: "fixed", left: "0", bottom: "0", zIndex: "1000", margin: "0", padding: "4px",
  maxHeight: "48vh", width: "100vw", overflow: "hidden", boxSizing: "border-box",
  background: "rgba(0, 0, 0, .82)", color: "#9f9", font: "9px/1.25 ui-monospace, monospace",
  pointerEvents: "none", whiteSpace: "pre-wrap", wordBreak: "break-all",
});
document.body.appendChild(box);
const started = performance.now();

function log(text) {
  lines.push(`${((performance.now() - started) / 1000).toFixed(2)} ${text}`);
  if (lines.length > 30) lines.shift();
  box.textContent = lines.join("\n");
}
// The viewer's own scripts write here too, when there is something to record: the
// comment list's reveal of an opened card, among them.
window.htmlMcpTrace = log;

function install() {
  const frame = document.querySelector("#artifact-frame");
  const win = frame.contentWindow;
  const doc = frame.contentDocument;
  if (win === null || doc === null || doc.body === null) return;
  if (doc.body.dataset.traced === "1") return;
  doc.body.dataset.traced = "1";
  const state = () => {
    const root = doc.documentElement;
    const holder = doc.querySelector("main.pages");
    const vv = win.visualViewport;
    const transform = holder === null ? "-" : (holder.style.transform || "-");
    return `s=${Math.round(win.scrollX)},${Math.round(win.scrollY)}`
      + ` z=${root.style.getPropertyValue("--html-mcp-zoom") || "?"}`
      + ` tf=${transform.replace(/px/g, "").replace(/(\.\d)\d+/g, "$1").slice(0, 36)}`
      + ` vv=${vv ? `${vv.scale.toFixed(2)}@${Math.round(vv.offsetLeft)},${Math.round(vv.offsetTop)} ${Math.round(vv.width)}x${Math.round(vv.height)}` : "-"}`
      + ` cw=${root.clientWidth}x${root.clientHeight} sw=${root.scrollWidth}x${root.scrollHeight}`;
  };
  let lastMove = 0;
  for (const kind of ["touchstart", "touchmove", "touchend", "touchcancel"]) {
    // In the bubble phase, after the viewer's capture listener, so dp says what it did.
    doc.addEventListener(kind, (event) => {
      if (kind === "touchmove") {
        if (performance.now() - lastMove < 150) return;
        lastMove = performance.now();
      }
      const fingers = Array.from(event.touches)
        .map((touch) => `${Math.round(touch.clientX)},${Math.round(touch.clientY)}`).join(" ");
      log(`${kind.slice(5) || "start"} n=${event.touches.length} [${fingers}] dp=${event.defaultPrevented ? 1 : 0} ${state()}`);
      if (kind === "touchend" || kind === "touchcancel") {
        for (const delay of [60, 250, 700, 1500]) setTimeout(() => log(`+${delay}ms ${state()}`), delay);
      }
    }, { passive: true });
  }
  for (const kind of ["gesturestart", "gesturechange", "gestureend"]) {
    doc.addEventListener(kind, (event) => {
      log(`${kind} scale=${event.scale?.toFixed(2)} dp=${event.defaultPrevented ? 1 : 0}`);
    }, { passive: true });
  }
  let lastScroll = 0;
  win.addEventListener("scroll", () => {
    if (performance.now() - lastScroll < 150) return;
    lastScroll = performance.now();
    log(`scroll ${state()}`);
  }, { passive: true });
  if (win.visualViewport) {
    for (const kind of ["resize", "scroll"]) {
      win.visualViewport.addEventListener(kind, () => log(`vv-${kind} ${state()}`), { passive: true });
    }
  }
  if (window.visualViewport) {
    for (const kind of ["resize", "scroll"]) {
      window.visualViewport.addEventListener(kind, () => {
        const vv = window.visualViewport;
        log(`top-vv-${kind} ${vv.scale.toFixed(2)}@${Math.round(vv.offsetLeft)},${Math.round(vv.offsetTop)}`);
      }, { passive: true });
    }
  }
  log(`traced ${navigator.userAgent.slice(0, 60)}`);
  log(`ready ${state()}`);
}

const frame = document.querySelector("#artifact-frame");
frame.addEventListener("load", () => setTimeout(install, 300));
setTimeout(install, 300);
