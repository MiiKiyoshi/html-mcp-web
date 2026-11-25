"""One headless Chrome for every step that has to see a document as a browser sets it: the
layout check, printing a PDF, exporting a pptx and setting a report's pages.

The browser is Google Chrome, else Chromium, else Microsoft Edge, which is built on Chromium
and comes with Windows. The layout check opens its page in the browser and the page posts
what it measured. Every other step drives the browser over its DevTools protocol, a WebSocket
on a port of the browser's own choosing, through aiohttp's client.

Callers surface the FileNotFoundError message instead of crashing."""
import asyncio
import base64
import contextlib
import ctypes
import functools
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path

import aiohttp
import psutil

# Each browser in the order it is looked for: its names on the PATH, and where its installer
# puts it on macOS and on Windows, folders the PATH does not name. A Windows place is a path
# under the folder for every user, the one for 32-bit programs, and the one for this user alone.
BROWSERS = [
    (["google-chrome", "google-chrome-stable", "chrome"],
     ["Google Chrome.app/Contents/MacOS/Google Chrome"],
     [r"Google\Chrome\Application\chrome.exe"]),
    (["chromium", "chromium-browser"],
     ["Chromium.app/Contents/MacOS/Chromium"],
     [r"Chromium\Application\chrome.exe"]),
    (["microsoft-edge", "microsoft-edge-stable", "msedge"],
     ["Microsoft Edge.app/Contents/MacOS/Microsoft Edge"],
     [r"Microsoft\Edge\Application\msedge.exe"]),
]
MISSING = "Chrome or Edge is not installed"
# A laptop's screen, on which the review page lays itself out as it does for most readers.
# A headless browser's own window is 800 by 600.
WINDOW = "1366,768"


