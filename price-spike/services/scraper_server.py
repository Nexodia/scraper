"""
Scraper service exposed as an MCP server (Streamable HTTP).

Plays the role of the "legacy/scraping microservice" in the devspeed-live
pattern: agents never touch HTTP/browser/JSON-LD internals directly; they only
see the tools published here via MCP.

Default port: 8101 -> http://127.0.0.1:8101/mcp
"""
import json
import os
import re
import sys
from pathlib import Path

import httpx
from mcp.server.mcpserver import MCPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))
from price_extractor.guardrails import ALLOWED_DOMAINS, is_allowed_url  # noqa: E402

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "price-spike/0.1 (university research; polite, rate-limited)"
)
MAX_HTML_CHARS = 300_000  # keep MCP payloads bounded; enough for JSON-LD + visible price
_JSONLD_RE = re.compile(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S)

mcp = MCPServer(
    name="scraper-service",
    instructions=(
        "Servicio de scraping: descarga HTML y extrae datos estructurados (JSON-LD). "
        "Solo acepta URLs de los dominios permitidos."
    ),
)


@mcp.tool()
def fetch_html(url: str) -> dict:
    """Descarga el HTML de una URL permitida. Devuelve status, content_type y texto (truncado)."""
    if not is_allowed_url(url):
        return {"status": "blocked", "reason": "domain not allowed", "url": url}
    with httpx.Client(follow_redirects=True, timeout=20, headers={"User-Agent": USER_AGENT}) as client:
        resp = client.get(url)
    text = resp.text[:MAX_HTML_CHARS]
    return {
        "status": "ok" if resp.status_code == 200 else "http_error",
        "http_status": resp.status_code,
        "final_url": str(resp.url),
        "content_type": resp.headers.get("content-type", ""),
        "length": len(text),
        "truncated": len(resp.text) > MAX_HTML_CHARS,
        "text": text,
    }


@mcp.tool()
def parse_jsonld(html: str) -> dict:
    """Extrae los bloques <script type="application/ld+json"> del HTML y los devuelve parseados."""
    documents = []
    for i, raw in enumerate(_JSONLD_RE.findall(html or "")):
        try:
            documents.append({"index": i, "data": json.loads(raw)})
        except json.JSONDecodeError:
            documents.append({"index": i, "error": "invalid_json"})
    return {"status": "ok", "count": len(documents), "documents": documents}


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8101")),
    )
