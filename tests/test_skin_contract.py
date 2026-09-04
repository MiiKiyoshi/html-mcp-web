"""A skin restyles the engine's components; it never introduces one.

Content is written against the vocabulary in templates/README.md, so a class that only
one skin styles renders bare under every other skin. This checks the rule against the
shipped skin, and against the reader's own skins when they are installed.

The slide engine and the report template each carry one rule that is about the browser
rather than about either layout, and a check here holds the two to the same account of
why it is there.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
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


def skeleton_vocabulary() -> set[str]:
    known: set[str] = set()
    for head in rule_heads(SKELETON.read_text(encoding="utf-8")):
        known |= names(head)
    return known


def unknown_components(skin_css: Path) -> dict[str, set[str]]:
    known = skeleton_vocabulary() | chrome_slots()
    offenders: dict[str, set[str]] = {}
    for head in rule_heads(skin_css.read_text(encoding="utf-8")):
        missing = names(head) - known
        if missing:
            offenders[head] = missing
    return offenders


def rule_with_its_reason(css_path: Path) -> str:
    """The browser rule together with the comment above it that says why it is there."""
    lines = css_path.read_text(encoding="utf-8").split("\n")
    at = [number for number, line in enumerate(lines) if line.strip() == BROWSER_RULE]
    assert len(at) == 1, f"{css_path} states {BROWSER_RULE!r} {len(at)} times"
    start = at[0] - 1
    while start >= 0 and "/*" not in lines[start]:
        start -= 1
    assert start >= 0, f"{css_path} states {BROWSER_RULE!r} without saying why"
    return "\n".join(lines[start:at[0] + 1])


def test_both_builders_give_the_browser_rule_the_same_reason() -> None:
    """The slide engine compiles skeleton.css with a skin's own; the report compiles
    template.css by itself. They read no stylesheet in common, so a rule that is about the
    browser rather than about either layout stands in both, and its account has to read the
    same in both: a copy is only as good as the day it was made."""
    assert rule_with_its_reason(SKELETON) == rule_with_its_reason(REPORT)


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
        ".tbar-logo { height: 56px; }\n"            # a chrome slot is fine
        "@media screen { .step { padding: 4px; } }\n"  # nested rules are read too
        ".sidebar-note { color: red; }\n",          # this one is not in the skeleton
        encoding="utf-8")
    assert unknown_components(skin) == {".sidebar-note": {"sidebar-note"}}
