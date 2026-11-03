"""Find the place in an artifact's source that words selected on its rendered page come from.

The rendered page shows the source's text with its markup gone, its entities decoded, its
spacing changed, and titles and other words taken from attributes, so the words are
compared without spacing against the text the source shows, each character kept with its
place in the source. The context around the selection and the page's title pick among
repeated words.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser

# Attributes whose values a template prints on the page, such as a section's title.
SHOWN_ATTRIBUTES = {"data-title", "data-author", "data-meta", "data-sub", "title", "alt", "aria-label"}
HIDDEN_CONTENT = {"script", "style"}
VALUE_TOKEN = re.compile(r"&#?\w+;|.", re.S)


@dataclass(frozen=True)
class Place:
    line_start: int
    column_start: int
    line_end: int
    column_end: int
    # False when only some of the words, or only their surroundings, were found.
    whole: bool


class _ShownText(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=False)
        self.source = source
        self.line_starts = [0] + [match.end() for match in re.finditer(r"\n", source)]
        # Each character the page shows, without spacing, as (character, start, end) in the source.
        self.kept: list[tuple[str, int, int]] = []
        # Each section with a title, as (title, start, end) in the source, closed when it ends.
        self.sections: list[list] = []
        self.open_sections: list[list] = []
        self.hidden = 0

    def here(self) -> int:
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def keep(self, text: str, start: int, end: int | None = None) -> None:
        # A $ delimits math, which the page shows rendered, and the page sends a formula
        # as the TeX between the delimiters.
        for index, character in enumerate(text):
            if not character.isspace() and character != "$":
                self.kept.append((character, start + index, start + index + 1) if end is None
                                 else (character, start, end))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        start = self.here()
        raw = self.get_starttag_text() or ""
        if tag in HIDDEN_CONTENT:
            self.hidden += 1
        if tag == "section":
            section = [dict(attrs).get("data-title") or "", start, len(self.source)]
            self.sections.append(section)
            self.open_sections.append(section)
        for name, value in attrs:
            if name not in SHOWN_ATTRIBUTES or not value:
                continue
            found = re.search(rf'\s{re.escape(name)}\s*=\s*(["\']?)', raw)
            if found is None:
                continue
            position = start + found.end()
            for token in VALUE_TOKEN.findall(raw[found.end():found.end() + len(raw)]):
                if token == found.group(1) or (not found.group(1) and token.isspace()) or token == ">":
                    break
                self.keep(html.unescape(token), position, position + len(token))
                position += len(token)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag in HIDDEN_CONTENT:
            self.hidden -= 1

    def handle_endtag(self, tag: str) -> None:
        if tag in HIDDEN_CONTENT and self.hidden > 0:
            self.hidden -= 1
        if tag == "section" and self.open_sections:
            self.open_sections.pop()[2] = self.here()

    def handle_data(self, data: str) -> None:
        if self.hidden == 0:
            self.keep(data, self.here())

    def handle_entityref(self, name: str) -> None:
        if self.hidden == 0:
            start = self.here()
            self.keep(html.unescape(f"&{name};"), start, start + len(name) + 2)

    def handle_charref(self, name: str) -> None:
        if self.hidden == 0:
            start = self.here()
            self.keep(html.unescape(f"&#{name};"), start, start + len(name) + 3)


def _squeeze(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _line_column(source: str, line_starts: list[int], offset: int) -> tuple[int, int]:
    """1-based line and 0-based column in UTF-16 units, the editor's."""
    line = max(index for index, start in enumerate(line_starts) if start <= offset)
    column = len(source[line_starts[line]:offset].encode("utf-16-le")) // 2
    return line + 1, column


def locate(source: str, quote: str, prefix: str = "", suffix: str = "", title: str = "") -> Place | None:
    shown = _ShownText(source)
    shown.feed(source)
    shown.close()
    text = "".join(character for character, _, _ in shown.kept)
    before, after = _squeeze(prefix)[-80:], _squeeze(suffix)[:80]

    def score(at: int, length: int) -> int:
        matched = 0
        while matched < len(before) and at - matched - 1 >= 0 and text[at - matched - 1] == before[-matched - 1]:
            matched += 1
        ahead = 0
        while ahead < len(after) and at + length + ahead < len(text) and text[at + length + ahead] == after[ahead]:
            ahead += 1
        offset = shown.kept[at][1]
        titled = bool(title) and any(
            name == title and start <= offset < end for name, start, end in shown.sections)
        return matched + ahead + (1000 if titled else 0)

    def best(wanted: str) -> int | None:
        if not wanted:
            return None
        found = [match.start() for match in re.finditer(f"(?={re.escape(wanted)})", text)]
        return max(found, key=lambda at: score(at, len(wanted))) if found else None

    def place(at: int, length: int, whole: bool) -> Place:
        line_start, column_start = _line_column(source, shown.line_starts, shown.kept[at][1])
        line_end, column_end = _line_column(source, shown.line_starts, shown.kept[at + length - 1][2])
        return Place(line_start, column_start, line_end, column_end, whole)

    wanted = _squeeze(quote)
    at = best(wanted)
    if at is not None:
        return place(at, len(wanted), True)
    # Words the source does not hold as written, such as math it writes as TeX: the longest
    # run of two or more of the selected words it does hold. One word alone is found in too
    # many places to say where the selection came from.
    words = quote.split()[:40]
    for size in range(len(words) - 1, 1, -1):
        for first in range(len(words) - size + 1):
            run = "".join(words[first:first + size])
            if len(run) < 4:
                continue
            at = best(run)
            if at is not None:
                return place(at, len(run), False)
    # None of them: the place where the words that lead up to the selection end.
    lead = before[-24:]
    at = best(lead)
    if at is not None:
        line, column = _line_column(source, shown.line_starts, shown.kept[at + len(lead) - 1][2])
        return Place(line, column, line, column, False)
    return None


@dataclass(frozen=True)
class Shown:
    """What the page shows of a stretch of the source, without spacing: the words, the
    words before and after them, and the title of the section around them."""

    quote: str
    before: str
    after: str
    title: str


def shown_text(source: str, line_start: int, column_start: int, line_end: int, column_end: int) -> Shown:
    """The page's text for a selection in the editor, whose columns count UTF-16 units."""
    shown = _ShownText(source)
    shown.feed(source)
    shown.close()

    def offset(line: int, column: int) -> int:
        if not 1 <= line <= len(shown.line_starts):
            raise ValueError(f"line {line} is not in the source")
        start = shown.line_starts[line - 1]
        units = source[start:].encode("utf-16-le")[:column * 2].decode("utf-16-le", errors="ignore")
        return start + len(units)

    start, end = offset(line_start, column_start), offset(line_end, column_end)
    inside = [index for index, (_, first, _) in enumerate(shown.kept) if start <= first < end]
    text = "".join(character for character, _, _ in shown.kept)
    if not inside:
        return Shown("", "", "", "")
    first, last = inside[0], inside[-1]
    title = next((name for name, opened, closed in shown.sections if opened <= start < closed), "")
    return Shown(text[first:last + 1], text[max(0, first - 80):first], text[last + 1:last + 81], title)
