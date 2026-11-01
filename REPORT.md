# Informe final — Spike de extracción de precios

Proyecto de investigación: distintas formas de montar un listado de precios, desde crawlers
clásicos hasta funciones agénticas que los verifican.

Metodología seguida: [`Guia_Spike_ADR.pdf`](./Guia_Spike_ADR.pdf)
(`Requirement → Driver → Signal → Uncertainty → Question → Spike → Evidence → Admissibility →
Sufficiency/Credibility → MCDA → Decision → ADR`).

Fecha: 2026-11-01 · Spike ID: **SP1** · Decisión: **ADR-001**

---

## 1. Resumen ejecutivo

Se evaluaron **5 métodos de extracción** (A1–A5) más un **híbrido emergente (A6)** sobre **5 sitios
reales** con patrones técnicos distintos, usando un **gold set de 25 productos**.

**Decisión:** adoptar una arquitectura **híbrida determinista-first con routing por sitio** —
JSON-LD/meta/CSS según el patrón, y una **API autenticada** para la SPA restringida (Sonepar). El
LLM queda como *fallback* opcional; el browser y el verifier agéntico **no** entran en el camino por
defecto.

**Hallazgo central:** en este dataset, los métodos deterministas alcanzan el umbral de exactitud
(≥ 95 % sobre cubiertos) a costo y latencia casi nulos; el browser y el LLM **empatan sin superar**;
y el **verifier agéntico añadió cero exactitud** (confirmó el único error real en vez de corregirlo).
Solo la SPA restringida justifica un camino especial (API autenticada).

Puntaje MCDA del híbrido: **94,55** (siguiente: A4 LLM 76,60). La decisión es **estable** ante
variaciones de ±0,10 en cualquier peso.

---

## 2. Contexto y sitios

| Sitio | Plataforma | Patrón | Señal de precio |
| --- | --- | --- | --- |
| dartel.cl | VTEX | datos estructurados + API catálogo | JSON-LD `AggregateOffer` / API search |
| vitelenergia.com | Magento 2 (Hyva) | server-rendered + meta + GraphQL | meta `product:price:amount` |
| rhona.cl | MIPLUS CMS (legacy) | solo HTML visible | texto visible `$ x.xxx` |
| tiendatecnored.cl | Magento | server-rendered + meta | meta `product:price:amount` / `data-price-amount` |
| shop.sonepar.cl | SPA propia (Checkbuy) | shell + API JSON interna | API `products/client/details` (auth) |

---

## 3. Requerimientos (R)

| ID | Tipo | Requerimiento |
| --- | --- | --- |
| R1 | Funcional | Extraer nombre, precio, moneda, unidad, disponibilidad y timestamp de una URL de producto |
| R2 | Funcional | Soportar ≥ 3 patrones técnicos distintos |
| R3 | Funcional | Verificar cada extracción y emitir estado/confianza |
| R4 | Calidad | Exactitud de precio ≥ 95 % contra gold set |
| R5 | Calidad | Cobertura ≥ 80 % |
| R6 | Calidad | p95 ≤ 15 s por producto |
| R7 | Restricción | Costo acotado (LLM ≤ USD 0,005/página; determinista ≈ 0) |
| R8 | Restricción | Respetar robots.txt/ToS; sin bypass de CAPTCHA |
| R9 | Restricción | Secretos solo en variables de entorno |
| R10 | Restricción | Resultados reproducibles y trazables |

---

## 4. Drivers, señales e incertidumbres

**Drivers:** D1 exactitud · D2 cobertura entre patrones · D3 costo/latencia · D4 cumplimiento y
reproducibilidad.

**Señales:** S1 precios en múltiples representaciones (JSON-LD, meta, texto) · S2 precios solo por
JS/API (SPA) · S3 rhona sin datos estructurados · S4 costo/latencia LLM no validados · S5 el scaffold
rutea por intención, no por sitio.

**Incertidumbres:** U1 qué método alcanza ≥ 95 % por sitio · U2 si el verifier agéntico justifica su
costo · U3 cómo mapear el scaffold a un routing por sitio.

**Preguntas experimentales:** Q1 ¿qué método por sitio alcanza ≥ 95 % al menor costo? · Q2 ¿el
verifier reduce errores de forma justificable?