def binary() -> str | None:
    """The browser to run, or None when none of them is installed."""
    for names, mac, windows in BROWSERS:
        for name in names:
            if (found := shutil.which(name)) is not None:
                return found
        if sys.platform == "darwin":
            places = [Path(folder, place) for place in mac for folder in ("/Applications", Path.home() / "Applications")]
        elif os.name == "nt":
            places = [Path(os.environ[variable], place) for place in windows
                      for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA") if os.environ.get(variable)]
        else:
            places = []
        if (found := next((str(place) for place in places if place.is_file()), None)) is not None:
            return found
    return None


def profile(prefix: str) -> str:
    """A new, empty folder for one browser's profile. Every browser gets one of its own: two
    on one profile hand their pages to the first, and a profile of a browser the user runs
    would get its windows."""
    return tempfile.mkdtemp(prefix=prefix)


def said(folder: str) -> Path:
    """The file in the profile that the browser's error output goes to, where it says on
    which port its DevTools protocol listens."""
    return Path(folder, "said.txt")


def command(folder: str, *arguments: str) -> list[str]:
    """The command that starts the browser headless on the profile in *folder*, with
    *arguments* after the ones every start takes."""
    program = binary()
    if program is None:
        raise FileNotFoundError(MISSING)
    return [
        program, "--headless=new", f"--user-data-dir={folder}", "--remote-debugging-port=0",
        "--no-first-run", f"--window-size={WINDOW}",
        # A new profile's first page waited 25 s on Linux for the desktop's keyring, which a
        # profile of its own does not need. macOS's keychain is left alone the same way.
        "--password-store=basic", "--use-mock-keychain",
        # A new profile downloads components and settings, which reach the network and left
        # 0.4 MB in the temporary folder for each browser.
        "--disable-component-update", "--disable-background-networking",
        # Scrollbars neither take width from a page nor show in a picture of it.
        "--hide-scrollbars",
        # A container's /dev/shm is too small for the pages of a long document.
        "--disable-dev-shm-usage",
        # Chrome refuses to run as root, as it is in a container, with its sandbox on.
        *(["--no-sandbox"] if hasattr(os, "geteuid") and os.geteuid() == 0 else []),
        *arguments,
    ]


def _endpoint(folder: str) -> str | None:
    """The browser's own DevTools address, once it has said it."""
    try:
        text = said(folder).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    found = re.search(r"DevTools listening on (ws://\S+)", text)
    return found.group(1) if found is not None else None


def close(folder: str) -> bool:
    """Ask the browser on the profile in *folder* to close, as its own Close does, and say
    whether it was asked. A browser that cannot be asked, one that has not said yet where it
    listens or no longer answers, is not."""
    endpoint = _endpoint(folder)
    if endpoint is None:
        return False

    async def asked() -> None:
        async with aiohttp.ClientSession() as session, session.ws_connect(endpoint) as socket:
            await socket.send_json({"id": 1, "method": "Browser.close"})
            await socket.receive()

    try:
        asyncio.run(asyncio.wait_for(asked(), 5))
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        return False
    return True


def _running(process: psutil.Process) -> bool:
    """Whether a process has not exited, without waiting for it, which is its parent's to do."""
    try:
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def end(pid: int, folder: str) -> None:
    """End the browser started as process *pid* on the profile in *folder*, and every process
    under it, so that its profile is no longer in use. It is asked to close, as its own Close
    does, and ended by a signal when it cannot be asked or has not exited within seconds:
    ended by a signal, it leaves a folder of its own in the temporary folder, outside its
    profile. One call does both, so a caller cancelled on the way leaves no browser running.
    The caller waits for its own process."""
    try:
        started = psutil.Process(pid)
    except psutil.Error:
        return
    # A browser that has just started is asked once it says where it listens, a moment later.
    # Ended before that, the processes it was still starting put its profile back once the
    # profile had been removed.
    deadline = time.monotonic() + 5
    while (said(folder).is_file() and _endpoint(folder) is None and _running(started)
           and time.monotonic() < deadline):
        time.sleep(0.05)
    try:
        below = started.children(recursive=True)
    except psutil.Error:
        below = []
    # The signal comes whatever the asking met.
    try:
        if close(folder):
            deadline = time.monotonic() + 5
            while _running(started) and time.monotonic() < deadline:
                time.sleep(0.05)
    finally:
        for process in (*below, started):
            if _running(process):
                with contextlib.suppress(psutil.Error):
                    process.terminate()
        for process in psutil.wait_procs(below, timeout=5)[1]:
            with contextlib.suppress(psutil.Error):
                process.kill()


if sys.platform.startswith("linux"):
    # Bound before any browser starts: the function below runs between fork and exec, where
    # nothing may be loaded or imported.
    _prctl = ctypes.CDLL(None, use_errno=True).prctl
    _PR_SET_PDEATHSIG, _SIGKILL = 1, int(signal.SIGKILL)

    def _tied(starter: int) -> None:
        """In the browser's process before it runs the browser: the kernel kills it once the
        thread that started it has exited, with its process or alone, and one whose starter
        died before this ran exits at once."""
        _prctl(_PR_SET_PDEATHSIG, _SIGKILL)
        if os.getppid() != starter:
            os._exit(1)

elif os.name == "nt":
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    _kernel32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _CREATE_SUSPENDED, _KILL_ON_JOB_CLOSE, _EXTENDED_LIMITS = 0x4, 0x2000, 9
    _PROCESS_SET_QUOTA, _PROCESS_TERMINATE = 0x100, 0x1

    class _BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _Limits(ctypes.Structure):
        # JOBOBJECT_EXTENDED_LIMIT_INFORMATION, its IO_COUNTERS six 64-bit counts.
        _fields_ = [("BasicLimitInformation", _BasicLimits), ("IoInfo", ctypes.c_uint64 * 6),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    def _checked(result):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())
        return result

    @functools.cache
    def _job() -> int:
        """The job every browser this process starts is put in, with the processes it starts.
        Only this process holds the job, and Windows ends what is in it once the job's last
        holder has gone, with this process however it ends."""
        job = _checked(_kernel32.CreateJobObjectW(None, None))
        limits = _Limits()
        limits.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
        _checked(_kernel32.SetInformationJobObject(job, _EXTENDED_LIMITS, ctypes.byref(limits),
                                                   ctypes.sizeof(limits)))
        return job

    def _join_job(pid: int) -> None:
        handle = _checked(_kernel32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid))
        try:
            _checked(_kernel32.AssignProcessToJobObject(_job(), handle))
        finally:
            _kernel32.CloseHandle(handle)


