"""Print the reviewed artifact to a single PDF with firefox marionette.

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
