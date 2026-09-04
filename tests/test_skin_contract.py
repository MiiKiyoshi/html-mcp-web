"""A skin restyles the engine's components; it never introduces one.

Content is written against the vocabulary in templates/README.md, so a class that only
one skin styles renders bare under every other skin. This checks the rule against the
shipped skin, and against the reader's own skins when they are installed. The vocabulary
is read from both sheets a deck is built from: components.css says what a component is,
in whatever page it sits on, and skeleton.css where it sits on a 1280x720 one.

A rule that is about the browser rather than about a layout belongs to components.css
with the rest, and a check here holds it to that one place.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
COMPONENTS = REPO / "html_mcp_web" / "components.css"
SKELETON = REPO / "html_mcp_web" / "slides" / "skeleton.css"
BUILD = REPO / "html_mcp_web" / "slides" / "build.py"
NEUTRAL = REPO / "templates" / "neutral-slides" / "skin.css"
REPORT = REPO / "templates" / "neutral-report" / "template.css"
USER_TEMPLATES = Path.home() / ".config" / "html-mcp-web" / "templates"
BROWSER_RULE = "letter-spacing: 0.01px;"


def rule_heads(css: str) -> list[str]:
    """Every selector list in the sheet, including inside @media."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    heads = []
    for match in re.finditer(r"([^{}]+)\{", css):
        head = match.group(1).strip()
        if head and not head.startswith("@"):
            heads.extend(part.strip() for part in head.split(","))
    return heads


def names(selector: str) -> set[str]:
    """Class names a selector depends on, which is what has to exist to style anything."""
    return set(re.findall(r"\.([A-Za-z][\w-]*)", selector))


def chrome_slots() -> set[str]:
    """Class names the builder puts on skin-supplied chrome images."""
    source = BUILD.read_text(encoding="utf-8")
    return set(re.findall(r'skin\.slot\("[^"]+"\),\s*"([^"]+)"', source))


def engine_vocabulary() -> set[str]:
    known: set[str] = set()
    for sheet in (COMPONENTS, SKELETON):
        for head in rule_heads(sheet.read_text(encoding="utf-8")):
            known |= names(head)
    return known


def unknown_components(skin_css: Path) -> dict[str, set[str]]:
    known = engine_vocabulary() | chrome_slots()
    offenders: dict[str, set[str]] = {}
    for head in rule_heads(skin_css.read_text(encoding="utf-8")):
        missing = names(head) - known
        if missing:
            offenders[head] = missing
    return offenders


def test_the_browser_rule_stands_once_and_says_why() -> None:
    """A deck and a report are read on the same browsers, so the rule that keeps Safari
    off its faster way of measuring belongs to neither layout. It sits in components.css,
    which both builders read, and nowhere else: a second copy is only as good as the day
    it was made."""
    sheets = {"components": COMPONENTS, "skeleton": SKELETON, "report": REPORT,
              "neutral skin": NEUTRAL}
    carrying = {name for name, sheet in sheets.items() if BROWSER_RULE in sheet.read_text(encoding="utf-8")}
    assert carrying == {"components"}, carrying
    lines = COMPONENTS.read_text(encoding="utf-8").split("\n")
    at = [number for number, line in enumerate(lines) if line.strip() == BROWSER_RULE]
    assert len(at) == 1, f"components.css states {BROWSER_RULE!r} {len(at)} times"
    assert "/*" in "\n".join(lines[max(0, at[0] - 12):at[0]]), "the rule stands without saying why"


def test_chrome_slots_are_read_from_the_builder() -> None:
    slots = chrome_slots()
    assert "tbar-logo" in slots and "full-art" in slots and "cover-bottom-left" in slots


def test_the_shipped_skin_introduces_no_component() -> None:
    assert unknown_components(NEUTRAL) == {}


@pytest.mark.parametrize("skin", sorted(USER_TEMPLATES.glob("*/skin.css")) if USER_TEMPLATES.is_dir() else [])
def test_installed_skins_introduce_no_component(skin: Path) -> None:
    offenders = unknown_components(skin)
    assert offenders == {}, (
        f"{skin} styles classes the skeleton does not define: {offenders}. "
        "Add the component to slides/skeleton.css and templates/README.md, then let the "
        "skin restyle it."
    )


def test_a_skin_that_invents_a_component_is_caught(tmp_path: Path) -> None:
    skin = tmp_path / "skin.css"
    skin.write_text(
        ":root { --accent: #123456; }\n"
        ".card { border-radius: 14px; }\n"          # restyling a known component is fine
        ".nw { letter-spacing: 0; }\n"              # one that components.css alone defines
        ".tbar-logo { height: 56px; }\n"            # a chrome slot is fine
        "@media screen { .step { padding: 4px; } }\n"  # nested rules are read too
        ".sidebar-note { color: red; }\n",          # this one is not in the skeleton
        encoding="utf-8")
    assert unknown_components(skin) == {".sidebar-note": {"sidebar-note"}}
