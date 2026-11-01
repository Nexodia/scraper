"""
Price Spike — agent roles (skeleton).

Reuses the devspeed-live pattern (Coordinator/Dispatcher + Sequential Pipeline):

    User / trigger ──► coordinator (no tools, routes by site pattern)
                         │
            ┌────────────┴───────────────┐
            ▼                            ▼
 extraction_pipeline (Sequential)   api_browser_agent (SPA/API specialist)
   1. fetch_agent  (MCP: fetch_html)
   2. parse_agent  (MCP: parse_jsonld)
   3. verify_agent (gate, no tools)

TODO P2: implement fetch_agent + parse_agent + deterministic verify gate.
TODO P4: implement api_browser_agent, LLM fallback and the verifier agent loop.
"""
import os

from google.adk.agents import LlmAgent, SequentialAgent

from . import guardrails as g
from .toolsets import fetch_tools, parse_tools

MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

# ---------------------------------------------------------------- P2: fetch
fetch_agent = LlmAgent(
    name="fetch_agent",
    model=MODEL,
    description="Descarga el HTML de una URL de producto permitida.",
    instruction=(
        "Eres el agente de descarga. A partir de la URL del usuario, llama a `fetch_html` UNA vez. "
        "No descargues URLs fuera de los dominios permitidos."
    ),
    tools=[fetch_tools()],
    before_tool_callback=g.validate_url_args,  # TODO P2: define in guardrails
    output_key="raw_html",
)

# ---------------------------------------------------------------- P2: parse
parse_agent = LlmAgent(
    name="parse_agent",
    model=MODEL,
    description="Extrae el precio y sus metadatos del HTML.",
    instruction=(
        "Eres el agente de parseo. Llama a `parse_jsonld` sobre el HTML capturado; si no hay JSON-LD, "
        "extrae el precio visible y devuelve name, price, currency, unit y availability."
    ),
    tools=[parse_tools()],
    before_tool_callback=g.validate_extraction_args,  # TODO P2
    output_key="extraction",
)

# ---------------------------------------------------------------- P4: verifier gate
# verify_agent: runs AFTER parse_agent; deterministic gate (g.require_valid_extraction)
# rejects or asks for a re-extraction, mirroring the scaffold's `require_reservation`.

# ---------------------------------------------------------------- P4: SPA/API specialist
# api_browser_agent: uses `render_page` / `query_api` for sonepar (SPA) and VTEX/Magento APIs.

# ---------------------------------------------------------------- Workflow
extraction_pipeline = SequentialAgent(
    name="extraction_pipeline",
    description="Pipeline de extracción: descarga, parsea y verifica el precio.",
    sub_agents=[fetch_agent, parse_agent],
)

# ---------------------------------------------------------------- Coordinator
root_agent = LlmAgent(
    name="coordinator",
    model=MODEL,
    description="Punto de entrada: clasifica el sitio y delega al especialista.",
    instruction=(
        "Eres el coordinador del price extractor. NO ejecutas scraping: solo enrutas. "
        "Clasifica el sitio por su patrón (legacy_html, structured_server_rendered, "
        "structured_spa, spa_api) y delega a `extraction_pipeline` o al agente de API/navegador."
    ),
    sub_agents=[extraction_pipeline],
)
