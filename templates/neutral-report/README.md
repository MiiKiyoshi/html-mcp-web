# Neutral report template

A two-column paper on A4, set like a conference proceedings paper: the title block across
the top of the first page, then numbered sections whose text runs on from column to
column and page to page. It is built from the shared content format described in
[`../README.md`](../README.md), and what only a report has is in Article 10 of
[`../KITS.md`](../KITS.md).

```bash
python3 build.py <content.html> <report.html>
```

The builder writes the text as one flow, and a script in the document pours it into the
columns when the page opens, because only the browser can measure the lines. Each column
carries `data-layout-guard`, so a block taller than a column is reported by the layout
check.

The faces in `fonts/` are Libertinus Serif and Sans, subset to Latin, Greek and the
common symbols, under the SIL Open Font License in `fonts/LICENSE`. Hangul is not in them
and is set in the reader's Korean serif.
