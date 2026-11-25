import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for the UI helper test")
def test_home_path_display_boundaries() -> None:
    module = (Path(__file__).parent.parent / "html_mcp_web" / "static" / "path-display.mjs").as_uri()
    script = f"""
      import {{ displayPath, fileName }} from {json.dumps(module)};
      const home = "/home/alice";
      console.log(JSON.stringify([
        displayPath(home, home),
        displayPath(`${{home}}/paper/artifact.html`, home),
        displayPath(`${{home}}2/paper/artifact.html`, home),
        displayPath("/srv/paper/artifact.html", home),
        displayPath("/srv/home-link/artifact.html", home),
        displayPath("relative/artifact.html", home),
        displayPath("C:\\\\Users\\\\alice\\\\paper\\\\artifact.html", "C:\\\\Users\\\\alice"),
        displayPath("C:\\\\Users\\\\alice2\\\\artifact.html", "C:\\\\Users\\\\alice"),
        displayPath("/srv/artifact.html", "/"),
        fileName("/home/alice/paper/artifact.html"),
        fileName("C:\\\\Users\\\\alice\\\\paper\\\\artifact.html"),
        fileName("artifact.html"),
      ]));
    """

    result = subprocess.run(
        ["node", "--input-type=module", "-"], input=script, text=True, encoding="utf-8",
        capture_output=True, check=True,
    )

    assert json.loads(result.stdout) == [
        "~",
        "~/paper/artifact.html",
        "/home/alice2/paper/artifact.html",
        "/srv/paper/artifact.html",
        "/srv/home-link/artifact.html",
        "relative/artifact.html",
        "~\\paper\\artifact.html",
        "C:\\Users\\alice2\\artifact.html",
        "~/srv/artifact.html",
        "artifact.html",
        "artifact.html",
        "artifact.html",
    ]
