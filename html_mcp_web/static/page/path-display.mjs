// The file's own name, after the last slash or, in a path written on Windows, backslash: cut
// at slashes alone, a Windows path showed whole where its name belonged.
export function fileName(path) {
  return path.split(/[\\/]/).pop();
}

export function displayPath(path, home) {
  if (typeof path !== "string" || typeof home !== "string" || home === "") return path;
  if (path === home) return "~";
  // Below the home folder, after a slash or, on Windows, a backslash.
  const folder = home.replace(/[\\/]+$/, "");
  const rest = path.slice(folder.length);
  return path.startsWith(folder) && /^[\\/]/.test(rest) ? `~${rest}` : path;
}
