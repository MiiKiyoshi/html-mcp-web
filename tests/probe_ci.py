"""What a CI runner's Firefox does, printed for the log: the fonts it sets each generic family
in, and how a page fares in a Firefox started the way the server's layout check starts one,
with a new profile and no marionette. A diagnosis for the runners, run by hand in CI."""

import http.server
import json
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlparse

from html_mcp_web import firefox

FAMILIES = ["serif", "sans-serif", "monospace", "system-ui", "-apple-system", "ui-monospace"]
NAMED = ["Noto Serif", "Noto Sans", "DejaVu Sans Mono", "Noto Sans Mono", "DejaVu Serif", "DejaVu Sans",
         "Liberation Serif", "Liberation Sans", "Times New Roman", "Times", "Arial", "Helvetica", "Segoe UI",
         "Consolas", "Cascadia Mono", "Menlo", "SF Mono", ".AppleSystemUIFont", "Courier New"]

PAGE = """<!doctype html><meta charset="utf-8"><title>probe</title><body><p>probe</p><script>
const sample = "Optimization History is the first line here and only the tail \\u222b";
const c = document.createElement("canvas").getContext("2d");
const width = (family) => { c.font = "16px " + family; return c.measureText(sample).width.toFixed(3); };
const fonts = {};
for (const family of FAMILIES.concat(NAMED.map((name) => `"${name}"`))) fonts[family] = width(family);
let frames = 0;
const tick = () => { frames += 1; requestAnimationFrame(tick); };
requestAnimationFrame(tick);
const started = performance.now();
const beat = () => fetch(`/beat?ms=${Math.round(performance.now() - started)}&frames=${frames}`
  + `&visible=${document.visibilityState}&focus=${document.hasFocus()}`
  + `&fonts=${encodeURIComponent(JSON.stringify(fonts))}`);
beat();
setInterval(beat, 500);
</script>""".replace("FAMILIES", json.dumps(FAMILIES)).replace("NAMED", json.dumps(NAMED))


def run_once(label: str, seconds: float) -> None:
    beats: list[dict] = []
    first: list[float] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/beat":
                if not first:
                    first.append(time.monotonic())
                beats.append({key: values[0] for key, values in parse_qs(url.query).items()})
                body = b"ok"
            else:
                body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    profile = tempfile.mkdtemp(prefix="html_mcp_probe_")
    started = time.monotonic()
    process = subprocess.Popen(
        firefox.command("-headless", "-no-remote", "-profile", profile, f"http://127.0.0.1:{server.server_port}/"),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=firefox.headless_environment())
    time.sleep(seconds)
    firefox.stop(process)
    server.shutdown()
    shutil.rmtree(profile, ignore_errors=True)
    print(f"[{label}] first beat after {first[0] - started:.1f} s" if first else f"[{label}] no beat in {seconds} s")
    states = [(beat.get("ms"), beat.get("frames"), beat.get("visible"), beat.get("focus")) for beat in beats]
    print(f"[{label}] beats (ms, frames, visibility, focus): {states[:3]} ... {states[-3:]}")
    if beats:
        fonts = json.loads(beats[0]["fonts"])
        by_width: dict[str, list[str]] = {}
        for name in NAMED:
            by_width.setdefault(fonts[f'"{name}"'], []).append(name)
        for family in FAMILIES:
            print(f"[{label}] {family}: {fonts[family]} = {by_width.get(fonts[family], ['?'])}")


def check_once(label: str) -> None:
    """The server's own layout check of the browser tests' deck, timed, with the console of the
    Firefox it starts."""
    import asyncio
    import socket
    from pathlib import Path

    import yaml

    from html_mcp_web.config import load_config
    from html_mcp_web.project_server import SharedProjectServer
    from tests.test_browser import slides_html

    folder = Path(tempfile.mkdtemp(prefix="html_mcp_probe_project_"))
    (folder / "slides.html").write_text(slides_html(), encoding="utf-8")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    (folder / ".html-mcp-web.yaml").write_text(yaml.safe_dump({
        "artifacts": {"slides": {"layout": "slides", "main": "slides.html"}}, "port": port}), encoding="utf-8")
    console = folder / "check-console.log"
    real = asyncio.create_subprocess_exec

    async def logged(*args, **kwargs):
        profile = args[list(args).index("-profile") + 1]
        Path(profile, "user.js").write_text('user_pref("devtools.console.stdout.content", true);\n', encoding="utf-8")
        out = open(console, "ab")
        kwargs["stdout"] = kwargs["stderr"] = out
        return await real(*args, **kwargs)

    asyncio.create_subprocess_exec = logged
    shared = SharedProjectServer(load_config(folder / ".html-mcp-web.yaml"))
    try:
        shared.ensure()
        started = time.monotonic()
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/artifacts/slides/layout", timeout=90) as response:
            data = json.loads(response.read())
        print(f"[{label}] check answered after {time.monotonic() - started:.1f} s: errors {data.get('errors')}, "
              f"unchecked {data.get('unchecked')}")
    except Exception as error:
        print(f"[{label}] check failed: {error!r}")
    finally:
        shared.stop()
        asyncio.create_subprocess_exec = real
    said = console.read_text(encoding="utf-8", errors="replace").splitlines() if console.exists() else []
    print(f"[{label}] check console, {len(said)} lines:")
    for line in said[-40:]:
        print(f"[{label}]   {line[:300]}")


