// The review page's own calls to its server. fetchJson(path, options) gives the JSON the server
// answers, or null for an answer with no body, and throws what the server said when it refuses:
// its words as it sent them, or the status when it sent none (refusalText).

export async function refusalText(response) {
  const text = await response.text();
  return text || `${response.status} ${response.statusText}`;
}

export async function fetchJson(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(await refusalText(response));
  return response.status === 204 ? null : response.json();
}
