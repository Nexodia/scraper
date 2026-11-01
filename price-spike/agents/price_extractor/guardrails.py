"""
Deterministic guardrails for the price extractor.

Same philosophy as the teacher's scaffold (Beurer-Kellner et al. 2025):
put safety AROUND the model, not inside the prompt. The LLM proposes; this
code validates and decides.

Pure stdlib so it can be smoke-tested without any installed dependencies.
"""
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

# ---------------------------------------------------------------- allow-lists
ALLOWED_DOMAINS = {
    "www.dartel.cl",
    "dartel.cl",
    "vitelenergia.com",
    "www.vitelenergia.com",
    "rhona.cl",
    "www.rhona.cl",
    "www.tiendatecnored.cl",
    "tiendatecnored.cl",
    "shop.sonepar.cl",
}

ALLOWED_CURRENCIES = {"CLP", "USD", "EUR", "UF"}

# "12.990" | "$12.990" | "12,990" | "12.990 CLP" | "12 990" -> 12990.0
_PRICE_RE = re.compile(r"^[^\d]*(\d{1,3}(?:[.,\s]\d{3})*|\d+)(?:[.,](\d{1,2}))?[^\d]*$")


def normalize_price(raw: Any) -> Optional[float]:
    """Best-effort parse of a human price string into a float. Returns None if not numeric."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    text = str(raw).strip().replace("$", "").replace("USD", "").replace("CLP", "").replace("EUR", "")
    if "-" in text or text == "":
        return None  # negative prices are always invalid
    m = _PRICE_RE.match(text)
    if not m:
        return None
    whole = m.group(1).replace(".", "").replace(",", "").replace(" ", "")
    frac = m.group(2) or "0"
    try:
        return float(f"{whole}.{frac}")
    except ValueError:
        return None


def is_allowed_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host in ALLOWED_DOMAINS


def _reject(reason: str) -> dict:
    return {"status": "blocked_by_guardrail", "reason": reason}


def validate_extraction(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a normalized extraction payload.

    Returns {"status": "ok", ...} or {"status": "blocked_by_guardrail", "reason": ...}.
    """
    url = data.get("url")
    if not url or not is_allowed_url(str(url)):
        return _reject(f"url no permitida o faltante: {url!r}")

    name = data.get("name")
    if not name or not str(name).strip():
        return _reject("name faltante o vacío")

    price = normalize_price(data.get("price"))
    if price is None or price <= 0:
        return _reject(f"price no es numérico positivo: {data.get('price')!r}")

    currency = str(data.get("currency", "CLP")).upper()
    if currency not in ALLOWED_CURRENCIES:
        return _reject(f"currency no permitida: {currency!r}")

    if data.get("price_before") is not None:
        before = normalize_price(data.get("price_before"))
        if before is not None and price > before:
            return _reject(f"price ({price}) > price_before ({before})")

    if data.get("timestamp") is not None:
        try:
            datetime.fromisoformat(str(data["timestamp"]))
        except ValueError:
            return _reject("timestamp no es ISO 8601")

    return {"status": "ok", "price": price, "currency": currency}


def validate_url_args(tool: Any, args: dict[str, Any], tool_context: Any = None) -> Optional[dict]:
    """before_tool_callback for fetch tools: only allow-listed domains."""
    url = args.get("url")
    if not url or not is_allowed_url(str(url)):
        return _reject(f"url no permitida o faltante: {url!r}")
    return None


def validate_extraction_args(tool: Any, args: dict[str, Any], tool_context: Any = None) -> Optional[dict]:
    """before_tool_callback for parse tools: the parse input must be non-empty."""
    html = args.get("html")
    if not html or not str(html).strip():
        return _reject("html faltante o vacío")
    return None


def cross_field_consistency(entries: list[dict[str, Any]]) -> list[str]:
    """Compare the same product extracted from multiple representations.

    Returns a list of human-readable inconsistency descriptions (empty = consistent).
    """
    problems: list[str] = []
    prices = [(e.get("source", "unknown"), normalize_price(e.get("price"))) for e in entries]
    parsed = [(s, p) for s, p in prices if p is not None]
    if len(parsed) < 2:
        return problems
    ref = parsed[0][1]
    for source, p in parsed[1:]:
        if abs(p - ref) > 0.01:
            problems.append(
                f"price mismatch: {parsed[0][0]}={ref} vs {source}={p}"
            )
    return problems
