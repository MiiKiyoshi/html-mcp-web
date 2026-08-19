# Neutral report template

An organization-neutral A4 report: a cover followed by one page per section, built from
the shared content format described in [`../README.md`](../README.md).

```bash
python3 build.py <content.html> <report.html>
```

Components specific to the report: `h3` subsection headings, `div.callout` for a
finding that needs attention, `div.metrics` containing `div.metric`, and `figure` with
`figcaption`. Prose, notes, tables, `div.two`, and `code` behave as on slides.

Each content page carries `data-layout-guard`, so overflow is reported the same way.
