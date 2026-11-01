# Price Extractor — Spike Investigation Plan

From requirements with uncertainty signals to an Architectural Decision Record (ADR), applied to a
price-extraction system that must read product prices from five real Chilean e-commerce sites, each
with a different technical pattern.

This plan follows the chain required by `Guia_Spike_ADR.pdf`:

```
Requirement → Driver → Signal → Uncertainty → Question → Spike → Evidence
            → Admissibility → Sufficiency/Credibility → MCDA → Decision → ADR
```

---

## 1. Context and goal

University research project about **different ways to set up a price listing**, from classic crawlers
to agentic functions that verify the extracted data. The teacher provided a working multi-agent
scaffold ([`agenticExample`](./agenticExample) → `devspeed-live`) that already solves the hard part of
the agentic cycle: **Google ADK** agents, **MCP** microservices, deterministic **guardrails**, and a
**coordinator/dispatcher + sequential pipeline** pattern. Our job is to reuse that pattern and produce
*evidence* to justify an architectural decision for the extraction strategy.

Goal of this spike: determine, with measurable evidence, which extraction method (or hybrid) is the
best fit per site pattern, and whether an **agentic verifier loop** is worth its cost.

---

## 2. Inputs and assets

| Asset | Role |
| --- | --- |
| `Guia_Spike_ADR.pdf` | Methodology: Requirements → ADR (20 steps). |
| `agenticExample/devspeed-live*` | Reusable agent scaffold (ADK + MCP + guardrails). |
| 5 target sites | Real test cases covering distinct patterns. |

---

## 3. Site pattern matrix (preliminary fingerprint)

Fingerprints come from a light, non-invasive probe (homepage HTML + `robots.txt` only). They must be
confirmed per-product in Phase 1 before being used as evidence.

