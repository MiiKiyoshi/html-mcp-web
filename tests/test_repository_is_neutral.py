"""The repository carries no organization identity: private skins live outside it."""

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

# Words, colours, and file kinds that belong to a private skin. Any hit in a tracked file is a
# leak, so the list stays deliberately blunt.
PRIVATE_MARKERS = re.compile(
    r"seda|unist|first in change|semiconductor design automation|001c54|44c1c3|093464",
    re.IGNORECASE,
)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp"}


def tracked_files() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True,
    ).stdout
    return [ROOT / name for name in output.decode().split("\0") if name]


def test_tracked_files_carry_no_private_identity() -> None:
    hits = []
    for path in tracked_files():
        # A tracked file removed in the working tree is on its way out; this file itself
        # names the markers it looks for.
        if not path.is_file() or path == Path(__file__).resolve():
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
            if PRIVATE_MARKERS.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:80]}")
    assert hits == [], "\n".join(hits)
