"""
Prueba de humo SIN LLM (no gasta cuota de Gemini):

  1) verifica los guardrails deterministas offline (siempre corre),
  2) si el servicio MCP está arriba, lista sus herramientas y llama a fetch_html/parse_jsonld
     sobre una URL permitida.

Requiere (solo para la parte 2) el servicio corriendo: python scripts/run_services.py.
"""
import asyncio
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):  # consola de Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))
from price_extractor.guardrails import (  # noqa: E402
    ALLOWED_DOMAINS,
    normalize_price,
    validate_extraction,
    cross_field_consistency,
)

SCRAPER_URL = "http://127.0.0.1:8101/mcp"


def check_guardrails() -> None:
    print("[guardrails] normalize_price")
    for raw in ["$12.990", "12,990", "12.990 CLP", "1.234,56", "n/a", None]:
        print(f"    {raw!r} -> {normalize_price(raw)}")

    print("[guardrails] validate_extraction")
    cases = [
        {"url": "https://www.dartel.cl/p/1", "name": "Producto", "price": "$12.990", "currency": "CLP"},
        {"url": "https://evil.com/p/1", "name": "Producto", "price": "10", "currency": "CLP"},
        {"url": "https://rhona.cl/p/1", "name": "Producto", "price": "-5", "currency": "CLP"},
        {"url": "https://shop.sonepar.cl/p/1", "name": "Producto", "price": "100", "currency": "CLP",
         "price_before": "50"},
    ]
    for c in cases:
        print(f"    {c} -> {validate_extraction(c)}")

    print("[guardrails] cross_field_consistency")
    entries = [
        {"source": "jsonld", "price": "12.990"},
        {"source": "visible", "price": "12.990"},
        {"source": "meta", "price": "13.000"},
    ]
    print(f"    -> {cross_field_consistency(entries)}")


async def probe_service() -> None:
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(SCRAPER_URL) as (read, write, *_):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = [t.name for t in (await session.list_tools()).tools]
                print(f"[scraper] tools={tools}")
    except Exception as exc:  # noqa: BLE001 - smoke test must not fail if service is down
        print(f"[scraper] no disponible ({type(exc).__name__}: {exc}). "
              "Arranca python scripts/run_services.py para la parte 2.")


async def main() -> None:
    check_guardrails()
    print()
    await probe_service()


if __name__ == "__main__":
    asyncio.run(main())
