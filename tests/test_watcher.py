import asyncio
import logging
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


def test_a_project_that_takes_many_watches_says_so(tmp_path: Path, caplog) -> None:
    """A watch goes on every directory and the limit belongs to the login, so a tree that
    holds no artifact content spends other sessions' watches. The limit itself is only met
    at the moment a watch cannot be taken, and by a session that spent none of them, so the
    count is said while the project still works."""
    (tmp_path / "html").mkdir()
    for number in range(12):
        (tmp_path / "vendor" / f"pkg{number}").mkdir(parents=True)
    watcher = Watcher(tmp_path, ["*.html"], [], _unused_change)
    watcher.LOUD_WATCH_COUNT = 10
    loop = asyncio.new_event_loop()
    try:
        with caplog.at_level(logging.WARNING):
            watcher.start(loop)
    finally:
        watcher.stop()
        loop.close()
    said = "\n".join(record.getMessage() for record in caplog.records)
    assert "watching 15 directories" in said, said
    assert "vendor 13" in said and "ignore" in said, said

    # A project of the ordinary size says nothing: a warning every reader learns to skip
    # is worth less than the silence it replaces.
    quiet = Watcher(tmp_path, ["*.html"], [], _unused_change)
    caplog.clear()
    loop = asyncio.new_event_loop()
    try:
        with caplog.at_level(logging.WARNING):
            quiet.start(loop)
    finally:
        quiet.stop()
        loop.close()
    assert caplog.records == []


async def _unused_change(path: str) -> None:
    raise AssertionError("no file was changed in this test")
