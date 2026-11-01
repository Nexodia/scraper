# Price Extractor — Spike Investigation

University research project on **the different ways to set up a price listing** — from classic
crawlers to agentic functions that verify the extracted data — tested on five real Chilean
e-commerce sites with distinct technical patterns.

The investigation follows the **Spike ADR** methodology from
[`Guia_Spike_ADR.pdf`](./Guia_Spike_ADR.pdf):

```
Requirement → Driver → Signal → Uncertainty → Question → Spike → Evidence
            → Admissibility → Sufficiency/Credibility → MCDA → Decision → ADR
```

## Repository layout

| Path | What it is |
| --- | --- |
| [Guia_Spike_ADR.pdf](./Guia_Spike_ADR.pdf) | Methodology guide (Spanish) — requirements to ADR in 20 steps |
| [PLAN.md](./PLAN.md) | Full spike plan: requirements R1–R10, drivers, signals, uncertainties, alternatives A1–A5, phases P0–P5 |
| [price-spike/](./price-spike/) | The working scaffold, site config, gold set, raw snapshots, and tools |
| [price-spike/README.md](./price-spike/README.md) | Scaffold-specific details and run instructions |
| [agenticExample/](./agenticExample/) | Teacher's multi-agent reference (`Google ADK` + `MCP` + guardrails); the pattern we reuse |

## Spike progress briefing

### Phases

| Phase | Goal | Status |
| --- | --- | --- |
| P0 — Scaffold | Project skeleton adapted from the teacher's `devspeed-live` (ADK + MCP + guardrails) | ✅ done |
| P1 — Gold set | 25 product pages (5/site) snapshotted + prices labeled | 🟡 24/25 human-confirmed; Sonepar pending login |
| P2 — Deterministic baseline | A1 CSS crawler + A2 JSON-LD/meta, measured vs. gold set | ⬜ next |
| P3 — Browser + APIs | A3 Playwright + Magento/VTEX/Sonepar APIs | ⬜ |
| P4 — LLM + agentic verifier | A4 LLM fallback + A5 verifier gate (reuses the scaffold) | ⬜ |
| P5 — Analyze → ADR | Admissibility → MCDA → sensitivity → ADR-001 + traceability | ⬜ |

### Site pattern matrix (fingerprinted during P0/P1)

| Site | Platform | Pattern | Extraction strategy |
| --- | --- | --- | --- |
| dartel.cl | VTEX | Structured data + JSON API | JSON-LD (`AggregateOffer`) |
| vitelenergia.com | Magento 2 | Server-rendered + JSON-LD/meta | meta `product:price:amount` |
| rhona.cl | MIPLUS CMS (legacy) | No structured data, jQuery | CSS selectors (visible price) |
| tiendatecnored.cl | Magento | Server-rendered, no sitemap | meta `product:price:amount` |
| shop.sonepar.cl | Custom SPA (Checkbuy) | Shell HTML + internal JSON API | OAuth2 + `products/client/details` |

### Key findings so far

1. **One method cannot cover all patterns.** Each site needed a different discovery route
   (sitemap index, category crawl, homepage links, full sitemap) and a different price signal
   (JSON-LD, meta tag, visible text, authenticated API).
2. **rhona is the classic hard case**: no structured data at all; prices only in visible text
   with `.` as thousands separator.
3. **Sonepar is the restricted case**: the anonymous API returns `"price": {}`; prices are
   client-specific and require OAuth2 login. Auth is reverse-engineered
   ([`sonepar_auth.py`](./price-spike/services/sonepar_auth.py)); the one-time login is manual
   (reCAPTCHA is never automated) — see below.
4. **The gold set is the reference** for evaluating every extraction method in P2–P4. It lives in
   [`price-spike/data/gold_set.draft.json`](./price-spike/data/gold_set.draft.json) with a
   human-review table in [`price-spike/data/gold_set.review.md`](./price-spike/data/gold_set.review.md).

### Alternatives under test (from [PLAN.md](./PLAN.md))

- **A1** classic crawler (CSS/XPath) · **A2** structured data (JSON-LD/meta)
- **A3** headless browser (Playwright) · **A4** LLM extraction
- **A5** agentic extraction + verifier (reuses the teacher's coordinator + guardrails pattern)

## Quick start

```powershell
cd price-spike
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1   # creates .venv, installs deps
.\.venv\Scripts\Activate.ps1
python scripts\run_services.py   # terminal 1: MCP scraper service
python scripts\smoke_test.py     # terminal 2: no-LLM verification
```

Sonepar (one-time, requires an account):

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe scripts\sonepar_login.py   # log in manually, press Enter when done
```

## Security

- Secrets live **only** in `.env` (e.g. `GOOGLE_API_KEY`, `SONEPAR_REFRESH_TOKEN`), which is
  gitignored. Never commit it.
- The Sonepar login session dump (`data/sonepar_session.json`) is gitignored.
- Raw page snapshots (`data/raw/`) and logs are gitignored.
- No CAPTCHAs are bypassed; Sonepar login is a manual, human-in-the-loop step.
- The OAuth client id/secret in [`sonepar_auth.py`](./price-spike/services/sonepar_auth.py) are
  **public** values embedded in Sonepar's own JS bundle, not real secrets.