def start(folder: str, *arguments: str) -> subprocess.Popen:
    """Start the browser headless on the profile in *folder*, with *arguments* after the ones
    every start takes, and its error output in said(folder). Its callers end it with stop()
    and remove its profile, and a starter that ends without doing so takes the browser with it:
    on Linux the kernel kills the browser once the thread that started it exits, and on Windows
    the browser and every process it starts are in a job that ends with the starter. On macOS
    nothing ends it but its callers."""
    tie: dict = {}
    if sys.platform.startswith("linux"):
        tie["preexec_fn"] = functools.partial(_tied, os.getpid())
    elif os.name == "nt":
        # Put in the job before it runs, and so before it starts processes of its own.
        tie["creationflags"] = _CREATE_SUSPENDED
    with open(said(folder), "wb") as output:
        process = subprocess.Popen(command(folder, *arguments), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=output, env=headless_environment(), **tie)
    if os.name == "nt":
        try:
            _join_job(process.pid)
            psutil.Process(process.pid).resume()
        except BaseException:
            process.kill()
            process.wait()
            raise
    return process


def remove(folder: str) -> None:
    """Remove the profile in *folder* of a browser that has exited, and the folder of its own
    in the temporary folder that a browser ended by a signal leaves: its profile's
    SingletonSocket points into it."""
    with contextlib.suppress(OSError):
        own = Path(os.readlink(Path(folder, "SingletonSocket"))).parent
        if own.parent == Path(folder).parent:
            shutil.rmtree(own, ignore_errors=True)
    shutil.rmtree(folder, ignore_errors=True)


def stop(process: subprocess.Popen, folder: str) -> None:
    """End a browser this process started on the profile in *folder*, and wait until it has
    exited. One that has exited already is not looked for by its pid, which another process
    may have now."""
    if process.poll() is None:
        end(process.pid, folder)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def headless_environment() -> dict[str, str]:
    """The environment a headless browser is started in: this one without a display. Over
    ssh with X forwarding the display is the far machine's, and a browser given one connects
    to it."""
    return {name: value for name, value in os.environ.items() if name not in ("DISPLAY", "WAYLAND_DISPLAY")}


