import pytest

from html_mcp_web.shared.update import Update
from html_mcp_web.tool import TOOL


def pytest_addoption(parser):
    parser.addoption("--part", default="", help="run one part of the tests, as 2/3 for the second of three")


def pytest_collection_modifyitems(config, items):
    """With --part i/n, keep every nth test from the ith on. The CI jobs of a slow system each
    run one part, side by side."""
    if not config.getoption("--part"):
        return
    part, parts = (int(number) for number in config.getoption("--part").split("/"))
    kept = items[part - 1::parts]
    config.hook.pytest_deselected(items=[item for item in items if item not in kept])
    items[:] = kept


@pytest.fixture(autouse=True)
def no_plugin_monitor(tmp_path, monkeypatch):
    """No plugin monitor runs for a test's session, whatever runs for the one running the
    tests. A server a test starts as its own process reads XDG_CACHE_HOME instead."""
    monkeypatch.setattr(TOOL, "monitors", tmp_path / "no-monitor")


@pytest.fixture(autouse=True)
def no_update(monkeypatch):
    """No test fetches the upstream of the clone it runs from to see what is newer, and none
    updates the install. A test of the page's Update puts its own answers in their place."""
    async def unknown(self):
        return None, None

    async def refused(self, *command, timeout=None):
        raise AssertionError("a test ran a real update")

    monkeypatch.setattr(Update, "news", unknown)
    monkeypatch.setattr(Update, "_run", refused)
