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


if __name__ == "__main__":
    run_once("first", 25)
    run_once("second", 20)
