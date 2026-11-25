// The project as the server last described it, and the artifact of it the page shows. The
// description holds each artifact's revision, layout, files and layout check, whether the server
// checks layouts, the agents the bell may call, and the code the server serves. A description
// from a server that serves other code than this page runs reloads the page, which then gets that
// code: the modules it loaded stay what they were however the server changes.
//
// createProject({ leaving }) takes leaving(), told just before the page reloads for other code.
// It gives the readers project(), the description; alias(), the artifact shown, null before the
// first description; artifact(), the shown artifact's description as last taken; revision(), the
// revision of it the page shows; base(), the route of its calls, null before there is one; and
// url(), the address of the revision shown. Its commands: adopt(description), which answers
// whether the page goes on with it; read(), which asks the server and shows the artifact a link's
// ?artifact= names, else the one the reader last chose, else the first, and answers as adopt does;
// show(alias); choose(alias), shown and kept for next time; take(artifact), the shown artifact's
// description, with its revision; and checked(record), the shown artifact's description as the
// layout check answered it, which the project's description keeps too. servedStatic() and
// homePath() read what the server stamped into the page: the code it was built with, and the
// folder a path is shown from as ~.

import { fetchJson } from "./fetch-json.js";

// What the browser keeps the reader's choice of artifact under.
const CHOSEN = "htmlMcpArtifact";

// The tag of the code this page was built with, stamped into it by the server.
export function servedStatic() {
  return document.querySelector('meta[name="html-mcp-static"]')?.content ?? null;
}

// The home folder of the server's user, stamped into the page by the server, under which a path
// is shown from ~.
export function homePath() {
  return document.querySelector('meta[name="html-mcp-home"]')?.content ?? "";
}

export function createProject({ leaving }) {
  let described = null;
  let shownAlias = null;
  let shownArtifact = null;
  let shownRevision = null;

  // Every description, whether asked for or sent, passes through here.
  function adopt(description) {
    if ((description.static ?? null) !== servedStatic()) {
      leaving();
      location.reload();
      return false;
    }
    described = description;
    return true;
  }

  function show(alias) {
    shownAlias = alias;
    take(described.artifacts[alias]);
  }

  function take(artifact) {
    shownArtifact = artifact;
    shownRevision = artifact.revision;
  }

  function base() {
    return shownAlias === null ? null : `/artifacts/${encodeURIComponent(shownAlias)}`;
  }

  async function read() {
    if (!adopt(await fetchJson("/state"))) return false;
    const ids = Object.keys(described.artifacts);
    // ?artifact= names the artifact to open: a shareable link, and how the server's own
    // headless browser is pointed at the artifact whose layout it has to check.
    const asked = new URLSearchParams(location.search).get("artifact");
    const remembered = asked !== null ? asked : localStorage.getItem(CHOSEN);
    show(remembered !== null && ids.includes(remembered) ? remembered : ids[0]);
    return true;
  }

  return {
    project: () => described,
    alias: () => shownAlias,
    artifact: () => shownArtifact,
    revision: () => shownRevision,
    base,
    url: () => `${base()}/artifact?v=${encodeURIComponent(shownRevision)}&shared=1`,
    adopt,
    read,
    show,
    choose(alias) {
      show(alias);
      localStorage.setItem(CHOSEN, alias);
    },
    take,
    checked(record) {
      shownArtifact = record;
      described.artifacts[shownAlias] = record;
    },
  };
}
