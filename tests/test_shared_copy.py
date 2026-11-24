import hashlib
import json
from pathlib import Path

import html_mcp_web

SHARED = Path(html_mcp_web.__file__).resolve().parent / "static" / "shared"


def test_the_shared_page_files_are_the_copies_their_manifest_names() -> None:
    """The files in static/shared are written in tex-mcp-web and copied here by its
    scripts/share_page.py, never edited here: each is the copy the manifest names, and
    nothing else is in the folder. A change belongs in tex-mcp-web, copied again."""
    manifest = json.loads((SHARED / "MANIFEST.json").read_text(encoding="utf-8"))
    assert sorted(path.name for path in SHARED.iterdir()) == sorted([*manifest["files"], "MANIFEST.json"])
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((SHARED / name).read_bytes()).hexdigest() == digest, (
            f"static/shared/{name} differs from the copy of {manifest['source']}")
