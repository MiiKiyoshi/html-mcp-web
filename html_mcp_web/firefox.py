"""One headless Firefox under marionette, for every step that has to see a document as
the browser sets it: printing a PDF and setting a report's pages.

Requires firefox and the marionette_driver package. Callers surface the ImportError or
FileNotFoundError message instead of crashing."""
import contextlib
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import psutil


def binary() -> str | None:
    """The Firefox to run: the one on the PATH, or else the one where its installer puts it,
    which on macOS and Windows is a folder the PATH does not name."""
    found = shutil.which("firefox")
    if found is not None:
        return found
    if sys.platform == "darwin":
        places = [Path(folder, "Firefox.app", "Contents", "MacOS", "firefox")
                  for folder in ("/Applications", Path.home() / "Applications")]
    elif os.name == "nt":
        # For every user, as a 32-bit program, and for this user alone.
        places = [Path(os.environ[name], "Mozilla Firefox", "firefox.exe")
                  for name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA") if os.environ.get(name)]
    else:
        places = []
    return next((str(place) for place in places if place.is_file()), None)


def command(*arguments: str) -> list[str]:
    """The command that starts Firefox with *arguments*. On Windows Firefox can start as a
    launcher that hands the browser to a process of its own and ends; told to wait for the
    browser, it stays the browser's parent, so end() finds the browser under it."""
    program = binary()
    if program is None:
        raise FileNotFoundError("firefox is not installed")
    return [program, *(["-wait-for-browser"] if os.name == "nt" else []), *arguments]


def end(pid: int) -> None:
    """End the Firefox started as process *pid* and every process under it, and wait for
    those under it, so that its profile is no longer in use. The caller waits for its own
    process."""
    try:
        started = psutil.Process(pid)
        below = started.children(recursive=True)
    except psutil.Error:
        return
    for process in (*below, started):
        with contextlib.suppress(psutil.Error):
            process.terminate()
    for process in psutil.wait_procs(below, timeout=5)[1]:
        with contextlib.suppress(psutil.Error):
            process.kill()


def stop(process: subprocess.Popen) -> None:
    """End a Firefox this process started, and wait until it has exited. One that has exited
    already is not looked for by its pid, which another process may have now."""
    if process.poll() is None:
        end(process.pid)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def headless_environment() -> dict[str, str]:
    """The environment a headless Firefox is started in: this one without a display. A
    headless Firefox still connects to the display it is given, and over ssh with X
    forwarding that display is the far machine's, which prints a refusal for each try."""
    return {name: value for name, value in os.environ.items() if name not in ("DISPLAY", "WAYLAND_DISPLAY")}


@contextmanager
def firefox():
    """A marionette client with a session open, on a Firefox of its own."""
    from marionette_driver.marionette import Marionette

    browser = command("-marionette", "-headless", "-no-remote", "-profile")
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
        [*browser, profile, "about:blank"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=headless_environment(),
    )
    try:
        client = Marionette(host="127.0.0.1", port=marionette_port, startup_timeout=60)
        client.start_session()
        yield client
        client.delete_session()
    finally:
        # Removed under a running browser, the profile came back in part, and on Windows a
        # file a running browser holds is not removed at all.
        stop(proc)
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
