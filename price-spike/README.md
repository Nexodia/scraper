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
- [x] P1 — gold set completo (25/25 con precios; Sonepar vía API de invitado)
- [x] P2 — baseline determinista (A1 CSS, A2 estructurado) medido contra el gold set
- [x] P3 — browser (A3 Playwright) + APIs oficiales, medidos contra el gold set
- [x] P4 — extracción LLM (A4) + verifier agéntico (A5), medidos contra el gold set
- [x] P5 — evidencia → MCDA → ADR-001

## Resultado P5 (MCDA + ADR)

- **Decisión**: adoptar **A6 híbrido determinista-first** (JSON-LD/meta/CSS por sitio + API
  autenticada para sonepar; LLM como fallback opcional). Puntaje MCDA **94,55** (siguiente: A4 76,60);
  decisión **estable** ante variaciones de ±0,10 en cualquier peso.
- **ADR**: `docs/ADR-001.md` · **Trazabilidad**: `docs/traceability.md` · **MCDA**: `data/evidence_mcda.json`.

## Resultado P2 (baseline determinista, sobre HTML cacheado)

| Sitio | A1 CSS | A2 estructurado | Mejor |
| --- | --- | --- | --- |
| dartel (VTEX) | 0 % (precio renderiza por JS) | **100 %** (JSON-LD) | 100 % |
| vitelenergia (Magento 2 Hyva) | 40 % (selector frágil) | **80 %** (meta) | 80 % |
| tecnored (Magento) | **100 %** (`data-price-amount`) | **100 %** (meta) | 100 % |
| rhona (MIPLUS legacy) | **100 %** (CSS visible) | 0 % (sin datos estructurados) | 100 % |
| sonepar (SPA) | 0 % | 0 % | 0 % → requiere A3 (API) |

Total: **cobertura 20/25 (80 %)**; **exactitud 19/20 sobre cubiertos (95 %)** — 19/25 (76 %) si se
cuenta sonepar. Evidencia: `data/evidence_p2.json`.
Hallazgos: (1) ningún método determinista cubre todos los patrones; (2) vitelenergia #4 es un
producto multi-variante donde el meta refleja otra variante; (3) Hyva renderiza el precio por JS,
lo que hace frágiles los selectores CSS.

## Resultado P3 (browser + APIs)

| Sitio | A3 browser | A3 API | Recomendado |
| --- | --- | --- | --- |
| dartel (VTEX) | 100 % (~11,6 s) | 100 % (VTEX search por mpn, ~380 ms) | A2 JSON-LD (más barato) |
| vitelenergia (Magento 2) | 80 % (~14 s) | 60 % (GraphQL; variantes ambiguas) | A2 meta |
| tecnored (Magento) | 100 % (~16 s) | n/d (REST 401) | A1/A2 |
| rhona (legacy) | 100 % (~3 s) | n/d (sin API) | A1 CSS |
| sonepar (SPA) | 0 % (shell sin auth) | **100 %** (OAuth2 + `products/client/details`) | A3 API |

**Hallazgo clave P3**: el browser (A3) **no mejora la exactitud** frente a los métodos deterministas
en estos 5 sitios — solo añade latencia (9,4 s promedio vs 2,6 ms). La API solo es necesaria para
sonepar (SPA restringida). Evidencia: `data/evidence_p3.json`, `data/evidence_p3_apis.json`,
`data/evidence_summary.json`.

## Resultado P4 (LLM + verifier)

- **A4 (Gemini flash-lite)**: 19/20 = **95 %** sobre los sitios no-Sonepar (mismo que el mejor
  determinista); en Sonepar devuelve `null` correctamente (no alucina precio). Latencia ~11,5 s/ítem
  y ~1,23 M tokens.
- **A5 (verifier)**: **no añadió exactitud** (19/25 = 19/25). Confirmó el único error real
  (vitelenergia #4 multi-variante) en vez de corregirlo.
- **429 quota**: 4 llamadas tocaron el límite de la capa gratuita de Gemini (retry con delay las
  recuperó). Hallazgo operativo: el LLM introduce límites de cuota y latencia.
- Modelo usado: `gemini-flash-lite-latest` (`gemini-flash-latest` estaba saturado con 503).

Evidencia: `data/evidence_p4.json`. Matriz consolidada: `data/evidence_summary.json`.
