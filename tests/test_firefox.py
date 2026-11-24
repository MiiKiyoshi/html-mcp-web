"""A Firefox the package starts, to print a page or set a report's pages (html_mcp_web/firefox.py)."""

import socket
from pathlib import Path

from html_mcp_web.firefox import firefox
from tests.firefox import needs_firefox


@needs_firefox
def test_a_firefox_is_gone_with_its_profile_once_its_session_ends() -> None:
    """Nothing listens on its port afterwards, and its profile is removed, which Windows
    refuses while a browser still holds it."""
    with firefox() as client:
        port = client.port
        profile = Path(client.session_capabilities["moz:profile"])
        assert profile.is_dir()
    assert not profile.exists()
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0
