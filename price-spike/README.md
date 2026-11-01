# Price Spike — extracción de precios con verificación agéntica

Spike de investigación para decidir, con evidencia, qué estrategia de extracción de precios usar por
sitio y si una capa de verificación agéntica se justifica. Reutiliza el patrón del scaffold del
profesor (`devspeed-live`: Google ADK + MCP + guardrails).

- Plan completo y metodología: [PLAN.md](../PLAN.md)
- Clasificación de sitios: [config/sites.json](config/sites.json)

## Estructura

| Ruta | Rol arquitectónico |
| --- | --- |
| `agents/price_extractor/agent.py` | Roles de agentes (coordinator + pipeline + verifier) |
| `agents/price_extractor/toolsets.py` | Conexión MCP + mínimo privilegio (`tool_filter`) |
| `agents/price_extractor/guardrails.py` | Validaciones deterministas alrededor del LLM |
| `services/scraper_server.py` | Fachada MCP del "microservicio" de scraping |
| `services/sonepar_auth.py` | OAuth2 (refresh grant) + clientes de API para Sonepar |
| `scripts/` | setup, arranque de servicios, smoke test, demo, login de Sonepar |
| `config/sites.json` | Los 5 sitios y su patrón detectado |
| `data/raw/`, `data/gold_set.json` | Capturas crudas y ground truth (P1) |

## Puesta en marcha (Windows + VS Code)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
.\.venv\Scripts\Activate.ps1
python scripts\run_services.py   # terminal 1: servidor MCP de scraping
python scripts\smoke_test.py     # terminal 2: verificación SIN LLM
```

El smoke test valida los guardrails sin gastar cuota y, si el servicio MCP está arriba, lista sus
herramientas.

## Estado

- [x] P0 — scaffold y configuración de sitios
- [~] P1 — gold set (borrador generado; falta confirmación manual en `data/gold_set.review.md`)
- [ ] P2 — baseline determinista (A1 crawler, A2 JSON-LD)
- [ ] P3 — browser + APIs (A3)
- [ ] P4 — extracción LLM + verifier agéntico (A4/A5)
- [ ] P5 — evidencia → MCDA → ADR-001
