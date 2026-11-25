// The ⋯ menu of the top bar, and Settings, which the bar and the menu both open. A choice in the
// menu closes it, but for an export, which shows its progress there. attachMenu({ openSettings })
// wires them.

import { $ } from "../shared/dom.js";

export function attachMenu({ openSettings }) {
  const closeMore = () => {
    $("#more-menu").hidden = true;
    $("#more-btn").setAttribute("aria-expanded", "false");
  };
  $("#more-btn").addEventListener("click", (event) => {
    event.stopPropagation();
    const open = $("#more-menu").hidden;
    $("#more-menu").hidden = !open;
    $("#more-btn").setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".more")
      || event.target.closest(".more-menu button:not(.download-btn)")) closeMore();
  });
  $("#settings-btn").addEventListener("click", () => openSettings());
  $("#settings-menu-btn").addEventListener("click", () => openSettings());
}
