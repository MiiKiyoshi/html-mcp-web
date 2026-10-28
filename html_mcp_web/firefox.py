"""One headless Firefox under marionette, for every step that has to see a document as
the browser sets it: printing a PDF and setting a report's pages.

Requires firefox and the marionette_driver package. Callers surface the ImportError or
FileNotFoundError message instead of crashing."""
import shutil
import socket
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def firefox():
    """A marionette client with a session open, on a Firefox of its own."""
    from marionette_driver.marionette import Marionette

    if shutil.which("firefox") is None:
        raise FileNotFoundError("firefox is not installed")
    # A port of its own for this firefox. Every project runs a server of its own, and on the
    # default port an export attached to whatever browser already held it: another
    # project's export, which failed this one with "No data received over socket" or gave
    # it a page of the other project's deck.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        marionette_port = int(probe.getsockname()[1])
    profile = tempfile.mkdtemp(prefix="html_mcp_firefox_")
    # Accessibility off: on a host where firefox turned it on, about half the prints of one
    # deck failed at once with NS_ERROR_UNEXPECTED, each after the accessibility IPC error
    # "PDocAccessibleConstructor ... handler returned false", and none failed without it.
    Path(profile, "user.js").write_text(
        f'user_pref("marionette.port", {marionette_port});\n'
        'user_pref("accessibility.force_disabled", 1);\n', encoding="utf-8")
    proc = subprocess.Popen(
        ["firefox", "-marionette", "-headless", "-no-remote", "-profile", profile, "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        client = Marionette(host="127.0.0.1", port=marionette_port, startup_timeout=60)
        client.start_session()
        yield client
        client.delete_session()
    finally:
        proc.terminate()
        shutil.rmtree(profile, ignore_errors=True)


def wait_loaded(client, condition: str = "true", tries: int = 50) -> None:
    """Wait for the document, its images and its fonts, and then for condition, a
    JavaScript expression."""
    for _ in range(tries):
        if client.execute_script(
                "return document.readyState === 'complete' && "
                "Array.from(document.images).every(im => im.complete) && "
                f"document.fonts.status === 'loaded' && ({condition})"):
            return
        time.sleep(0.2)
    raise TimeoutError(f"the document did not finish loading: {condition}")
