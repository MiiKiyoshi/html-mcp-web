import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for the UI helper test")
def test_home_path_display_boundaries() -> None:
    module = (Path(__file__).parent.parent / "html_mcp_web" / "static" / "path-display.mjs").as_uri()
    script = f"""
      import {{ displayPath }} from {json.dumps(module)};
      const home = "/home/users/kiyoshi";
      console.log(JSON.stringify([
        displayPath(home, home),
        displayPath(`${{home}}/paper/artifact.html`, home),
        displayPath(`${{home}}2/paper/artifact.html`, home),
        displayPath("/srv/paper/artifact.html", home),
        displayPath("/srv/home-link/artifact.html", home),
        displayPath("relative/artifact.html", home),
      ]));
    """

    result = subprocess.run(
        ["node", "--input-type=module", "-"], input=script, text=True,
        capture_output=True, check=True,
    )

    assert json.loads(result.stdout) == [
        "~",
        "~/paper/artifact.html",
        "/home/users/kiyoshi2/paper/artifact.html",
        "/srv/paper/artifact.html",
        "/srv/home-link/artifact.html",
        "relative/artifact.html",
    ]
