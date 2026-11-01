"""
Integration layer: connects agents to the scraper service via MCP.

Architectural concerns solved here (mirrors the teacher's scaffold):
  * Decoupling       -> agents know MCP URLs, not HTTP/browser internals.
  * Least privilege  -> each agent gets ONLY the tools of its role (tool_filter).
  * Configurability  -> URLs via environment variables.
"""
import os

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

SCRAPER_MCP_URL = os.getenv("SCRAPER_MCP_URL", "http://127.0.0.1:8101/mcp")


def _toolset(url: str, allowed: list[str]) -> McpToolset:
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(url=url, timeout=15),
        tool_filter=allowed,  # explicit allow-list: what's not here, the LLM never sees
    )


def fetch_tools() -> McpToolset:
    return _toolset(SCRAPER_MCP_URL, ["fetch_html"])


def parse_tools() -> McpToolset:
    return _toolset(SCRAPER_MCP_URL, ["parse_jsonld"])


def browser_tools() -> McpToolset:
    # TODO P3: add `render_page` and `query_api` to the MCP facade and expose them here.
    return _toolset(SCRAPER_MCP_URL, ["render_page", "query_api"])
