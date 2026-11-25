// The comments' marks in the source editor: the words an open comment on the source is on, and
// the text an open suggestion would replace, whatever its comment points at, each with a mark
// beside its first line. This module keeps the marks and which comments each one stands for.
//
// createSourceMarks() gives sync(editor, file, comments), the marks of `comments` drawn in the
// editor showing `file`, or none when `file` is null; clear(editor); commentAt(row, column), the
// comment the cursor is on, the narrowest when several cover it, else one on its line, or
// undefined; and commentsOn(row), the comments marked beside a line.

export function createSourceMarks() {
  let markers = [];
  // Each comment's marked text in the editor, as { range, comment }.
  let spans = [];
  const rows = new Set();
  const byRow = new Map();

  function clear(editor) {
    for (const marker of markers) editor.session.removeMarker(marker);
    for (const row of rows) {
      editor.session.removeGutterDecoration(row, "source-comment-line");
      editor.session.removeGutterDecoration(row, "source-suggestion-line");
    }
    markers = [];
    spans = [];
    rows.clear();
    byRow.clear();
  }

  function sync(editor, file, comments) {
    clear(editor);
    if (file === null) return;
    const Range = window.ace.require("ace/range").Range;
    for (const comment of comments) {
      const anchor = comment.anchor;
      if (comment.status !== "open" || anchor.kind !== "source" || anchor.file !== file || anchor.stale) continue;
      const firstRow = anchor.line_start - 1;
      const lastRow = anchor.line_end - 1;
      markers.push(editor.session.addMarker(
        new Range(firstRow, anchor.column_start, lastRow, anchor.column_end),
        "source-comment-highlight",
        "text",
        false,
      ));
      spans.push({ range: new Range(firstRow, anchor.column_start, lastRow, anchor.column_end), comment });
      editor.session.addGutterDecoration(firstRow, "source-comment-line");
      rows.add(firstRow);
      const onRow = byRow.get(firstRow) ?? [];
      onRow.push(comment);
      byRow.set(firstRow, onRow);
    }
    // The text an open proposal would replace, whatever its comment points at: a comment on the
    // rendered page proposes in the source too, and the editor marks the same text the card's −
    // line shows. The server found each piece once in the file, so a piece an edit has since moved
    // or duplicated is left unmarked rather than marked wrongly.
    const text = editor.session.getValue();
    for (const comment of comments) {
      const suggestion = comment.suggestion;
      if (comment.status !== "open" || suggestion === undefined || suggestion.file !== file) continue;
      for (const change of suggestion.changes) {
        const at = text.indexOf(change.old);
        if (at < 0 || text.indexOf(change.old, at + 1) >= 0) continue;
        const start = editor.session.doc.indexToPosition(at);
        const end = editor.session.doc.indexToPosition(at + change.old.length);
        markers.push(editor.session.addMarker(
          new Range(start.row, start.column, end.row, end.column),
          "source-suggestion-highlight",
          "text",
          false,
        ));
        spans.push({ range: new Range(start.row, start.column, end.row, end.column), comment });
        editor.session.addGutterDecoration(start.row, "source-comment-line");
        editor.session.addGutterDecoration(start.row, "source-suggestion-line");
        rows.add(start.row);
        const onRow = byRow.get(start.row) ?? [];
        if (!onRow.includes(comment)) onRow.push(comment);
        byRow.set(start.row, onRow);
      }
    }
  }

  return {
    sync,
    clear,
    commentAt(row, column) {
      const size = ({ range }) => (range.end.row - range.start.row) * 1e6 + range.end.column - range.start.column;
      const covering = spans.filter(({ range }) => range.contains(row, column)).sort((a, b) => size(a) - size(b));
      return covering[0]?.comment ?? byRow.get(row)?.[0];
    },
    commentsOn: (row) => byRow.get(row) ?? [],
  };
}
