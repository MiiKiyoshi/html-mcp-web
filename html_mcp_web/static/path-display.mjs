export function displayPath(path, home) {
  if (typeof path !== "string" || typeof home !== "string" || home === "") return path;
  if (path === home) return "~";
  // Below the home folder, after a slash or, on Windows, a backslash.
  const folder = home.replace(/[\\/]+$/, "");
  const rest = path.slice(folder.length);
  return path.startsWith(folder) && /^[\\/]/.test(rest) ? `~${rest}` : path;
}
