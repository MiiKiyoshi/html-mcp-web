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


def test_the_shared_hook_files_are_the_copies_their_manifest_names() -> None:
    """plugin/hooks holds this tool's own hook beside the files the review tools' plugins
    share, the guide gates' record and the script that starts a hook with a Python that runs,
    written in tex-mcp-web and copied here by its scripts/share_page.py with a manifest of
    those files."""
    hooks = PACKAGE.parent / "plugin" / "hooks"
    manifest = json.loads((hooks / "MANIFEST.json").read_text(encoding="utf-8"))
    assert sorted(manifest["files"]) == ["guide_record.py", "python.sh"]
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((hooks / name).read_bytes()).hexdigest() == digest, (
            f"plugin/hooks/{name} differs from the copy of {manifest['source']}")


def test_the_browser_the_tests_drive_is_the_copy_its_manifest_names() -> None:
    """tests/chrome.py, the browser the tests drive, is written in tex-mcp-web and copied here
    beside this tool's own tests by its scripts/share_page.py, never edited here: it is the copy
    the manifest in tests names. A change belongs in tex-mcp-web, copied again, and what only
    this tool's tests use is in tests/html_chrome.py."""
    tests = Path(__file__).resolve().parent
    manifest = json.loads((tests / "MANIFEST.json").read_text(encoding="utf-8"))
    assert "chrome.py" in manifest["files"]
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((tests / name).read_bytes()).hexdigest() == digest, (
            f"tests/{name} differs from the copy of {manifest['source']}")