| Site | Detected platform | Pattern | Likely extraction strategy | Notes / uncertainty |
| --- | --- | --- | --- | --- |
| [dartel.cl](https://www.dartel.cl/) | VTEX | Headless commerce, JSON-LD present, public catalog/search JSON API | Structured data (JSON-LD) + VTEX search API | 2.1 MB homepage, heavy JS; API endpoints to discover |
| [vitelenergia.com](https://vitelenergia.com/) | Magento 2 | Server-rendered + JSON-LD + REST/GraphQL API | JSON-LD + Magento REST/GraphQL | `pub/static` paths confirm Magento; API availability to confirm |
| [rhona.cl](https://rhona.cl/) | MIPLUS CMS (legacy) | Classic server-rendered HTML, jQuery, no modern framework, reCAPTCHA present | Classic crawler (CSS selectors) | No structured data found; hardest for generic parsers |
| [tiendatecnored.cl](https://www.tiendatecnored.cl/) | Magento (version TBD) | Server-rendered; M1-style paths in robots | Crawler + Magento API | 103 Magento markers; M1 vs M2 to confirm |
| [shop.sonepar.cl](https://shop.sonepar.cl/) | Custom SPA "Checkbuy" | Shell HTML (~9 KB) + internal JSON API | Internal API + headless browser | Restricted: likely needs session/auth for prices; ToS review required |

This matrix is the empirical backbone of the study: **one method cannot cover all patterns**, which is
exactly what the spike must quantify.

---

## 4. Requirements (R)

| ID | Type | Requirement | Architectural concern |
| --- | --- | --- | --- |
| R1 | Functional | Extract product **name, price, currency, unit of measure, availability, and timestamp** from a product URL | Data model, extraction pipeline |
| R2 | Functional | Support at least **3 distinct platform patterns** (legacy HTML, structured data, SPA/JSON API) | Adaptability, abstraction layers |
| R3 | Functional | **Verify** each extraction and emit a confidence/status (`ok`, `warning`, `rejected`) | Verification layer, agent design |
| R4 | Quality | **Exact-price accuracy ≥ 95 %** against a hand-labeled gold set | Correctness of extraction |
| R5 | Quality | **Coverage ≥ 80 %** of sampled URLs produce a price | Robustness, fallbacks |
| R6 | Quality | **p95 latency ≤ 15 s** per product extraction | Performance, sync vs async |
| R7 | Constraint | **Cost** per extraction bounded (target: ≤ USD 0.005 for LLM methods; ~0 for deterministic) | Cost/resource usage |
| R8 | Constraint | Respect `robots.txt` and site ToS; polite rate limiting (≥ 1.5 s between same-host requests); no CAPTCHA bypass | Legal/compliance |
| R9 | Constraint | No secrets in code; API keys via environment variables only | Security, secret management |
| R10 | Constraint | Every result must be **reproducible and traceable** (URL → method → raw evidence → output) | Observability, evidence quality |

---

## 5. Architectural drivers (Driver Cards)

**D1 — Extraction correctness**

- Concern: Accuracy.
- Stimulus: a heterogeneous set of product pages across 5 platforms.
- Environment: nightly or on-demand extraction over the public internet.
- Expected response: return the correct price and metadata with a verifiable confidence level.
- Measure: exact-price accuracy ≥ 95 % on gold set; false-accept rate low.
- Constraint: must not require CAPTCHA bypass or ToS violations.

**D2 — Coverage across patterns**

- Concern: Adaptability / Integrability.
- Stimulus: new sites with unknown markup or API shape.
- Environment: research project, 5 initial sites, likely more later.
- Expected response: each pattern is handled by at least one admissible method.
- Measure: coverage ≥ 80 %; number of patterns supported ≥ 3.
- Constraint: one codebase, configurable per site.

**D3 — Cost and latency**

- Concern: Cost / Resource Usage.
- Stimulus: LLM calls scale linearly with pages; browser rendering is slow.
- Environment: university budget (limited API quota).
- Expected response: minimize LLM/browser usage where deterministic methods suffice.
- Measure: cost ≤ USD 0.005/page (LLM paths); p95 ≤ 15 s.
- Constraint: deterministic methods preferred when accuracy is equal.

**D4 — Compliance and reproducibility**

- Concern: Security / Legal / Observability.
- Stimulus: public e-commerce sites with ToS and anti-bot measures.
- Environment: academic research.
- Expected response: never bypass protection; every result auditable.
- Measure: 100 % of extractions traceable; zero robots/ToS violations.
- Constraint: allow-listed domains only; keys via env.

---

## 6. Architectural signals (S)

| ID | Signal | Observable evidence | Implicit assumption | Needs evidence? |
| --- | --- | --- | --- | --- |
| S1 | Price appears in multiple representations (JSON-LD, meta tags, visible text) but consistency is unknown | dartel/vitelenergia/sonepar emit JSON-LD; visible price may differ | All representations agree | Yes |
| S2 | Some sites render prices only via JS or an internal API | sonepar homepage is a 9 KB SPA shell; dartel is 2.1 MB of JS | Classic crawling will work on all sites | Yes |
| S3 | One site (rhona) has no structured data and is a legacy CMS | no `application/ld+json`; MIPLUS CMS; jQuery + reCAPTCHA | Generic/LLM methods will handle it | Yes |
| S4 | LLM extraction and agentic verification have unvalidated cost/latency for this dataset | no measurements exist yet | The added accuracy justifies the cost | Yes |
| S5 | The scaffold's pipeline is built for a fixed 3-service flow, not for per-site extraction routing | devspeed-live routes by *intent* (order vs delivery), not by *site* | The pattern transfers directly | Yes |

---

## 7. Uncertainties (U)

**U1.** There is no evidence yet on which extraction method reaches ≥ 95 % accuracy for each site
pattern, nor at what cost.

- Known: the 5 sites, their platforms, the scaffold.
- Assumed: structured data + deterministic fallback is enough for VTEX/Magento; LLM is only needed for
  rhona and sonepar.
- Unknown: real accuracy/cost/latency per method; API availability on Magento/VTEX; auth needs on
  sonepar.
- Decision affected: extraction method per site; whether an agentic verifier is justified.

**U2.** It is unknown whether the agentic verifier loop (extract → deterministic guards → verifier
agent) reduces errors enough to justify its added cost and latency over deterministic checks alone.

- Decision affected: whether to include a verifier agent in the final architecture.

**U3.** It is unknown how to cleanly map the scaffold's roles to per-site extraction while preserving
its guardrail and minimum-privilege guarantees.

- Decision affected: agent topology (per-site agents vs. one generic agent + config).

---

## 8. Experimental questions (Q) and hypotheses

**Q1.** For each of the five sites, which extraction method reaches **exact-price accuracy ≥ 95 %**
with the **lowest cost**, while respecting robots/ToS?

**Q2.** Does an **agentic verifier** reduce the error rate of the best deterministic pipeline by a
meaningful margin (target: ≥ 50 % error reduction) at an acceptable added cost?

Working hypotheses:

- **H1** (Q1): VTEX and Magento sites are solved by structured-data extraction (JSON-LD/API) with a
  deterministic fallback; rhona requires CSS selectors; sonepar requires the internal API or a browser.
- **H2** (Q2): the agentic verifier catches layout/markup drift that deterministic checks miss, but is
  cost-justified only on the SPA/legacy sites.
- **H0** (nulls): the chosen method does **not** meet the threshold, or the verifier does **not** add
  value.

---

## 9. Spike design (Spike Card)

| Field | Value |
| --- | --- |
| Spike ID | **SP1** |
| Uncertainty | U1, U2, U3 |
| Questions | Q1, Q2 |
| Type | Prototyping + comparison + validation |
| Alternatives | A1–A5 (below) |
| Variables | site, method, product URL, prompt, verifier on/off |
| Metrics | exact-price accuracy, coverage, latency (p50/p95), cost per page, error-reduction by verifier |
| Thresholds | accuracy ≥ 95 %, coverage ≥ 80 %, p95 ≤ 15 s, cost ≤ USD 0.005 (LLM paths) |
| Artifacts | gold set, scraper code, logs, raw captures, measurement notebook, evidence cards |
| Time-box | 4 sessions (see phases) |
| Closure criterion | comparable evidence for all alternatives on all 5 sites + coverage of critical criteria |

### Alternatives (A1–A5)

| Alt | Description | Expected benefit | Expected risk |
| --- | --- | --- | --- |
| **A1** | Classic crawler: `httpx` + `selectolax`/CSS selectors | Fast, free, deterministic | Breaks on markup change; fails on SPAs |
| **A2** | Structured data: parse JSON-LD / microdata / Open Graph | Free, typed, no selectors | Missing or stale on some sites |
| **A3** | Headless browser: Playwright renders JS, then extract | Handles SPA + JS prices | Slow, heavy, fragile selectors |
| **A4** | LLM extraction: feed HTML → LLM returns JSON (schema) | Resilient to markup drift | Cost, latency, hallucination |
| **A5** | Agentic extraction + verifier: reuse devspeed-live (MCP tools + guardrails + verifier gate) | Self-checking, auditable, minimum privilege | Most complex; highest cost |

The likely winning design is a **hybrid**: deterministic first (A1/A2/A3 by site), LLM fallback (A4),
agentic verifier (A5) as a gate — but the spike must *prove* it, not assume it.

---

## 10. Architecture adaptation (devspeed-live → price extractor)

The scaffold's pattern transfers 1:1; only the **roles** change from orders/delivery to
extraction/verification.

```
User / trigger ──► coordinator (no tools, routes by site + task)
                     │
        ┌────────────┴───────────────┐
        ▼                            ▼
 extraction_pipeline (Sequential)   api_browser_agent (specialist for SPA/API)
   1. fetch_agent   (MCP: fetch)      MCP: render_page + query_api
   2. parse_agent   (MCP: parse)      (allow-listed per site)
   3. verify_agent  (gate, no tools)
```

| devspeed-live | price-spike equivalent | Role |
| --- | --- | --- |
| `inventory/orders/delivery` MCP servers | `scraper` MCP servers: `fetch_html`, `parse_jsonld`, `render_page`, `query_api` | Adapter facades that hide HTTP/browser/API details |
| `toolsets.py` (`tool_filter`) | per-role tool allow-lists (`fetch` only for fetcher, `parse_*` only for parser) | Minimum privilege |
| `guardrails.py` (validate args) | URL allow-list, price/currency format, cross-field consistency, rate limiter | Deterministic safety *around* the LLM |
| `guardrails.py` (`require_reservation` gate) | `verify_agent` gate: extraction is only accepted if it passes checks or the verifier approves | Pipeline gate |
| `coordinator` (routes order vs delivery) | `coordinator` (routes by site pattern: `legacy` / `structured` / `spa` / `api`) | Dispatcher |

---

## 11. Execution phases

| Phase | Goal | Output | Session |
| --- | --- | --- | --- |
| **P0 — Scaffold** | Project skeleton adapted from devspeed-live; env ready; sites config | runnable skeleton + `config/sites.json` | this one |
| **P1 — Gold set** | Pick ~5 products/site, record ground-truth price/currency/unit manually + raw HTML snapshot | `data/gold_set.json` + `data/raw/` | 1 |
| **P2 — Deterministic baseline** | Implement A1 + A2 for the 3 non-SPA sites; measure accuracy/coverage/latency | baseline numbers, evidence E1/E2 | 1 |
| **P3 — Browser + API** | Implement A3 (sonepar, dartel if needed) and try Magento/VTEX APIs (R2) | evidence E3/E4 | 1 |
| **P4 — LLM + agentic verifier** | Implement A4 fallback + A5 verifier gate using the scaffold | evidence E5/E6 | 1 |
| **P5 — Analyze → ADR** | Admissibility, sufficiency/credibility, MCDA, sensitivity, ADR | `docs/ADR-001.md`, traceability | 1 |

---

## 12. Evidence plan (Evidence Cards to be filled during execution)

Each measurement produces an Evidence Card:

| Field | Meaning |
| --- | --- |
| E-ID | `E1..En` |
| Claim | e.g., "A2 reaches 100 % accuracy on dartel (n=5)" |
| Source | instrumented run |
| Procedure | N repetitions, controlled config |
| Result | measured value |
| Variability | std-dev / min–max across runs |
| Artifact | script, log, raw JSON, commit |
| Limitations | small gold set; homepage-only fingerprint; network variance |

At minimum: **E1** A1 results, **E2** A2 results, **E3** A3 results, **E4** API results, **E5** A4
results, **E6** A5 verifier results, **E7** cost/latency table.

---

## 13. Admissibility matrix (non-compensatory constraints)

An alternative is admissible only if it satisfies **all** constraints, before any scoring:

| Condition | A1 | A2 | A3 | A4 | A5 |
| --- | --- | --- | --- | --- | --- |
| Respects robots.txt / ToS (no CAPTCHA bypass) | Yes | Yes | Yes | Yes | Yes |
| No credentials in code (env only) | Yes | Yes | Yes | Yes | Yes |
| Rate limits respected (≥ 1.5 s/site) | Yes | Yes | Yes | Yes | Yes |
| Domain allow-list enforced | Yes | Yes | Yes | Yes | Yes |
| Cost ≤ USD 0.005/page | Yes | Yes | Yes | TBD (measure) | TBD (measure) |
| p95 ≤ 15 s | Yes | Yes | TBD (measure) | TBD | TBD |

Alternatives that fail a measured threshold are **inadmissible** and excluded from MCDA.

---

## 14. Sufficiency and credibility checklist

Sufficiency (all must be Yes to close the spike):

- [ ] All 5 sites tested with at least one admissible method.
- [ ] A1–A5 each measured or explicitly ruled out with justification.
- [ ] All critical criteria measured against explicit thresholds.
- [ ] Gold set and raw captures archived and traceable.
- [ ] No remaining uncertainty that could invert the decision.

Credibility (target **High**):

- Reproducible procedure (scripts versioned), ≥ 3 repetitions per measurement, artifacts traceable,
  limitations explicit. A single one-off run is **Low** credibility and does not close the spike.

---

## 15. MCDA criteria and weights (proposal)

| Criterion | Weight | Direction | Source |
| --- | --- | --- | --- |
| Accuracy (exact price) | 0.35 | maximize | spike E1–E6 |
| Coverage | 0.20 | maximize | spike |
| Cost per page | 0.15 | minimize | measurement |
| Latency p95 | 0.10 | minimize | measurement |
| Robustness (drift resistance) | 0.10 | maximize | qualitative + repeated runs |
| Compliance / politeness | 0.10 | maximize | checklist |

Weights are a starting point; sensitivity analysis will vary them (±0.10) to check robustness.

---

## 16. Decision and ADR template

The spike ends with `docs/ADR-001.md` using the guide's MADR-inspired structure:

```
# ADR-001: Estrategia de extracción de precios
Status: Proposed / Accepted
Context and Problem Statement
Decision Drivers
Considered Options (A1..A5)
Decision Outcome
Rationale
Evidence (SP1, E1..E7)
Positive Consequences
Negative Consequences
Risks and Limitations
Revisit Conditions
```

Traceability matrix (`R → D → S → U → Q → SP → E → DEC → ADR`) to be filled in P5.

---

## 17. Open decisions (defaults chosen, can be overridden)

1. **LLM provider**: default **Gemini via Google AI Studio** (matches the teacher's scaffold,
   `GOOGLE_API_KEY`). Alternatives: OpenAI, Anthropic, or a local model — trivial to swap.
2. **Language of deliverables**: this plan and code comments in **English**; ADR can be produced in
   Spanish if the course requires it.
3. **Gold-set size**: 5 products/site (25 total) to start; expand if credibility demands it.
4. **Browser engine**: Playwright (Chromium) for A3.

---

## 18. Risks and limitations

- Fingerprints are homepage-level and preliminary; per-product behavior may differ.
- sonepar may require login for prices → could reduce coverage; ToS must be reviewed before any API use.
- Small gold set limits statistical power; treat accuracy as indicative, report confidence intervals.
- Network/anti-bot variability may add noise → repeat runs and snapshot raw HTML.
- LLM outputs are non-deterministic → use structured output + temperature 0 + N repetitions.

---

## 19. Immediate next steps (this scaffold)

1. Create the `price-spike/` skeleton (README, config, agents, services, scripts).
2. Set up the Python venv with the teacher's dependencies.
3. Verify the skeleton runs a no-LLM smoke test.
4. Start **P1: build the gold set** by manually recording one product price per site.
