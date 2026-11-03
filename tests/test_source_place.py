from html_mcp_web.source_place import Place, locate

SOURCE = '''<body data-author="A. Writer" data-meta="Lab|2026">
<section data-title="Methods">
  <p>The quick brown fox &amp; the
     lazy dog. 😀 Then $\\alpha_k$ grows with the step.</p>
</section>
<section data-title="Results">
  <p>The quick brown fox again.</p>
  <script>const quick = "brown fox";</script>
</section>
</body>'''
LINES = SOURCE.split("\n")


def selected(place: Place) -> str:
    """The source text a place covers, read with UTF-16 columns as the editor reads them."""
    def index(line: int, column: int) -> int:
        text = LINES[line - 1]
        return len(text.encode("utf-16-le")[:column * 2].decode("utf-16-le"))
    if place.line_start == place.line_end:
        line = LINES[place.line_start - 1]
        return line[index(place.line_start, place.column_start):index(place.line_end, place.column_end)]
    return "\n".join([LINES[place.line_start - 1][index(place.line_start, place.column_start):],
                      *LINES[place.line_start:place.line_end - 1],
                      LINES[place.line_end - 1][:index(place.line_end, place.column_end)]])


def test_repeated_words_are_told_apart_by_their_surroundings_and_page_title() -> None:
    assert locate(SOURCE, "quick brown fox", "The ", " again.", "").line_start == 7
    assert locate(SOURCE, "quick brown fox", "The ", " & the", "").line_start == 3
    assert locate(SOURCE, "quick brown fox", "", "", "Results").line_start == 7


def test_the_page_shows_decoded_text_without_the_source_spacing() -> None:
    place = locate(SOURCE, "fox & the lazy", "", "", "")
    assert place.whole and selected(place) == "fox &amp; the\n     lazy"


def test_words_taken_from_attributes_are_found_in_the_attribute() -> None:
    assert selected(locate(SOURCE, "A. Writer", "", "", "")) == "A. Writer"
    assert selected(locate(SOURCE, "Results", "", "", "")) == "Results"


def test_columns_count_utf16_units_as_the_editor_does() -> None:
    assert selected(locate(SOURCE, "Then", "😀 ", " ", "Methods")) == "Then"


def test_math_written_as_tex_selects_the_words_around_it_or_the_place_before() -> None:
    partial = locate(SOURCE, "αk grows with", "Then ", " the step", "Methods")
    assert not partial.whole and selected(partial) == "grows with"
    alone = locate(SOURCE, "αk", "lazy dog. 😀 Then ", " grows", "Methods")
    assert not alone.whole and (alone.line_start, alone.line_start) == (alone.line_end, 4)
    assert LINES[3][:len(LINES[3].encode("utf-16-le")[:alone.column_start * 2].decode("utf-16-le"))].endswith("Then")


def test_words_only_a_script_holds_are_not_shown_text() -> None:
    assert locate(SOURCE, "const quick", "", "", "") is None



def test_a_source_selection_gives_the_text_the_page_shows() -> None:
    from html_mcp_web.source_place import shown_text

    fox = LINES[2].index("fox")
    shown = shown_text(SOURCE, 3, fox, 4, LINES[3].index("lazy") + 4)   # "fox &amp; the\n     lazy"
    assert (shown.quote, shown.title) == ("fox&thelazy", "Methods")
    assert shown.before.endswith("MethodsThequickbrown") and shown.after.startswith("dog.😀Then")
    # Past the 😀 an editor column is a UTF-16 unit, two for the 😀 itself.
    then = LINES[3].index("Then") + 1
    assert shown_text(SOURCE, 4, then, 4, then + 4).quote == "Then"
    # Markup alone shows nothing.
    assert shown_text(SOURCE, 2, 0, 2, 8).quote == ""


def test_a_formula_is_found_by_its_tex_without_the_dollar_signs() -> None:
    place = locate(SOURCE, " \\alpha_k ", "😀 Then ", " grows with", "Methods")
    assert place.whole and selected(place) == "\\alpha_k"
    # Prose with a formula in it, as the page sends it, the formula as its TeX.
    assert selected(locate(SOURCE, "Then \\alpha_k grows", "", "", "Methods")) == "Then $\\alpha_k$ grows"
