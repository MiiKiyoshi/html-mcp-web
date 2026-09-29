"""The repository carries no private identity: private skins and names live outside it."""

import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
# One pattern per line. The list names what must stay private, so it lives outside the
# repository, and a machine without it skips the check.
MARKERS_FILE = Path.home() / ".config" / "html-mcp-web" / "private-markers.txt"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp"}


def tracked_files() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True,
    ).stdout
    return [ROOT / name for name in output.decode().split("\0") if name]


@pytest.mark.skipif(not MARKERS_FILE.is_file(), reason="no private marker list on this machine")
def test_tracked_files_carry_no_private_identity() -> None:
    lines = MARKERS_FILE.read_text(encoding="utf-8").splitlines()
    markers = re.compile("|".join(f"(?:{line})" for line in lines if line.strip()), re.IGNORECASE)
    hits = []
    for path in tracked_files():
        # A tracked file removed in the working tree is on its way out.
        if not path.is_file():
            continue
        # docs/ holds curated, manually reviewed product screenshots for the README; every
        # other raster image is refused so a private skin's assets cannot slip in.
        if path.suffix.lower() in IMAGE_SUFFIXES:
            if Path("docs") not in path.relative_to(ROOT).parents:
                hits.append(f"{path.relative_to(ROOT)}: raster image tracked")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if markers.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:80]}")
    assert hits == [], "\n".join(hits)
