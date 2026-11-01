"""
P3: API probe — official/internal APIs for price extraction.

  * sonepar (Checkbuy): authenticated OAuth2 -> /products/client/details
  * dartel (VTEX):    public catalog search -> items[].sellers[].commertialOffer.Price
  * vitelenergia (Magento 2): public GraphQL -> price_range.minimum_price.regular_price.value

Compares each against the gold set and saves data/evidence_p3_apis.json.

Usage:
    python scripts/probe_apis.py
"""
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
sys.path.insert(0, str(ROOT / "services"))

from price_extractor.deterministic import extract_jsonld  # noqa: E402 (unused, kept for parity)
from sonepar_auth import SoneparClient  # noqa: E402

GOLD = ROOT / "data" / "gold_set.draft.json"
OUT = ROOT / "data" / "evidence_p3_apis.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "Chrome/126 Safari/537.36 price-spike/0.1")


def match(a, b):
    if a is None or b is None:
        return False
    return round(float(a)) == round(float(b))


def slug_from_url(url):
    seg = url.rstrip("/").split("/")[-1]
    if seg.endswith(".html"):
        seg = seg[:-5]
    if seg == "p":
        seg = url.rstrip("/").split("/")[-2]
    return seg


def _cached_html(it):
    html_file = ROOT / it.get("html_file", "")
    if html_file.exists():
        return html_file.read_text(encoding="utf-8", errors="replace")
    return ""


def dartel_mpn_from_html(it):
    m = re.search(r'"mpn"\s*:\s*"([^"]+)"', _cached_html(it))
    return m.group(1) if m else None


def dartel_price(client, url, it):
    # VTEX fulltext search by mpn (exact, numeric) -> commertialOffer.Price
    mpn = dartel_mpn_from_html(it)
    terms = mpn or slug_from_url(url).split("-")[0]
    r = client.get(f"https://www.dartel.cl/api/catalog_system/pub/products/search",
                   params={"_from": 0, "_to": 5, "ft": terms})
    if r.status_code not in (200, 206):
        return None, f"http {r.status_code}"
    data = r.json()
    if isinstance(data, list) and data:
        p = data[0]
        sellers = p.get("items", [{}])[0].get("sellers", []) if p.get("items") else []
        offer = sellers[0].get("commertialOffer", {}) if sellers else {}
        return offer.get("Price"), f"vtex(mpn={terms})"
    return None, "no_match"


def vitelenergia_name_from_html(it):
    html = _cached_html(it)
    m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    if not m:
        m = re.search(r"<title>(.*?)</title>", html, re.S)
    if not m:
        m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if not m:
        return None
    name = m.group(1).strip()
    name = re.sub(r"\s*-?\s*(VITEL|Vitel|Vitelesa).*$", "", name)
    # strip accents for the fulltext search
    name = ("".join(c for c in unicodedata.normalize("NFD", name)
                    if unicodedata.category(c) != "Mn"))
    return name


def vitelenergia_price(client, url, name):
    terms = (name or slug_from_url(url).replace("-", " "))[:80]
    query = ("{ products(search: \"" + terms +
             "\") { items { name url_key price_range { minimum_price { final_price { value } } } } } }")
    r = client.post("https://vitelenergia.com/graphql", json={"query": query})
    if r.status_code != 200:
        return None, f"http {r.status_code}"
    items = r.json().get("data", {}).get("products", {}).get("items", [])
    if not items:
        return None, "no_search_results"
    it = items[0]
    price = it.get("price_range", {}).get("minimum_price", {}).get("final_price", {}).get("value")
    # Magento final_price is float; display price is rounded to integer CLP.
    return (round(float(price)) if price is not None else None), "graphql_final"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    items = gold["items"]

    import os
    from dotenv import load_dotenv
    load_dotenv(ROOT / "agents" / "price_extractor" / ".env")

    rows = []
    per_site = {}

    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=30) as client:
        sonepar = SoneparClient(
            os.environ["SONEPAR_REFRESH_TOKEN"],
            os.environ["SONEPAR_CLIENT_ID"],
            os.environ["SONEPAR_USER_ID"],
            env_path=str(ROOT / "agents" / "price_extractor" / ".env"),
        )
        for it in items:
            sid = it["site"]
            per_site.setdefault(sid, {"n": 0, "cov": 0, "ok": 0, "ms": []})
            per_site[sid]["n"] += 1
            url = it["url"]
            truth = it.get("ground_truth")
            t0 = time.perf_counter()

            if sid == "sonepar":
                pid = url.split("/products/")[1].split("/")[0]
                try:
                    price = sonepar.get_product(pid).get("data", {}).get("price", {}).get("value")
                    src = "sonepar_api"
                except Exception as exc:  # noqa: BLE001
                    price, src = None, f"error {type(exc).__name__}"
            elif sid == "dartel":
                price, src = dartel_price(client, url, it)
            elif sid == "vitelenergia":
                price, src = vitelenergia_price(client, url, vitelenergia_name_from_html(it))
            else:
                price, src = None, "no_api_probed"  # tecnored/rhona: Magento REST 401 / no API

            ms = (time.perf_counter() - t0) * 1000
            per_site[sid]["ms"].append(ms)
            covered = price is not None
            correct = match(price, truth)
            if covered:
                per_site[sid]["cov"] += 1
            if correct:
                per_site[sid]["ok"] += 1
            rows.append({"site": sid, "index": it["index"], "url": url,
                         "extracted": price, "truth": truth, "source": src,
                         "ms": round(ms, 1), "covered": covered, "correct": correct})
            print(f"[{sid} #{it['index']}] {ms:7.0f}ms  {src:14s}  extracted={price}  truth={truth}  "
                  f"{'OK' if correct else ('MISS' if not covered else 'WRONG')}")

    summary = {}
    for sid, s in per_site.items():
        n = s["n"]
        summary[sid] = {"n": n, "coverage": s["cov"], "correct": s["ok"],
                        "accuracy": round(s["ok"] / n, 4),
                        "avg_ms": round(sum(s["ms"]) / n, 1)}

    total_n = len(rows)
    total_cov = sum(1 for r in rows if r["covered"])
    total_ok = sum(1 for r in rows if r["correct"])
    evidence = {
        "spike": "SP1",
        "phase": "P3",
        "method": "A3_api (official/internal APIs)",
        "metrics": {
            "n": total_n,
            "coverage": total_cov,
            "correct": total_ok,
            "accuracy": round(total_ok / total_n, 4),
            "avg_ms": round(sum(r["ms"] for r in rows) / total_n, 1),
        },
        "per_site": summary,
        "rows": rows,
        "notes": [
            "sonepar: authenticated guest API (products/client/details).",
            "dartel: VTEX public catalog search API (commertialOffer.Price).",
            "vitelenergia: Magento 2 GraphQL (price_range). Magento REST V1 requires auth (401).",
            "tecnored/rhona: no usable public API found (Magento REST 401; rhona has no API).",
        ],
    }
    OUT.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 80)
    for sid in summary:
        s = summary[sid]
        print(f"{sid:<14} n={s['n']}  coverage={s['coverage']}  accuracy={s['accuracy']*100:.0f}%  avg={s['avg_ms']:.0f}ms")
    print("-" * 80)
    print(f"{'TOTAL':<14} n={total_n}  coverage={total_cov}  accuracy={total_ok/total_n*100:.0f}%")
    print(f"\nEvidence -> {OUT}")


if __name__ == "__main__":
    main()
