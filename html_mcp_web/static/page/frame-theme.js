// The theme the review page shows, told to each frame's document, the artifact's and the slide
// previews', which draw their ground by it: as each document loads (attachFrameTheme), and to all
// of them when the theme changes (markFrameThemes). A frame from elsewhere keeps its own look.

function markFrameTheme(frame) {
  try {
    const root = frame.contentDocument?.documentElement;
    if (root) root.dataset.htmlMcpTheme = document.documentElement.dataset.theme;
  } catch {
    // A frame from elsewhere keeps its own look.
  }
}

export function markFrameThemes() {
  for (const frame of document.querySelectorAll("iframe")) markFrameTheme(frame);
}

export function attachFrameTheme() {
  // A load does not bubble, but it is seen on the way down.
  document.addEventListener("load", (event) => {
    if (event.target instanceof HTMLIFrameElement) markFrameTheme(event.target);
  }, true);
}
