"""Parse the shared content format used by HTML artifact templates."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path


VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr",
}


@dataclass
class Element:
    tag: str
    attributes: dict[str, str]
    children: list[Element | str] = field(default_factory=list)

    def inner_html(self, excluded: set[int] | None = None) -> str:
        excluded = excluded if excluded is not None else set()
        return "".join(
            child if isinstance(child, str) else "" if id(child) in excluded else child.to_html()
            for child in self.children
        )

    def to_html(self) -> str:
        attributes = "".join(
            f' {name}="{html.escape(value, quote=True)}"' if value != "" else f" {name}"
            for name, value in self.attributes.items()
        )
        if self.tag in VOID_ELEMENTS:
            return f"<{self.tag}{attributes}>"
        return f"<{self.tag}{attributes}>{self.inner_html()}</{self.tag}>"

    def text(self) -> str:
        return "".join(child if isinstance(child, str) else child.text() for child in self.children)


class ContentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.root = Element("document", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(tag, {name: value if value is not None else "" for name, value in attrs})
        self.stack[-1].children.append(element)
        if tag not in VOID_ELEMENTS:
            self.stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_ELEMENTS:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if len(self.stack) == 1 or self.stack[-1].tag != tag:
            raise ValueError(f"unexpected closing tag: {tag}")
        self.stack.pop()

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)

    def handle_entityref(self, name: str) -> None:
        self.stack[-1].children.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.stack[-1].children.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.stack[-1].children.append(f"<!--{data}-->")

    def close(self) -> None:
        super().close()
        if len(self.stack) != 1:
            raise ValueError(f"unclosed tag: {self.stack[-1].tag}")


@dataclass(frozen=True)
class ContentSection:
    title: str
    body_html: str
    script_html: str
    layout: str = "body"
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TemplateContent:
    title: str
    author: str
    metadata: list[str]
    cover_script_html: str
    sections: list[ContentSection]
    subtitle: str = ""


def _elements(root: Element, tag: str) -> list[Element]:
    found = []
    for child in root.children:
        if not isinstance(child, Element):
            continue
        if child.tag == tag:
            found.append(child)
        found.extend(_elements(child, tag))
    return found


def _script_child(element: Element) -> Element | None:
    matches = [
        child for child in element.children
        if isinstance(child, Element)
        and child.tag == "aside"
        and "script" in child.attributes.get("class", "").split()
    ]
    if len(matches) > 1:
        raise ValueError("an element may contain at most one direct aside.script")
    return matches[0] if matches else None


def parse_template_content(path: Path) -> TemplateContent:
    parser = ContentParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    titles = _elements(parser.root, "title")
    bodies = _elements(parser.root, "body")
    if len(titles) != 1 or len(bodies) != 1:
        raise ValueError("content requires exactly one title and one body")
    body = bodies[0]
    if "data-author" not in body.attributes or "data-meta" not in body.attributes:
        raise ValueError("body requires data-author and data-meta")
    section_elements = [
        child for child in body.children
        if isinstance(child, Element) and child.tag == "section"
    ]
    if not section_elements:
        raise ValueError("content requires at least one direct section")
    sections = []
    for section in section_elements:
        # A page carrying its own title bar needs the title; a template's other page
        # kinds name themselves through their own markup.
        layout = section.attributes.get("data-layout", "body").strip() or "body"
        if layout == "body" and "data-title" not in section.attributes:
            raise ValueError("each direct body section requires data-title")
        script = _script_child(section)
        sections.append(ContentSection(
            title=section.attributes.get("data-title", "").strip(),
            body_html=section.inner_html({id(script)} if script is not None else set()).strip(),
            script_html=script.inner_html().strip() if script is not None else "",
            layout=layout,
            attributes=dict(section.attributes),
        ))
    cover_script = _script_child(body)
    return TemplateContent(
        title=html.unescape(titles[0].text()).strip(),
        author=body.attributes["data-author"].strip(),
        metadata=[value.strip() for value in body.attributes["data-meta"].split("|")],
        cover_script_html=cover_script.inner_html().strip() if cover_script is not None else "",
        sections=sections,
        subtitle=body.attributes.get("data-sub", "").strip(),
    )
