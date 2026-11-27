"""html-mcp-web as the modules it shares with the other review tools know it (shared/tool.py)."""

from .shared.tool import Tool

TOOL = Tool(name="html-mcp-web", package="html_mcp_web", server="review server", event="[HTML review event]",
            plugin="html-mcp", page="review page", person="reviewer", work="review", press="[review]",
            extras="[mcp]")
