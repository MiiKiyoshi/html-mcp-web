// Export PDF and Export PPTX in the ⋯ menu. The PDF and the pptx are built on the server while
// their button shows it is busy and takes no second press; the file then downloads. A plain link
// would leave the button silent for the seconds the export takes, and each further press would
// start another export and download another copy. attachExport({ base }) wires the two buttons,
// base() giving the route of the artifact's calls.

import { $, h } from "../shared/dom.js";

export function attachExport({ base }) {
  async function download(button, format) {
    if (button.disabled) return;
    const label = button.dataset.label;
    const title = button.dataset.title ??= button.title;
    button.disabled = true;
    button.classList.add("busy");
    button.textContent = `${label}…`;
    try {
      const response = await fetch(`${base()}/download/${format}`);
      if (!response.ok) throw new Error(await response.text());
      const blob = await response.blob();
      const name = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "")?.[1] || `${format}.${format}`;
      const url = URL.createObjectURL(blob);
      const link = h("a", { href: url, download: name });
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      button.textContent = label;
    } catch (error) {
      // A 404 on the pptx means the review server predates its export: restart the MCP process.
      button.textContent = `${label} failed`;
      button.title = String(error.message || error);
      setTimeout(() => { button.textContent = label; button.title = title; }, 6000);
    } finally {
      button.disabled = false;
      button.classList.remove("busy");
    }
  }

  $("#download-pdf-btn").addEventListener("click", (event) => download(event.currentTarget, "pdf"));
  $("#download-pptx-btn").addEventListener("click", (event) => download(event.currentTarget, "pptx"));
}
