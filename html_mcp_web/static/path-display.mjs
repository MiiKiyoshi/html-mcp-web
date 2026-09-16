export function displayPath(path, home) {
  if (typeof path !== "string" || typeof home !== "string" || home === "") return path;
  if (path === home) return "~";
  const prefix = home === "/" ? "/" : `${home}/`;
  return path.startsWith(prefix) ? `~/${path.slice(prefix.length)}` : path;
}
