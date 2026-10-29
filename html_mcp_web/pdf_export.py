"""Print the reviewed artifact, or one figure of a report, to a PDF with firefox marionette.

The artifact URL already carries the print CSS (artifact.css @media print
places each section.page on its own fixed-size sheet), so WebDriver:Print
with the layout's page size yields the artifact exactly as the Print button would
in a browser that honors @page size.

Requires firefox and the marionette_driver package; callers surface the
ImportError/FileNotFoundError message to the user instead of crashing.
"""
import base64

from .firefox import firefox, wait_loaded

PRINT_PAGE_CM = {
    "slides": (33.867, 19.05),
    "report": (21.0, 29.7),
}


def print_artifact_pdf(artifact_url: str, layout: str) -> bytes:
    width_cm, height_cm = PRINT_PAGE_CM[layout]
    with firefox() as client:
        client.navigate(artifact_url)
        # A font that never arrives does not stop the print: it is the page as far as it got.
        try:
            wait_loaded(client)
        except TimeoutError:
            pass
        body = {
            "background": True, "shrinkToFit": False, "scale": 1.0,
            "margin": {"top": 0, "bottom": 0, "left": 0, "right": 0},
            "page": {"width": width_cm, "height": height_cm},
        }
        return base64.b64decode(client._send_message("WebDriver:Print", body, key="value"))


# The drawing of report figure N, alone in the document: the figure whose caption reads
# "Figure N:", its svg with the HTML lifted over it and without the caption. The rest of
# the body is removed rather than hidden, since Firefox prints hidden text into the PDF
# as text a reader can select and extract. The head stays, so the faces and the kit's
# styles stay. The drawing keeps the size and the inherited text style it was set at, and
# the sheet is its svg's box. Returns the sheet's width and height in CSS pixels, or why
# there is none.
ISOLATE_FIGURE = """
const label = `Figure ${arguments[0]}:`;
const figure = [...document.querySelectorAll('figure')]
  .find((candidate) => candidate.querySelector('.caption-label')?.textContent.trim() === label);
if (!figure) return `no figure is captioned "${label}"`;
const drawing = figure.querySelector(':scope .svg-html') ?? figure.querySelector(':scope svg');
if (!drawing) return `${label} holds no svg`;
// The sheet is the svg's box. The HTML lifted over it stays where it was on the drawing,
// whose own box may be wider: a figure's column.
const svg = drawing.matches('svg') ? drawing : drawing.querySelector(':scope > svg');
const outer = drawing.getBoundingClientRect(), inner = svg.getBoundingClientRect();
const scale = outer.width / parseFloat(getComputedStyle(drawing).width);
const width = inner.width / scale, height = inner.height / scale;
const holder = document.createElement('div');
for (const name of ['font-family', 'font-size', 'font-weight', 'font-style', 'line-height', 'color',
                    'letter-spacing', 'word-spacing', 'font-variant-numeric', 'font-variant-ligatures'])
  holder.style.setProperty(name, getComputedStyle(drawing.parentElement).getPropertyValue(name));
holder.lang = drawing.closest('[lang]')?.lang ?? document.documentElement.lang;
holder.style.width = `${width}px`;
holder.style.height = `${height}px`;
holder.style.overflow = 'hidden';
drawing.style.width = `${outer.width / scale}px`;
drawing.style.height = `${outer.height / scale}px`;
drawing.style.margin = `${(outer.top - inner.top) / scale}px 0 0 ${(outer.left - inner.left) / scale}px`;
holder.append(drawing);
document.body.replaceChildren(holder);
const sheet = document.createElement('style');
sheet.textContent = `@page { size: ${width}px ${height}px; margin: 0 }
html, body { margin: 0; padding: 0; width: ${width}px; height: ${height}px; overflow: hidden; background: #fff; }`;
document.head.append(sheet);
return [width, height];
"""


def print_figure_pdf(artifact_url: str, number: int) -> bytes:
    """Report figure number's drawing as a PDF of one sheet its own size, its text vector
    text in the document's embedded faces."""
    with firefox() as client:
        client.navigate(artifact_url)
        try:
            wait_loaded(client)
        except TimeoutError:
            pass
        size = client.execute_script(ISOLATE_FIGURE, script_args=[number])
        if isinstance(size, str):
            raise ValueError(size)
        width_cm, height_cm = (value * 2.54 / 96 for value in size)
        body = {
            "background": True, "shrinkToFit": False, "scale": 1.0,
            "margin": {"top": 0, "bottom": 0, "left": 0, "right": 0},
            "page": {"width": width_cm, "height": height_cm},
        }
        return base64.b64decode(client._send_message("WebDriver:Print", body, key="value"))
