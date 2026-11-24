import hashlib
import json
from pathlib import Path

import pytest

import html_mcp_web

PACKAGE = Path(html_mcp_web.__file__).resolve().parent


@pytest.mark.parametrize("folder", ["static/shared", "shared"])
def test_the_shared_files_are_the_copies_their_manifest_names(folder: str) -> None:
    """The files in static/shared, which the page loads, and in shared, the server modules, are
    written in tex-mcp-web and copied here by its scripts/share_page.py, never edited here: each
    is the copy its folder's manifest names, and no other file is in the folder. A change
    belongs in tex-mcp-web, copied again."""
    shared = PACKAGE / folder
    manifest = json.loads((shared / "MANIFEST.json").read_text(encoding="utf-8"))
    assert sorted(path.name for path in shared.iterdir() if path.is_file()) == sorted([*manifest["files"], "MANIFEST.json"])
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((shared / name).read_bytes()).hexdigest() == digest, (
            f"{folder}/{name} differs from the copy of {manifest['source']}")
