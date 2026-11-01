"""
P1: build the gold set.

For each curated product URL:
  1. fetch the HTML politely (>= 1.5 s between same-host requests),
  2. save the raw HTML to data/raw/<site>/<nn>_<slug>.html plus a .meta.json,
  3. extract candidate price signals (JSON-LD, Open Graph/meta, visible regex),
  4. append to data/gold_set.draft.json with `ground_truth` left for human review.

Usage:
    python scripts/build_gold_set.py
"""
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "gold_set.draft.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "price-spike/0.1 (university research; polite, rate-limited)"
)

# Curated product URLs (5 per site), selected from sitemaps/category pages.
SELECTED = {
    "dartel": [
        "https://www.dartel.cl/curva-tubo-libre-de-halogenos-20mm-libre-de-halogenos-ip40---gewiss-40120103-gewiss/p",
        "https://www.dartel.cl/piloto-led-plast-22mm-ro-24vac-dc--b-torn-2452661-siemens/p",
        "https://www.dartel.cl/fusible-10x38-25a-gg-fx-2520-2502034-fnx/p",
        "https://www.dartel.cl/rollo-cable-2-5mm-100mts-azul-libre-de-halogenos-35200271-nexans---cocesa/p",
        "https://www.dartel.cl/caja-moldeada-sin-regulacion-drx-250n---25ka-415v-250a-2711704-legrand/p",
    ],
    "vitelenergia": [
        "https://vitelenergia.com/es/cable-eco-revi-l-h-1-5mm-h07z1-k-lineal-2.html",
        "https://vitelenergia.com/es/cable-eco-revi-l-h-2-5mm-h07z1-k-lineal-2.html",
        "https://vitelenergia.com/es/cable-eva-1-5mm2-libre-de-halogeno-h07z1-k-x-metros.html",
        "https://vitelenergia.com/es/cable-libre-de-halogeno-1-5mm-h07z1-k-x-rollo-100-mts-2.html",
        "https://vitelenergia.com/es/cable-libre-de-halogeno-2-5mm2-h07z1-k-x-rollo-10-mts.html",
    ],
    "tecnored": [
        "https://www.tiendatecnored.cl/bandeja-canaleta-pvc-100x50mm-2-metros-con-varillas-blanco.html",
        "https://www.tiendatecnored.cl/cable-preensamblado-1x16-1x16mm2-neutro-desnudo-elexor.html",
        "https://www.tiendatecnored.cl/cable-solar-10mm2-negro-elexor.html",
        "https://www.tiendatecnored.cl/canaleta-pvc-14x7mm-x-2-metros-blanco-con-adhesivo-economico.html",
        "https://www.tiendatecnored.cl/cond-fotovol-h1z2z2-k-4mm2-rojo-elexor.html",
    ],
    "rhona": [
        "https://rhona.cl/producto/10332/panel-solar-monocristalino-azul.html",
        "https://rhona.cl/producto/10587/panel-solar-monocristalino.html",
        "https://rhona.cl/producto/11293/panel-solar-monocristalino.html",
        "https://rhona.cl/producto/12095/panel-solar-bifacial-620wp.html",
        "https://rhona.cl/producto/10335/inversor-monofasico.html",
    ],
    "sonepar": [
        "https://shop.sonepar.cl/products/1000017/TI66942/ACCESORIO_CAJA_DISTRIBUCI%C3%93N_REDONDA_3_MOD_SENSOR_WATT_STOPPER_355",
        "https://shop.sonepar.cl/products/1000099/SCH10125/GUARDAMOTOR_TRIPOLAR_1%2C6-2%2C5A_100KA_EASYPACT_TVS",
        "https://shop.sonepar.cl/products/1000109/TE92580/GUARDAMOTOR_3P_24-32A_35KA_TESYS_GV2P32",
        "https://shop.sonepar.cl/products/1000113/SS66144/GUARDAMOTOR_TRIPOLAR_1%2C8-2%2C5A_100KA_S00",
        "https://shop.sonepar.cl/products/1000114/TE10008/GUARDAMOTOR_TRIPOLAR_9-13A_100KA",
    ],
}

_JSONLD_RE = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S)
_META_PRICE_RE = re.compile(
    r'''<(?:meta|span)[^>]+property=["'](?:product|og):price:amount["'][^>]+content=["']([^"']+)["']''',
    re.I)
_META_CURRENCY_RE = re.compile(
    r'''<(?:meta|span)[^>]+property=["'](?:product|og):price:currency["'][^>]+content=["']([^"']+)["']''',
    re.I)


_VISIBLE_PRICE_RE = re.compile(r"\$\s*(\d{1,3}(?:\.\d{3})+|\d+)")


def slugify(url):
    path = urlparse(url).path.rstrip("/")
    name = path.rsplit("/", 1)[-1] or "index"
    return re.sub(r"[^A-Za-z0-9_-]+", "-", name)[:80]


def _offer_from_dict(o):
    """Normalize an Offer/AggregateOffer dict to one or more {price, currency, availability}."""
    if not isinstance(o, dict):
        return []
    if "offers" in o and isinstance(o["offers"], list):  # AggregateOffer
        out = []
        for inner in o["offers"]:
            if isinstance(inner, dict):
                out.append({
                    "price": inner.get("price"),
                    "currency": inner.get("priceCurrency") or o.get("priceCurrency"),
                    "availability": inner.get("availability"),
                })
        if not out and o.get("lowPrice") is not None:
            out.append({"price": o.get("lowPrice"), "currency": o.get("priceCurrency"),
                        "availability": None})
        return out
    return [{
        "price": o.get("price"),
        "currency": o.get("priceCurrency"),
        "availability": o.get("availability"),
    }]


