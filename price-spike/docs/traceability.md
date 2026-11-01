# Matriz de trazabilidad — Spike SP1

Cadena completa desde requerimientos hasta la decisión arquitectónica.

```
R (Requirement) → D (Driver) → S (Signal) → U (Uncertainty) → Q (Question)
               → SP (Spike) → E (Evidence) → DEC (Decision) → ADR
```

## Requerimientos → Drivers

| Req | Tipo | Driver |
| --- | --- | --- |
| R1 (extraer precio+metadatos) | Funcional | D1 correctness |
| R4 (exactitud ≥ 95 %) | Calidad | D1 correctness |
| R5 (cobertura ≥ 80 %) | Calidad | D2 coverage |
| R2 (≥ 3 patrones) | Funcional | D2 coverage |
| R6 (p95 ≤ 15 s), R7 (costo) | Calidad/restricción | D3 cost/latency |
| R8 (robots/ToS), R9 (secretos) | Restricción | D4 compliance |
| R10 (trazabilidad) | Calidad | D4 reproducibility |

## Drivers → Señales → Incertidumbres

| Driver | Signal | Uncertainty |
| --- | --- | --- |
| D1, D2 | S1 precios en múltiples representaciones; S2 precios solo por JS/API; S3 rhona sin datos estructurados | U1 qué método alcanza ≥ 95 % por sitio |
| D1, D3 | S4 costo/latencia LLM no validados | U2 ¿el verifier agéntico reduce errores lo suficiente? |
| D2, D4 | S5 el scaffold rutea por intención, no por sitio | U3 mapeo de roles al patrón por-sitio |

## Preguntas → Spike → Evidencia

| Q | Spike | Evidence | Resultado |
| --- | --- | --- | --- |
| Q1 ¿qué método por sitio alcanza ≥ 95 % al menor costo? | SP1 | E1, E2, E3, E4, E5 | Determinista 19/20 (95 % no-sonepar); sonepar solo API; browser/LLM no añaden |
| Q2 ¿el verifier reduce errores de forma justificable? | SP1 | E6 | error_reduction = 0 → no justificado |
| U3 mapeo de roles | SP1 | E1–E7 | routing por patrón de sitio + guardrails deterministas |

## Evidencia → Decisión → ADR

| Evidence | Archivo | Método |
| --- | --- | --- |
| E1 | `data/evidence_p2.json` | A1 CSS |
| E2 | `data/evidence_p2.json` | A2 estructurado |
| E3 | `data/evidence_p3.json` | A3 browser |
| E4 | `data/evidence_p3_apis.json` | A3 API |
| E5 | `data/evidence_p4.json` | A4 LLM |
| E6 | `data/evidence_p4.json` | A5 verifier |
| E7 | `data/evidence_summary.json`, `data/evidence_mcda.json` | matriz + MCDA |

**Decisión (DEC-1):** adoptar **A6 híbrido determinista-first con routing por sitio + API
autenticada para la SPA**; LLM como fallback opcional. → **ADR-001** (`docs/ADR-001.md`).

## Regla de cierre (Close = A ∧ S ∧ C ∧ T)

| Condición | Estado |
| --- | --- |
| A — alternativas admisibles o justificadamente descartadas | ✅ A1–A6 evaluadas; A3/A4/A5 admisibles pero dominadas |
| S — evidencia suficiente (cobertura de alternativas, criterios y umbrales) | ✅ 5 sitios × 5 métodos, umbrales explícitos |
| C — evidencia creíble (reproducible, artefactos trazables) | ✅ scripts versionados, JSON de evidencia, gold set |
| T — trazabilidad pregunta→medición→decisión | ✅ esta matriz |