def listening(process: subprocess.Popen, folder: str, seconds: float = 60) -> int:
    """The port the DevTools protocol of the browser on the profile in *folder* listens on,
    once the browser has said it."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if (endpoint := _endpoint(folder)) is not None:
            return int(re.match(r"ws://[^/]*:(\d+)/", endpoint).group(1))
        if process.poll() is not None:
            text = said(folder).read_text(encoding="utf-8", errors="replace")
            raise RuntimeError(f"the browser exited as it started: {text[-2000:]}")
        time.sleep(0.05)
    raise TimeoutError("the browser did not start")


class Page:
    """The page of a browser, driven over its DevTools protocol. Each call waits for its
    answer. A step runs on a thread of its own, and its WebSocket on an event loop of its own
    on that thread."""

    def __init__(self, port: int):
        self.loop = asyncio.new_event_loop()
        self.calls = 0
        try:
            self.loop.run_until_complete(self._connect(port))
        except BaseException:
            self.loop.close()
            raise
        self.call("Page.enable")

    async def _connect(self, port: int) -> None:
        self.session = aiohttp.ClientSession()
        # The page the browser opened is listed a moment after the protocol is.
        for _ in range(100):
            async with self.session.get(f"http://127.0.0.1:{port}/json/list") as response:
                page = next((target for target in await response.json() if target["type"] == "page"), None)
            if page is not None:
                break
            await asyncio.sleep(0.05)
        else:
            await self.session.close()
            raise TimeoutError("the browser opened no page")
        # A PDF or a picture of a page comes back as one message of many megabytes.
        self.socket = await self.session.ws_connect(page["webSocketDebuggerUrl"], max_msg_size=0)

    async def _call(self, method: str, params: dict, until: str | None) -> dict:
        self.calls += 1
        await self.socket.send_json({"id": self.calls, "method": method, "params": params})
        answer, seen = None, until is None
        while answer is None or not seen:
            message = await self.socket.receive_json(timeout=120)
            if message.get("id") == self.calls:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error'].get('message')}")
                answer = message["result"]
            elif message.get("method") == until:
                seen = True
        return answer

    def call(self, method: str, until: str | None = None, **params) -> dict:
        """Send *method* with *params* and give its answer, once the event *until* has come
        too when it is named."""
        return self.loop.run_until_complete(self._call(method, params, until))

    def navigate(self, url: str) -> None:
        """Open *url* and wait until its document and what it loads have loaded."""
        answer = self.call("Page.navigate", until="Page.loadEventFired", url=url)
        if answer.get("errorText"):
            raise RuntimeError(f"{url} did not open: {answer['errorText']}")

    def execute_script(self, script: str, args: Sequence = ()):
        """Run *script* in the page as the body of a function whose arguments are *args*,
        and give what it returns, a promise's value once it settles, as JSON gives it."""
        answer = self.call("Runtime.evaluate", returnByValue=True, awaitPromise=True,
                           expression=f"(function () {{\n{script}\n}}).apply(null, {json.dumps(list(args))})")
        if "exceptionDetails" in answer:
            details = answer["exceptionDetails"]
            raise RuntimeError(details.get("exception", {}).get("description") or details.get("text"))
        return answer["result"].get("value")

    def print_pdf(self, width: float, height: float) -> bytes:
        """The document printed on sheets *width* by *height* inches, without margins, with
        its backgrounds."""
        answer = self.call("Page.printToPDF", printBackground=True, scale=1, paperWidth=width,
                           paperHeight=height, marginTop=0, marginBottom=0, marginLeft=0, marginRight=0)
        return base64.b64decode(answer["data"])

    def screenshot(self, box: Sequence[float]) -> bytes:
        """A PNG of the part of the document *box* gives, as x, y, width and height in the
        document's CSS pixels, at the browser's pixel ratio."""
        x, y, width, height = box
        answer = self.call("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                           clip={"x": x, "y": y, "width": width, "height": height, "scale": 1})
        return base64.b64decode(answer["data"])

    def close(self) -> None:
        async def closed() -> None:
            await self.socket.close()
            await self.session.close()

        try:
            self.loop.run_until_complete(closed())
        finally:
            self.loop.close()


@contextmanager
def chrome(*arguments: str):
    """A page on a headless browser of its own, started with *arguments* as well."""
    folder = profile("html_mcp_chrome_")
    process = start(folder, *arguments, "about:blank")
    try:
        page = Page(listening(process, folder))
        try:
            yield page
        finally:
            page.close()
    finally:
        # Removed under a running browser, the profile came back in part, and on Windows a
        # file a running browser holds is not removed at all.
        stop(process, folder)
        remove(folder)


def wait_loaded(page: Page, condition: str = "true", tries: int = 50) -> None:
    """Wait for the document, its images and its fonts, and then for condition, a
    JavaScript expression."""
    for _ in range(tries):
        if page.execute_script(
                "return document.readyState === 'complete' && "
                "Array.from(document.images).every(im => im.complete) && "
                f"document.fonts.status === 'loaded' && ({condition})"):
            return
        time.sleep(0.2)
    raise TimeoutError(f"the document did not finish loading: {condition}")