def checks_at_once(label: str, count: int, prefs: str = "") -> None:
    """*count* servers each running its own layout check at the same time, as the test workers
    do, timed, with how busy the processors were, the check profiles given *prefs*. The console
    of each checking Firefox is printed for the first check that went unanswered."""
    import asyncio
    import socket
    import urllib.request
    from pathlib import Path

    import psutil
    import yaml

    from html_mcp_web.config import load_config
    from html_mcp_web.project_server import SharedProjectServer
    from tests.test_browser import slides_html

    times: list[str] = []
    consoles: dict[int, Path] = {}
    real = asyncio.create_subprocess_exec

    async def logged(*args, **kwargs):
        profile = args[list(args).index("-profile") + 1]
        Path(profile, "user.js").write_text('user_pref("devtools.console.stdout.content", true);\n' + prefs,
                                            encoding="utf-8")
        port = int(args[-1].split("//", 1)[1].split("/", 1)[0].rsplit(":", 1)[1])
        out = open(consoles.setdefault(port, Path(tempfile.mkdtemp()) / "console.log"), "ab")
        kwargs["stdout"] = kwargs["stderr"] = out
        return await real(*args, **kwargs)

    def one() -> None:
        folder = Path(tempfile.mkdtemp(prefix="html_mcp_probe_project_"))
        (folder / "slides.html").write_text(slides_html(), encoding="utf-8")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        (folder / ".html-mcp-web.yaml").write_text(yaml.safe_dump({
            "artifacts": {"slides": {"layout": "slides", "main": "slides.html"}}, "port": port}), encoding="utf-8")
        shared = SharedProjectServer(load_config(folder / ".html-mcp-web.yaml"))
        try:
            shared.ensure()
            started = time.monotonic()
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/artifacts/slides/layout", timeout=90) as response:
                data = json.loads(response.read())
            answered = data.get("errors") is not None
            times.append(f"{time.monotonic() - started:.1f}s{'' if answered else ' unchecked'}")
            if not answered:
                unanswered.append(port)
        except Exception as error:
            times.append(repr(error)[:80])
        finally:
            shared.stop()

    unanswered: list[int] = []
    asyncio.create_subprocess_exec = logged
    psutil.cpu_percent()
    threads = [threading.Thread(target=one) for _ in range(count)]
    for thread in threads:
        thread.start()
    busy = []
    while any(thread.is_alive() for thread in threads):
        time.sleep(1)
        busy.append(round(psutil.cpu_percent()))
    asyncio.create_subprocess_exec = real
    print(f"[{label}] {count} checks at once answered after {times}, processors busy {busy[:12]}... %")
    if unanswered and unanswered[0] in consoles:
        for line in consoles[unanswered[0]].read_text(encoding="utf-8", errors="replace").splitlines()[-25:]:
            print(f"[{label}]   {line[:300]}")


def browsers_at_once(label: str, count: int) -> None:
    """*count* Firefoxes started at once as the check starts one, each on a page of its own."""
    threads = [threading.Thread(target=run_once, args=(f"{label} {index}", 20)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


if __name__ == "__main__":
    import sys

    run_once("first", 20)
    check_once("check 1")
    checks_at_once("load", 4)
    if sys.platform == "win32":
        browsers_at_once("browsers", 4)
        checks_at_once("load, no default browser check", 4, 'user_pref("browser.shell.checkDefaultBrowser", false);\n')
        checks_at_once("load, first run settled", 4, "".join(f"user_pref({name!r}, {value});\n".replace("'", '"') for name, value in (
            ("browser.shell.checkDefaultBrowser", "false"),
            ("browser.startup.homepage_override.mstone", "'ignore'"),
            ("startup.homepage_welcome_url", "''"),
            ("browser.aboutwelcome.enabled", "false"),
            ("datareporting.policy.dataSubmissionPolicyBypassNotification", "true"),
            ("toolkit.telemetry.reportingpolicy.firstRun", "false"),
            ("app.update.disabledForTesting", "true"),
        )))
