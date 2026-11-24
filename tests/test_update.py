"""The page's Update for html-mcp-web, which is installed from a git clone and not from PyPI:
what runs and what is on disk carry the clone's commit, what is newer is the commits the
clone's upstream has that it lacks, and an update pulls the clone and installs it again with its
[mcp] extra. The shared module is tex-mcp-web's (shared/update.py), tested there in full."""

import subprocess
import sys
from pathlib import Path

import pytest

from html_mcp_web import __version__
from html_mcp_web.shared.update import Update, UpdateError
from html_mcp_web.tool import TOOL

ROOT = Path(__file__).resolve().parent.parent
# The real one, which the no_update fixture replaces for every other test.
NEWS = Update.news


def commit(folder: Path) -> str:
    """A commit in the git clone in *folder*, made there first: its short hash."""
    git = ("git", "-C", str(folder), "-c", "user.name=Ann", "-c", "user.email=ann@example.com")
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "change"], check=True)
    return subprocess.run([*git, "rev-parse", "--short", "HEAD"], check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()


def test_what_runs_and_what_is_on_disk_carry_the_clones_commit(tmp_path: Path) -> None:
    """The version stays the same from one commit to the next, so the commit tells what runs
    from what a pull put on disk."""
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()
    update = Update(TOOL, __version__, lambda: True)
    assert update.version == f"{__version__}+{head}" == update.on_disk()
    clone = tmp_path / "clone"
    (clone / "html_mcp_web").mkdir(parents=True)
    (clone / "html_mcp_web" / "__init__.py").write_text(f'__version__ = "{__version__}"\n', encoding="utf-8")
    first = commit(clone)
    update.root, update.package = clone, clone / "html_mcp_web"
    assert update.on_disk() == f"{__version__}+{first}"
    second = commit(clone)
    assert update.on_disk() == f"{__version__}+{second}" != f"{__version__}+{first}"


def test_only_a_git_clone_with_its_own_environment_updates_itself(tmp_path: Path, monkeypatch) -> None:
    """html-mcp-web has no package on PyPI to upgrade: a clone with its own virtual
    environment updates by git pull, and anything else says to ask the agent."""
    update = Update(TOOL, __version__, lambda: True)
    update.root = tmp_path
    monkeypatch.setattr(sys, "base_prefix", sys.prefix + "-base")
    assert update.way() is None
    (tmp_path / ".git").mkdir()
    assert update.way() == "checkout"
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert update.way() is None


async def test_an_update_pulls_the_clone_and_installs_it_again_with_its_mcp_extra(tmp_path: Path, monkeypatch) -> None:
    """The pull is fast-forward only, and the install again takes a changed dependency of the
    MCP server, which the [mcp] extra holds. A failed command is the error."""
    ran = []

    async def note(self, *command, timeout=None):
        ran.append(command)
        if command[3:5] == ("pull", "-q") and len(ran) > 2:
            raise UpdateError("fatal: Not possible to fast-forward, aborting.")
        return ""

    monkeypatch.setattr(Update, "_run", note)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/git")
    update = Update(TOOL, __version__, lambda: True)
    update.root = tmp_path
    monkeypatch.setattr(update, "way", lambda: "checkout")
    await update.run()
    pip = (sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check")
    assert ran == [("/usr/bin/git", "-C", str(tmp_path), "pull", "-q", "--ff-only"), (*pip, "-e", f"{tmp_path}[mcp]")]
    with pytest.raises(UpdateError, match="Not possible to fast-forward"):
        await update.run()
    assert len(ran) == 3
    monkeypatch.setattr(update, "way", lambda: None)
    with pytest.raises(UpdateError, match="Ask your agent to update html-mcp-web"):
        await update.run()


async def test_what_is_newer_is_the_upstreams_commits_fetched_once_a_day(tmp_path: Path, monkeypatch) -> None:
    """The clone's upstream is fetched, and the commits it has that the clone lacks are
    counted, once a day; PyPI is never asked."""
    monkeypatch.setattr(Update, "news", NEWS)
    ran = []

    async def git(self, *command, timeout=None):
        ran.append(command[3:])
        return "2" if command[3] == "rev-list" else ""

    async def pypi(self):
        raise AssertionError("asked PyPI")

    monkeypatch.setattr(Update, "_run", git)
    monkeypatch.setattr(Update, "_latest", pypi)
    update = Update(TOOL, __version__, lambda: True)
    update.root = tmp_path
    (tmp_path / ".git").mkdir()
    assert await update.news() == (None, 2) and await update.news() == (None, 2)
    assert ran == [("fetch", "-q"), ("rev-list", "--count", "HEAD..@{upstream}")]
