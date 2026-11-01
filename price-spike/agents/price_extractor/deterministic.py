"""
Deterministic extraction methods (P2 baseline).

  A2  structured data  -> JSON-LD offers + <meta property="product|og:price:amount">
  A1  CSS crawler      -> per-site visible/server-rendered selectors

All functions take raw HTML and return {"price": float|None, "currency": str|None,
"source": str, "raw": str|None}. Pure and fast (no network, no browser).
"""
import json
import re

from selectolax.lexbor import LexborHTMLParser

from .guardrails import normalize_price

_JSONLD_RE = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S)
_META_AMOUNT_RE = re.compile(
    r'''<(?:meta)[^>]+property=["'](?:product|og):price:amount["'][^>]+content=["']([^"']+)["']''',
    re.I)
_META_CURRENCY_RE = re.compile(
    r'''<(?:meta)[^>]+property=["'](?:product|og):price:currency["'][^>]+content=["']([^"']+)["']''',
    re.I)

# ------------------------------------------------------------------ A2: structured
def _offer_from_dict(o, fallback_currency):
    if not isinstance(o, dict):
        return []
    if isinstance(o.get("offers"), list):  # AggregateOffer
        out = []
        for inner in o["offers"]:
            if isinstance(inner, dict) and inner.get("price") is not None:
                out.append({"price": inner.get("price"),
                            "currency": inner.get("priceCurrency") or o.get("priceCurrency") or fallback_currency})
        if not out and o.get("lowPrice") is not None:
            out.append({"price": o.get("lowPrice"),
                        "currency": o.get("priceCurrency") or fallback_currency})
        return out
    if o.get("price") is not None:
        return [{"price": o.get("price"),
                 "currency": o.get("priceCurrency") or fallback_currency}]
    return []


def extract_jsonld(html):
    """First price found in JSON-LD Product offers (incl. AggregateOffer)."""
    for raw in _JSONLD_RE.findall(html or ""):
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for d in (doc if isinstance(doc, list) else [doc]):
            if not isinstance(d, dict):
                continue
            offs = d.get("offers")
            if isinstance(offs, dict):
                offs = [offs]
            if isinstance(offs, list):
                for o in offs:
                    for norm in _offer_from_dict(o, "CLP"):
                        price = normalize_price(norm["price"])
                        if price is not None:
                            return {"price": price, "currency": norm["currency"] or "CLP",
                                    "source": "jsonld", "raw": str(norm["price"])}
    return {"price": None, "currency": None, "source": "jsonld", "raw": None}


def extract_meta(html):
    """Price from <meta property='product:price:amount'> (and optional currency)."""
    amounts = _META_AMOUNT_RE.findall(html or "")
    currencies = _META_CURRENCY_RE.findall(html or "")
    if not amounts:
        return {"price": None, "currency": None, "source": "meta", "raw": None}
    price = normalize_price(amounts[0])
    return {"price": price, "currency": currencies[0] if currencies else "CLP",
            "source": "meta", "raw": amounts[0]}


# ------------------------------------------------------------------ A1: CSS
def _first_price_in_text(text):
    m = re.search(r"\$\s*(\d{1,3}(?:[.]\d{3})+|\d+)", text or "")
    if not m:
        return None
    return normalize_price(m.group(1).replace(".", ""))


def extract_css(html, site):
    """Per-site CSS selector for the visible/server-rendered price."""
    tree = LexborHTMLParser(html or "")
    if site == "rhona":
        node = tree.css_first("div.precio span.verde") or tree.css_first("div.precio")
        if node is not None:
            price = _first_price_in_text(node.text())
            if price is not None:
                return {"price": price, "currency": "CLP", "source": "css", "raw": node.text().strip()}
    elif site == "tecnored":
        node = tree.css_first("span[data-price-type='finalPrice']")
        if node is not None:
            amount = node.attributes.get("data-price-amount")
            price = normalize_price(amount)
            if price is not None:
                return {"price": price, "currency": "CLP", "source": "css", "raw": amount}
    elif site == "vitelenergia":
        node = tree.css_first("span.price-wrapper") or tree.css_first("[id^='product-price-']")
        if node is not None:
            price = normalize_price(node.text())
            if price is not None:
                return {"price": price, "currency": "CLP", "source": "css", "raw": node.text().strip()}
    elif site == "dartel":
        node = tree.css_first("[class*='vtex-product-price']") or tree.css_first("[class*='sellingPrice']")
        if node is not None:
            price = _first_price_in_text(node.text())
            if price is not None:
                return {"price": price, "currency": "CLP", "source": "css", "raw": node.text().strip()}
    return {"price": None, "currency": None, "source": "css", "raw": None}


# ------------------------------------------------------------------ runner
def run_extractors(html, site):
    """Return per-method results plus a best deterministic pick (A2 preferred)."""
    a2_jsonld = extract_jsonld(html)
    a2_meta = extract_meta(html)
    a1 = extract_css(html, site)

    # A2 = first structured source that yields a price
    a2 = a2_jsonld if a2_jsonld["price"] is not None else a2_meta
    a2["method"] = "A2_structured"

    best = a2 if a2["price"] is not None else a1
    return {
        "A1_css": a1,
        "A2_jsonld": a2_jsonld,
        "A2_meta": a2_meta,
        "best_deterministic": best,
    }