def extract_jsonld_offers(html):
    offers = []
    for raw in _JSONLD_RE.findall(html):
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError:
            continue
        docs = doc if isinstance(doc, list) else [doc]
        for d in docs:
            if not isinstance(d, dict):
                continue
            if isinstance(d.get("offers"), (dict, list)):
                offs = d["offers"] if isinstance(d["offers"], list) else [d["offers"]]
                for o in offs:
                    for norm in _offer_from_dict(o):
                        offers.append({
                            "name": d.get("name"),
                            "price": norm["price"],
                            "currency": norm["currency"],
                            "availability": norm["availability"],
                        })
    return offers


def extract_candidates(html):
    meta_prices = _META_PRICE_RE.findall(html)
    meta_currency = _META_CURRENCY_RE.findall(html)
    visible_prices = _VISIBLE_PRICE_RE.findall(html)
    return {
        "jsonld_offers": extract_jsonld_offers(html),
        "meta_price_amount": meta_prices[:5],
        "meta_price_currency": meta_currency[:5],
        "visible_prices": visible_prices[:8],
    }


def best_guess(candidates, site):
    """Deterministic best-effort price (source-dependent). Never used as evidence alone."""
    if candidates.get("jsonld_offers"):
        o = candidates["jsonld_offers"][0]
        if o.get("price") is not None:
            return {
                "price": o["price"],
                "currency": o.get("currency") or "CLP",
                "source": "jsonld",
            }
    if candidates.get("meta_price_amount"):
        return {
            "price": float(candidates["meta_price_amount"][0]),
            "currency": (candidates.get("meta_price_currency") or ["CLP"])[0],
            "source": "meta",
        }
    if site == "rhona" and candidates.get("visible_prices"):
        # rhona shows prices like "$ 187.124" (dot = thousands separator, CLP).
        raw = candidates["visible_prices"][0].replace(".", "")
        return {"price": float(raw), "currency": "CLP", "source": "visible"}
    return None


def build_items(use_network):
    """Return the gold-set items list. use_network=False re-reads data/raw/*.html."""
    items = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30) as client:
        for site, urls in SELECTED.items():
            site_dir = RAW / site
            site_dir.mkdir(exist_ok=True)
            for i, url in enumerate(urls, 1):
                html_path = None
                meta_path = None
                if use_network:
                    time.sleep(1.5)  # polite rate limit
                    print(f"[{site}] {url}")
                    try:
                        r = client.get(url)
                        html = r.text
                    except Exception as exc:  # noqa: BLE001
                        print(f"    ERROR: {exc}")
                        items.append({"site": site, "index": i, "url": url,
                                      "fetch_error": str(exc), "needs_human_review": True})
                        continue
                    slug = slugify(url)
                    html_path = site_dir / f"{i:02d}_{slug}.html"
                    html_path.write_text(html, encoding="utf-8")
                    meta_path = site_dir / f"{i:02d}_{slug}.meta.json"
                    meta_path.write_text(json.dumps({
                        "requested_url": url,
                        "final_url": str(r.url),
                        "http_status": r.status_code,
                        "content_type": r.headers.get("content-type", ""),
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }, indent=2, ensure_ascii=False), encoding="utf-8")
                else:
                    # find existing snapshot by URL mapping saved in *.meta.json
                    for mf in sorted(site_dir.glob("*.meta.json")):
                        m = json.loads(mf.read_text(encoding="utf-8"))
                        if m.get("requested_url") == url:
                            meta_path = mf
                            html_path = mf.with_name(mf.name.replace(".meta.json", ".html"))
                            break
                    if html_path is None or not html_path.exists():
                        print(f"[{site}] MISSING snapshot for {url}")
                        items.append({"site": site, "index": i, "url": url,
                                      "fetch_error": "missing snapshot", "needs_human_review": True})
                        continue
                    html = html_path.read_text(encoding="utf-8")
                    print(f"[{site}] (cached) {url}")

                candidates = extract_candidates(html)
                guess = best_guess(candidates, site)
                items.append({
                    "site": site,
                    "index": i,
                    "url": url,
                    "html_file": str(html_path.relative_to(ROOT)),
                    "meta_file": str(meta_path.relative_to(ROOT)),
                    "candidates": candidates,
                    "ground_truth": guess["price"] if guess else None,
                    "ground_truth_currency": guess["currency"] if guess else None,
                    "ground_truth_source": guess["source"] if guess else None,
                    "ground_truth_note": (
                        "AUTO best-guess; verify by hand" if guess
                        else "NO deterministic signal (needs browser/API or manual review)"),
                    "needs_human_review": True,
                })
    return items


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    use_network = "--extract-only" not in sys.argv
    RAW.mkdir(parents=True, exist_ok=True)
    gold = {"built_at": datetime.now(timezone.utc).isoformat(), "items": build_items(use_network)}

    OUT.write_text(json.dumps(gold, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {OUT} with {len(gold['items'])} items")


if __name__ == "__main__":
    main()
