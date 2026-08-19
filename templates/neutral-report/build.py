#!/usr/bin/env python3
"""Compile content.html into a self-contained neutral A4 report.

Usage: python3 build.py <content.html> <report.html>
"""

import sys
from pathlib import Path

from html_mcp_web.template_content import parse_template_content


HERE = Path(__file__).parent


def build(content_path: Path, output_path: Path) -> None:
    content = parse_template_content(content_path)

    css = (HERE / "template.css").read_text(encoding="utf-8")
    metadata_html = "<br>\n        ".join(content.metadata)
    page_count = len(content.sections) + 1
    pages = [f'''    <section class="page cover">
      <div class="cover-rule"></div>
      <div class="cover-content">
        <p class="document-type">TECHNICAL REPORT</p>
        <h1>{content.title}</h1>
        {f'<p class="cover-sub">{content.subtitle}</p>' if content.subtitle else ''}
        <div class="cover-meta">
          <p class="author">{content.author}</p>
          <p>{metadata_html}</p>
        </div>
      </div>
      <footer><span>1 / {page_count}</span></footer>
    </section>''']

    for page_number, section in enumerate(content.sections, 2):
        pages.append(f'''    <section class="page">
      <header class="page-header">
        <span class="report-title">{content.title}</span>
        <h2>{section.title}</h2>
      </header>
      <div class="report-body" data-layout-guard>
{section.body_html}
      </div>
      <footer><span>{page_number} / {page_count}</span></footer>
    </section>''')

    output_path.write_text(f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{content.title}</title>
  <style>
{css}
  </style>
</head>
<body>
  <main class="pages">

{chr(10).join(pages)}

  </main>
</body>
</html>
''', encoding="utf-8")
    print(f"{output_path}: cover + {len(content.sections)} report pages")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    build(Path(sys.argv[1]), Path(sys.argv[2]))
