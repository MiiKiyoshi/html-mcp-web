import asyncio
import time
from pathlib import Path

from html_mcp_web.watcher import HtmlFileHandler, Watcher


def handler(tmp_path: Path) -> HtmlFileHandler:
    async def changed(path: str) -> None:
        return None

    return HtmlFileHandler(
        tmp_path,
        ["*.html", "assets/**"],
        ["private/**"],
        changed,
        asyncio.new_event_loop(),
    )


def test_watch_and_ignore_patterns(tmp_path: Path) -> None:
    value = handler(tmp_path)
    assert value._should_process(str(tmp_path / "artifact.html"))
    assert value._should_process(str(tmp_path / "assets" / "chart.json"))
    assert not value._should_process(str(tmp_path / "private" / "artifact.html"))
    assert not value._should_process(str(tmp_path / "notes.md"))


def test_config_triggers_reload_and_comment_storage_does_not(tmp_path: Path) -> None:
    value = handler(tmp_path)
    assert value._should_process(str(tmp_path / ".html-mcp-web.yaml"))
    assert not value._should_process(str(tmp_path / ".html-mcp-web" / "comments.json"))


def _watches(watcher: Watcher) -> set[tuple[str, bool]]:
    return {(watch.path, watch.is_recursive) for watch in watcher.observer._watches}


def _started(tmp_path: Path, roots: list[Path]) -> Watcher:
    watcher = Watcher(tmp_path, ["*.html"], [], _unused_change, roots)
    watcher.start(asyncio.new_event_loop())
    return watcher


def test_only_artifact_roots_are_watched_and_the_rest_is_never_walked(tmp_path: Path) -> None:
    """A watch goes on every directory under a recursive root and the limit belongs to the
    login, and a cold walk of a big tree takes longer than the server has to start. Trees
    that hold no artifact are neither scheduled nor enumerated."""
    (tmp_path / "html").mkdir()
    for number in range(300):
        (tmp_path / "sites" / f"run{number}" / "out").mkdir(parents=True)
    watcher = _started(tmp_path, [tmp_path / "html"])
    try:
        assert _watches(watcher) == {(str(tmp_path), False), (str(tmp_path / "html"), True)}
        assert watcher._census() == [(1, "html")]
    finally:
        watcher.stop()


def test_roots_are_merged_and_confined_to_the_project(tmp_path: Path) -> None:
    for name in ("html", "html/nested", "src"):
        (tmp_path / name).mkdir()
    watcher = Watcher(tmp_path, ["*.html"], [], _unused_change,
                      [tmp_path / "html" / "nested", tmp_path / "html", tmp_path / "src",
                       tmp_path.parent / "elsewhere"])
    assert watcher.roots == [tmp_path / "html", tmp_path / "src"]


def test_an_artifact_at_the_top_level_is_watched_flat_only(tmp_path: Path) -> None:
    """The project root is never a recursive root: an artifact kept there is covered by
    the flat watch, and a huge tree beside it is not walked for it."""
    (tmp_path / "slides.html").write_text("<html></html>", encoding="utf-8")
    for number in range(300):
        (tmp_path / "runs" / f"run{number}" / "out").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    at_root = _started(tmp_path, [tmp_path, tmp_path / "docs"])
    try:
        assert at_root.roots == [tmp_path / "docs"]
        assert _watches(at_root) == {(str(tmp_path), False), (str(tmp_path / "docs"), True)}
        assert not [watch for watch in _watches(at_root) if watch[1] and watch[0] == str(tmp_path)]
    finally:
        at_root.stop()


def test_a_root_that_appears_later_is_watched(tmp_path: Path) -> None:
    watcher = _started(tmp_path, [tmp_path / "html"])
    try:
        assert _watches(watcher) == {(str(tmp_path), False)}
        (tmp_path / "html").mkdir()
        (tmp_path / "other").mkdir()
        deadline = time.monotonic() + 3
        while _watches(watcher) != {(str(tmp_path), False), (str(tmp_path / "html"), True)}:
            assert time.monotonic() < deadline, _watches(watcher)
            time.sleep(0.05)
    finally:
        watcher.stop()


async def _unused_change(path: str) -> None:
    raise AssertionError("no file was changed in this test")
