"""
P4: A4 LLM extraction + A5 agentic verifier.

A4: feed cleaned HTML to Gemini (flash-lite) -> structured JSON {name, price, currency, availability}.
A5: a second LLM call verifies the A4 extraction against the HTML and can CORRECT it.

Measures accuracy (exact integer vs gold set), latency, and token usage, and evaluates
whether the verifier reduces the error rate (research question Q2).

Saves data/evidence_p4.json.

Usage:
    python scripts/run_llm.py
"""
import json
import re
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data" / "gold_set.draft.json"
OUT = ROOT / "data" / "evidence_p4.json"

MAX_HTML_CHARS = 80_000
MODEL = "gemini-flash-lite-latest"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

A4_PROMPT = (
    "Extract the product's FINAL selling price from this HTML.\n"
    "Return a JSON object with exactly these keys:\n"
    '  {"name": string, "price": integer or null, "currency": string, "availability": string or null}\n'
    "Rules:\n"
    " - price = the final price the customer pays (after discount), NOT the list/regular price.\n"
    " - Chilean peso prices are whole numbers (no decimals). Round if needed.\n"
    " - If several prices appear, pick the MAIN product's current price.\n"
    " - If no price is present, set price=null.\n"
    " - currency: ISO 4217 (default CLP).\n"
    "HTML:\n"
)

A5_PROMPT = (
    "You are a price-verification agent. Verify the candidate price against the HTML.\n"
    "Return a JSON object with exactly these keys:\n"
    '  {"verdict": string, "corrected_price": integer or null, "reason": string}\n'
    " - verdict = \"confirm\" if the candidate price is correct, else \"correct\".\n"
    " - corrected_price = the correct final price (integer) when verdict is \"correct\", else null.\n"
    " - If the HTML has no price and the candidate is null, verdict=\"confirm\", corrected_price=null.\n"
    "Candidate price: {candidate}\n"
    "HTML:\n"
)

_JSONLD_RE = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>.*?</script>", re.S | re.I)


def clean_html(html):
    """Keep JSON-LD; strip other scripts/styles/comments; collapse whitespace; truncate."""
    jsonlds = _JSONLD_RE.findall(html or "")
    h = re.sub(r"<script[^>]*>.*?</script>", " ", html or "", flags=re.S | re.I)
    h = re.sub(r"<style[^>]*>.*?</style>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<!--.*?-->", " ", h, flags=re.S)
    h = "\n".join(jsonlds) + "\n" + h
    h = re.sub(r"\s+", " ", h)
    return h[:MAX_HTML_CHARS]


