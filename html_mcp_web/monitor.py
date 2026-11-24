"""The html-mcp review monitor, which the plugin's monitors/review.sh starts (shared/monitor.py).

Run as ``python -m html_mcp_web.monitor [session pid | --from pid]``.
"""

from .shared import monitor
from .tool import TOOL

if __name__ == "__main__":
    monitor.main(TOOL)
