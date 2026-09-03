"""Print the reviewed artifact to a single PDF with firefox marionette.

The artifact URL already carries the print CSS (artifact.css @media print
places each section.page on its own fixed-size sheet), so WebDriver:Print
with the layout's page size yields the artifact exactly as the Print button would
in a browser that honors @page size.

Requires firefox and the marionette_driver package; callers surface the
ImportError/FileNotFoundError message to the user instead of crashing.
"""
import base64
import shutil
import subprocess
import tempfile
import time

PRINT_PAGE_CM = {
    "slides": (33.867, 19.05),
    "report": (21.0, 29.7),
}


def print_artifact_pdf(artifact_url: str, layout: str) -> bytes:
    """Callers must not run two of these at once: they share the default marionette port 2828."""
    from marionette_driver.marionette import Marionette

    if shutil.which("firefox") is None:
        raise FileNotFoundError("firefox is not installed")
    width_cm, height_cm = PRINT_PAGE_CM[layout]
    profile = tempfile.mkdtemp(prefix="html_mcp_pdf_")
    proc = subprocess.Popen(
        ["firefox", "-marionette", "-headless", "-no-remote", "-profile", profile, "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        client = Marionette(host="127.0.0.1", port=2828, startup_timeout=60)
        client.start_session()
        client.navigate(artifact_url)
        for _ in range(50):
            done = client.execute_script(
                "return document.readyState === 'complete' && "
                "Array.from(document.images).every(im => im.complete) && "
                "document.fonts.status === 'loaded'")
            if done:
                break
            time.sleep(0.2)
        body = {
            "background": True, "shrinkToFit": False, "scale": 1.0,
            "margin": {"top": 0, "bottom": 0, "left": 0, "right": 0},
            "page": {"width": width_cm, "height": height_cm},
        }
        pdf = client._send_message("WebDriver:Print", body, key="value")
        client.delete_session()
        return base64.b64decode(pdf)
    finally:
        proc.terminate()
        shutil.rmtree(profile, ignore_errors=True)
