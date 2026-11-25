// The speaker scripts a slides template puts after each page, shown or hidden by the button in the
// artifact's bar. The choice is the reader's, kept by the browser, and set on the artifact's
// document as an attribute its stylesheet reads, so it holds through reloads and tab switches. The
// button rests while the artifact has no scripts.
//
// createScripts takes nothing. It gives apply(), the choice set on the document shown and on the
// button; changed(listener), which hands in a function called when the reader shows or hides
// them; and attach().

import { $ } from "../shared/dom.js";
import { frameDocument } from "./deck-dom.js";
import { createListeners } from "../shared/listeners.js";

const KEPT = "htmlMcpScriptsHidden";

export function createScripts() {
  const changed = createListeners();
  const hidden = () => localStorage.getItem(KEPT) === "1";

  function apply() {
    const off = hidden();
    const doc = frameDocument();
    if (doc?.documentElement) {
      if (off) doc.documentElement.dataset.htmlMcpScriptsHidden = "";
      else delete doc.documentElement.dataset.htmlMcpScriptsHidden;
    }
    const button = $("#scripts-btn");
    button.classList.toggle("active", !off);
    button.setAttribute("aria-pressed", off ? "false" : "true");
    const hasScripts = doc?.querySelector("main.pages > .script-block") !== null;
    button.disabled = !hasScripts;
  }

  return {
    apply,
    changed: changed.add,
    attach() {
      $("#scripts-btn").addEventListener("click", () => {
        localStorage.setItem(KEPT, hidden() ? "0" : "1");
        apply();
        changed.tell();
      });
    },
  };
}