def gemini_json(key, prompt, timeout=90, retries=3):
    """Call Gemini with JSON output mode. Returns (dict|None, usage_dict)."""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0},
    }
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = httpx.post(ENDPOINT, params={"key": key},
                           json=body, timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                usage = data.get("usageMetadata", {})
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    m = re.search(r"\{.*\}", text, re.S)
                    parsed = json.loads(m.group(0)) if m else None
                return parsed, usage
            if r.status_code in (429, 503, 500) and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            last_err = f"http {r.status_code}: {r.text[:120]}"
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {str(exc)[:120]}"
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
    return None, {"error": last_err}


def match(a, b):
    if a is None or b is None:
        return False
    return round(float(a)) == round(float(b))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    import os
    from dotenv import load_dotenv
    load_dotenv(ROOT / "agents" / "price_extractor" / ".env")
    key = os.environ["GOOGLE_API_KEY"]

    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    items = gold["items"]

    rows = []
    per_site = {}
    total_prompt_tokens = total_cand_tokens = 0
    total_ms = 0.0

    for it in items:
        sid = it["site"]
        per_site.setdefault(sid, {"n": 0, "A4": {"cov": 0, "ok": 0},
                                  "A5": {"cov": 0, "ok": 0}})
        per_site[sid]["n"] += 1
        truth = it.get("ground_truth")

        html_file = it.get("html_file")
        raw_html = ""
        if html_file:
            p = ROOT / html_file
            if p.exists():
                raw_html = p.read_text(encoding="utf-8", errors="replace")
        cleaned = clean_html(raw_html)

        # ---- A4: LLM extraction
        t0 = time.time()
        a4, usage4 = gemini_json(key, A4_PROMPT + cleaned)
        ms4 = (time.time() - t0) * 1000
        total_ms += ms4
        pt = (usage4 or {}).get("promptTokenCount", 0)
        ct = (usage4 or {}).get("candidatesTokenCount", 0)
        total_prompt_tokens += pt
        total_cand_tokens += ct

        a4_price = None
        if isinstance(a4, dict):
            raw_price = a4.get("price")
            if raw_price is not None:
                try:
                    a4_price = round(float(raw_price))
                except (TypeError, ValueError):
                    a4_price = None

        # ---- A5: verifier (verify the A4 candidate against the HTML)
        t0 = time.time()
        cand = a4_price if a4_price is not None else None
        a5, usage5 = gemini_json(key, A5_PROMPT.replace("{candidate}", str(cand)) + cleaned)
        ms5 = (time.time() - t0) * 1000
        total_ms += ms5
        total_prompt_tokens += (usage5 or {}).get("promptTokenCount", 0)
        total_cand_tokens += (usage5 or {}).get("candidatesTokenCount", 0)

        corrected = None
        if isinstance(a5, dict) and a5.get("verdict") == "correct":
            cp = a5.get("corrected_price")
            if cp is not None:
                try:
                    corrected = round(float(cp))
                except (TypeError, ValueError):
                    corrected = None
        final_after_verify = corrected if corrected is not None else a4_price

        # ---- accounting
        if a4_price is not None:
            per_site[sid]["A4"]["cov"] += 1
            if match(a4_price, truth):
                per_site[sid]["A4"]["ok"] += 1
        if final_after_verify is not None:
            per_site[sid]["A5"]["cov"] += 1
            if match(final_after_verify, truth):
                per_site[sid]["A5"]["ok"] += 1

        rows.append({
            "site": sid, "index": it["index"], "url": it["url"],
            "truth": truth,
            "A4_price": a4_price,
            "A4_correct": match(a4_price, truth),
            "A5_verdict": (a5 or {}).get("verdict") if isinstance(a5, dict) else None,
            "A5_corrected": corrected,
            "final_after_verify": final_after_verify,
            "A5_correct": match(final_after_verify, truth),
            "A4_ms": round(ms4, 1),
            "A5_ms": round(ms5, 1),
            "A4_prompt_tokens": pt,
            "A4_cand_tokens": ct,
            "A4_llm_name": (a4 or {}).get("name") if isinstance(a4, dict) else None,
            "A4_currency": (a4 or {}).get("currency") if isinstance(a4, dict) else None,
            "error": (usage4 or {}).get("error"),
        })
        flag = "OK " if match(a4_price, truth) else ("MISS" if a4_price is None else "WRNG")
        print(f"[{sid} #{it['index']}] A4={a4_price} {flag}  A5={ (a5 or {}).get('verdict') if isinstance(a5,dict) else 'err' } "
              f"final={final_after_verify}  ({ms4:.0f}ms+{ms5:.0f}ms, {pt}/{ct} tok)")

    n = len(rows)
    def stats(mode):
        cov = sum(1 for r in rows if r[f"{mode}_price" if mode=="A4" else "final_after_verify"] is not None)
        # A5 coverage/correct use final_after_verify
        if mode == "A4":
            ok = sum(1 for r in rows if r["A4_correct"])
        else:
            ok = sum(1 for r in rows if r["A5_correct"])
        return cov, ok

    a4_cov, a4_ok = stats("A4")
    a5_cov, a5_ok = stats("A5")

    evidence = {
        "spike": "SP1",
        "phase": "P4",
        "model": MODEL,
        "methods": ["A4_llm", "A5_verifier"],
        "metrics": {
            "n": n,
            "A4": {"coverage": a4_cov, "correct": a4_ok, "accuracy": round(a4_ok / n, 4)},
            "A5_after_verify": {"coverage": a5_cov, "correct": a5_ok, "accuracy": round(a5_ok / n, 4)},
            "error_reduction": round(a5_ok - a4_ok, 4),  # how many errors the verifier fixed
            "avg_ms_per_item": round(total_ms / n, 1),
            "total_prompt_tokens": total_prompt_tokens,
            "total_candidates_tokens": total_cand_tokens,
        },
        "per_site": {sid: {
            "n": v["n"],
            "A4": {"coverage": v["A4"]["cov"], "correct": v["A4"]["ok"]},
            "A5": {"coverage": v["A5"]["cov"], "correct": v["A5"]["ok"]},
        } for sid, v in per_site.items()},
        "rows": rows,
        "notes": [
            "A4 = Gemini flash-lite extracts price from cleaned HTML (JSON-LD kept, scripts/styles stripped).",
            "A5 = verifier LLM call on the A4 output; can confirm or correct.",
            "flash-latest was 503/timeout at runtime -> used flash-lite-latest (cheaper, available).",
        ],
    }
    OUT.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 70)
    for sid in per_site:
        v = per_site[sid]
        nv = v["n"]
        print(f"{sid:<14} A4 {v['A4']['cov']}/{nv} cov  {v['A4']['ok']/nv*100:3.0f}% acc  |  "
              f"A5 {v['A5']['cov']}/{nv} cov  {v['A5']['ok']/nv*100:3.0f}% acc")
    print("-" * 70)
    print(f"{'TOTAL':<14} A4 {a4_ok}/{n} = {a4_ok/n*100:.0f}%  |  A5 {a5_ok}/{n} = {a5_ok/n*100:.0f}%  "
          f"(verifier fixed {a5_ok - a4_ok} errors)")
    print(f"tokens: prompt={total_prompt_tokens} candidates={total_cand_tokens}  avg {total_ms/n:.0f}ms/item")
    print(f"\nEvidence -> {OUT}")


if __name__ == "__main__":
    main()
