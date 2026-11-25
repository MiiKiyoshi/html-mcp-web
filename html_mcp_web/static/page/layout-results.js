// The layout check's result on the page: the status beside the file's name in the top bar, and the
// Problems tab, which lists the artifact's error and the build's, then the layout's errors and
// warnings for the revision shown, each leading to its element. The server checks a revision in a
// browser of its own, which loads this page with a token; only there does this page measure, and
// it measures again as the deck's fonts and images arrive (layout-check.js). Every other page shows
// that check's result.
//
// createLayoutResults takes project (project(), alias(), artifact(), revision(), base(),
// checked(record)) and showing(), whether the slide show is on, which the check waits out. It
// gives show(), the result for the revision shown; schedule(), a check at the next frame; and
// watch(doc, images), a check again as the document's fonts and these images arrive.

import { $, h, clear } from "../shared/dom.js";
import { createLayoutChecks } from "../layout-check.js";
import { fetchJson } from "./fetch-json.js";
import { deckPages, frameDocument, frameWindow } from "./deck-dom.js";

export function createLayoutResults({ project, showing }) {
  // layout-check.js reads what it checks from one object it is handed, and keeps two fields of its
  // own there: the frame its next check waits for, and why its last result could not be reported.
  // The object reads the rest from their owners, and the result the check takes for the artifact
  // goes to the project (project.checked), which keeps it for the next tab switch to read back.
  const facts = {
    get project() { return project.project(); },
    get alias() { return project.alias(); },
    get artifact() { return project.artifact(); },
    set artifact(record) { project.checked(record); },
    get revision() { return project.revision(); },
    get slideShow() { return showing(); },
    layoutFrame: null,
    layoutCheckError: null,
  };
  const checks = createLayoutChecks({
    $, artifactBase: () => project.base(), artifactPages: deckPages, clear, fetchJson, frameDocument, frameWindow,
    h, state: facts,
  });

  function watch(doc, images) {
    doc.fonts.ready.then(checks.scheduleLayoutCheck);
    // An image that finishes loading after the check changes the layout the check measured, so
    // each pending image checks again.
    for (const img of images) {
      if (!img.complete) {
        img.addEventListener("load", checks.scheduleLayoutCheck, { once: true });
        img.addEventListener("error", checks.scheduleLayoutCheck, { once: true });
      }
    }
  }

  return {
    show: checks.updateLayoutUi,
    schedule: checks.scheduleLayoutCheck,
    watch,
  };
}
