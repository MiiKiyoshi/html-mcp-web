import asyncio
from pathlib import Path

from html_mcp_web.watcher import HtmlFileHandler


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