**Hipótesis:** H1 — VTEX/Magento se resuelven con datos estructurados; rhona con CSS; sonepar con
API/browser. H2 — el verifier detecta deriva que el determinista no ve, pero solo se justifica en
SPA/legacy. *(H2 fue refutada por la evidencia.)*

---

## 5. Gold set (P1)

25 productos (5/sitio) con precio de referencia confirmado. Fuentes del ground truth: JSON-LD
(dartel), meta (vitelenergia/tecnored), texto visible (rhona, revisado a mano) y **API autenticada**
(sonepar). Un producto multi-variante (vitelenergia #4) requirió revisión humana.

- `data/gold_set.draft.json` — gold set + trazas por ítem.
- `data/gold_set.review.md` — tabla de revisión.
- `data/raw/` — capturas HTML (no versionadas, ~25 MB).

---

## 6. Evidencia por método

### P2 — Determinista (A1 CSS, A2 estructurado)

| Sitio | A1 CSS | A2 estructurado |
| --- | --- | --- |
| dartel (VTEX) | 0 % | **100 %** (JSON-LD) |
| vitelenergia (Hyva) | 40 % | **80 %** (meta) |
| tecnored (Magento) | **100 %** | **100 %** |
| rhona (legacy) | **100 %** | 0 % |
| sonepar (SPA) | 0 % | 0 % |

Mejor determinista: cobertura 20/25, **19/20 exactos (95 %)**. Evidencia: `data/evidence_p2.json`.

### P3 — Browser (A3) y APIs

| Sitio | A3 browser | A3 API |
| --- | --- | --- |
| dartel | 100 % (~11,6 s) | **100 %** (VTEX search por mpn) |
| vitelenergia | 80 % (~14 s) | 60 % (GraphQL, variantes ambiguas) |
| tecnored | 100 % (~16 s) | n/d (REST 401) |
| rhona | 100 % (~3 s) | n/d (sin API) |
| sonepar | 0 % (shell sin auth) | **100 %** (OAuth2 guest) |

**Hallazgo:** el browser no mejora la exactitud (9,4 s vs 2,6 ms). La API solo es imprescindible en
sonepar. Evidencia: `data/evidence_p3.json`, `data/evidence_p3_apis.json`.

### P4 — LLM (A4) y verifier agéntico (A5)

Modelo: `gemini-flash-lite-latest` (`flash-latest` estaba saturado con 503).

| Sitio | A4 LLM | A5 verifier |
| --- | --- | --- |
| dartel | 5/5 | 5/5 |
| vitelenergia | 4/5 | 4/5 |
| tecnored | 5/5 | 5/5 |
| rhona | 5/5 | 5/5 |
| sonepar | 0/5 (devuelve null correctamente) | 0/5 |

A4 = **19/20 (95 %) sobre no-sonepar** (empata con el determinista). A5 **añadió 0 exactitud**:
confirmó el único error real (vitelenergia #4). Latencia ~11,5 s/ítem, ~1,23 M tokens, y un episodio
de **429 quota** (recuperado con retry). Evidencia: `data/evidence_p4.json`.

---

## 7. Matriz consolidada

| Sitio | A1 | A2 | A3 browser | A3 API | A4 LLM | Recomendado |
| --- | --- | --- | --- | --- | --- | --- |
| dartel | 0 % | **100 %** | 100 % | 100 % | 100 % | A2 (JSON-LD) |
| vitelenergia | 40 % | **80 %** | 80 % | 60 % | 80 % | A2 (meta) |
| tecnored | **100 %** | 100 % | 100 % | — | 100 % | A1/A2 |
| rhona | **100 %** | 0 % | 100 % | — | 100 % | A1 (CSS) |
| sonepar | 0 % | 0 % | 0 % | **100 %** | 0 % | A3 API |

`data/evidence_summary.json`.

---

## 8. Admisibilidad, suficiencia y credibilidad

**Admisibilidad** (restricciones no compensatorias): todas las alternativas respetan robots/ToS,
sin bypass de CAPTCHA, secretos solo en `.env`, rate-limit y allow-list. A4/A5 superan el umbral de
costo solo como *fallback*. Ninguna alternativa fue descartada por inadmisible.

**Suficiencia:** 5 sitios × 5 métodos evaluados contra umbrales explícitos; gold set y artefactos
trazables; no queda incertidumbre crítica que invierta la decisión. ✅

**Credibilidad:** procedimientos reproducibles (scripts versionados), múltiples ejecuciones (P4 con
retry), artefactos trazables y limitaciones explícitas. Nivel: **Alta** para la decisión principal;
**Media** en robustez ante deriva (no simulada).

---

## 9. MCDA y análisis de sensibilidad

Criterios y pesos: exactitud 0,35 · cobertura 0,20 · costo 0,15 · latencia 0,10 · robustez 0,10 ·
cumplimiento 0,10.

| Alternativa | Puntaje |
| --- | --- |
| **A6 híbrido** | **94,55** |
| A4 LLM | 76,60 |
| A3 browser | 74,10 |
| A2 estructurado | 71,60 |
| A5 verifier | 70,60 |
| A1 CSS | 66,80 |

**Sensibilidad:** variando cada peso ±0,10, la decisión **nunca cambia** (A6 siempre primero).
Cálculo reproducible en `data/evidence_mcda.json` (`scripts/run_mcda.py`).

---

## 10. Decisión (DEC-1)

Adoptar **A6**: híbrido determinista-first con routing por patrón de sitio.

```
URL ──► clasificador por patrón ──► VTEX      -> JSON-LD / API catálogo
                                   Magento   -> meta price:amount (+ GraphQL opc.)
                                   Legacy    -> selector CSS visible
                                   SPA (auth)-> API autenticada products/client/details
                                   (fallback)-> LLM solo si el determinista falla
```

Guardrails deterministas alrededor (allow-list de dominios, formato de precio, consistencia entre
campos) — reutilizados del scaffold del profesor (`devspeed-live`: ADK + MCP + guardrails).

Documento formal: [`price-spike/docs/ADR-001.md`](./price-spike/docs/ADR-001.md).

---

## 11. Trazabilidad

| Req | Driver | Signal | Unc. | Q | Spike | Evidencia | Decisión |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1, R4 | D1 | S1–S3 | U1 | Q1 | SP1 | E1–E5 | ADR-001 |
| R5, R2 | D2 | S1–S3 | U1 | Q1 | SP1 | E1–E5 | ADR-001 |
| R6, R7 | D3 | S4 | U1, U2 | Q1, Q2 | SP1 | E3–E7 | ADR-001 |
| R8, R9 | D4 | — | — | — | — | checklist | ADR-001 |
| R3 | D1 | S4 | U2 | Q2 | SP1 | E6 | ADR-001 |

Matriz completa en [`price-spike/docs/traceability.md`](./price-spike/docs/traceability.md).

---

## 12. Modelo de costo (y la pregunta DeepSeek)

El LLM quedó como **fallback**, así que su costo deja de ser crítico en el camino por defecto. Para
el fallback conviene el **modelo más barato que mantenga la exactitud**: `flash-lite` (usado) o un
modelo externo tipo DeepSeek/Flash. El scaffold lee el modelo desde una sola variable
(`GEMINI_MODEL`), por lo que cambiar de proveedor es trivial. Costo medido en P4: ~1,23 M tokens de
entrada para 25 páginas (~USD 0,09 con flash-lite; menor aún con proveedores más baratos).

---

## 13. Limitaciones

- Gold set pequeño (25 productos): exactitud indicativa, con la salvedad del n pequeño.
- La robustez ante deriva de markup no se simuló (se estimó cualitativamente).
- Precios de sonepar dependen del cliente/ubicación del guest login.
- La ambigüedad multi-variante (vitelenergia #4) es un problema de datos, no de método.

---

## 14. Conclusión

El spike transformó una incertidumbre ("¿qué método de extracción usar?") en una decisión defendible
por evidencia: **el determinista gana donde hay datos estructurados; el agéntico/LLM/browser no
aportan exactitud en este dataset; y la SPA restringida es el único caso que justifica un camino
especial (API autenticada)**. El ADR es el último artefacto de una cadena trazable
Requirement → Evidence → Decision → ADR.
