// The artifact tabs of the top bar, one for each artifact the project names, with the one shown
// marked and a click showing another, and what the bar and the browser's tab say of the artifact
// shown: its main file's name, with the path as its title, and Export PPTX for a deck alone.
//
// createArtifactTabs takes project (project(), alias(), artifact()) and select(alias), which shows
// another artifact. It gives render().

import { $, h, clear } from "../shared/dom.js";
import { displayPath, fileName } from "./path-display.mjs";
import { homePath } from "./project.js";

export function createArtifactTabs({ project, select }) {
  function renderTabs() {
    const tabs = $("#artifact-tabs");
    clear(tabs);
    for (const alias of Object.keys(project.project().artifacts)) {
      tabs.appendChild(h("button", {
        type: "button",
        class: `artifact-tab${alias === project.alias() ? " active" : ""}`,
        text: alias,
        onclick: () => select(alias).catch((error) => alert(error.message)),
      }));
    }
    // Tabs scroll sideways when they outnumber the row, so the open one is brought into the row.
    // The row's own scroll is set rather than scrollIntoView, which also scrolls the page.
    const active = tabs.querySelector(".artifact-tab.active");
    if (active !== null) {
      const left = active.offsetLeft - tabs.offsetLeft;
      if (left < tabs.scrollLeft) tabs.scrollLeft = left;
      else if (left + active.offsetWidth > tabs.scrollLeft + tabs.clientWidth) {
        tabs.scrollLeft = left + active.offsetWidth - tabs.clientWidth;
      }
    }
  }

  function renderNames() {
    const artifact = project.artifact();
    // The file's name alone, as the editor shows it; the path is its title.
    $("#main-file").textContent = fileName(artifact.main_file);
    $("#main-file").title = displayPath(artifact.main_file, homePath());
    // The tab carries the file being reviewed, so several projects open at once stay apart in the
    // browser's tab strip.
    document.title = fileName(artifact.main_file);
    $("#download-pptx-btn").hidden = artifact.layout !== "slides";
  }

  return {
    render() {
      renderTabs();
      renderNames();
    },
  };
}
