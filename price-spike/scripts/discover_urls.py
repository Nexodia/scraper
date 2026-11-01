"""
P1 discovery: find product URLs from each site's sitemap (robots.txt -> sitemap.xml).

Polite: >= 1.5 s between same-host requests, bounded recursion (max depth 2),
no parallel fetches. Saves results to data/discovered_urls.json.

Usage:
    python scripts/discover_urls.py
"""
import json
import sys
import time
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import httpx

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "sites.json").read_text(encoding="utf-8"))
OUT = ROOT / "data" / "discovered_urls.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "price-spike/0.1 (university research; polite, rate-limited)"
)

_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

# URL path hints that look like a product page (not a category, tag, or asset).
_PRODUCT_HINTS = ("/p/", "/producto", "/product", "/produtos", "/item", "/products/",
                  "/catalogo/", "/productos/", "/shop/", "/product/", "/mlc-", "/-p-")
_NON_PAGE_SUFFIX = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".css", ".js", ".xml")


def _loc_text(elem, tag):
    node = elem.find(f"{_SITEMAP_NS}{tag}")
    return (node.text or "").strip() if node is not None and node.text else ""


def fetch(client, url, delay=1.5):
    time.sleep(delay)
    return client.get(url, follow_redirects=True, timeout=30)


def parse_sitemap(xml_text):
    """Return (is_index, urls)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return False, []
    if root.tag == f"{_SITEMAP_NS}sitemapindex":
        return True, [_loc_text(e, "loc") for e in root.findall(f"{_SITEMAP_NS}sitemap")]
    return False, [_loc_text(e, "loc") for e in root.findall(f"{_SITEMAP_NS}url")]


def is_sitemap_url(url):
    low = url.lower()
    return low.endswith(".xml") or "/sitemap" in low or "sitemap" in low


def looks_like_product(url):
    low = url.lower()
    if low.endswith(_NON_PAGE_SUFFIX):
        return False
    return any(h in low for h in _PRODUCT_HINTS)


def sitemap_urls_from_robots(client, robots_url):
    try:
        r = fetch(client, robots_url)
        txt = r.text
    except Exception as exc:  # noqa: BLE001
        print(f"    robots.txt error: {exc}")
        return []
    return [line.split(":", 1)[1].strip() for line in txt.splitlines()
            if line.lower().startswith("sitemap:")]


def discover(client, site, max_depth=2):
    robots = sitemap_urls_from_robots(client, site["robots_txt"])
    if not robots:
        robots = [urljoin(site["url"], "sitemap.xml")]
    seen_sitemaps, products, child_sitemaps = set(), set(), set()
    frontier = [(u, 0) for u in robots]
    while frontier:
        url, depth = frontier.pop(0)
        if url in seen_sitemaps or depth > max_depth:
            continue
        seen_sitemaps.add(url)
        try:
            r = fetch(client, url)
            r.raise_for_status()
            is_index, locs = parse_sitemap(r.text)
        except Exception as exc:  # noqa: BLE001
            print(f"    sitemap error {url}: {exc}")
            continue
        if is_index:
            child_sitemaps.update(locs)
            frontier.extend((u, depth + 1) for u in locs)
            continue
        for loc in locs:
            if is_sitemap_url(loc):
                frontier.append((loc, depth + 1))
            elif looks_like_product(loc):
                products.add(loc)
    return robots, sorted(child_sitemaps), sorted(products)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    result = {}
    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
        for site in CONFIG["targets"]:
            sid = site["id"]
            print(f"\n===== {sid} ({site['url']}) =====")
            robots, child_sitemaps, products = discover(client, site)
            print(f"    robots sitemaps: {robots}")
            print(f"    child sitemaps parsed: {len(child_sitemaps)}")
            print(f"    product URLs: {len(products)}")
            result[sid] = {
                "robots_sitemaps": robots,
                "child_sitemaps": child_sitemaps,
                "product_urls": products,
            }

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
