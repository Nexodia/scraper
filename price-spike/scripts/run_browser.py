"""
P3: A3 browser evaluation.

Renders each gold-set URL with Playwright (headless Chromium), takes the RENDERED
DOM, runs the same deterministic extractors (A1 CSS + A2 JSON-LD/meta) on it, and
compares against the ground truth. Measures wall-clock render+extract latency.

Saves data/evidence_p3.json.

Usage:
    python scripts/run_browser.py
Prereq (once):
    python -m playwright install chromium
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))

from price_extractor.deterministic import run_extractors  # noqa: E402

GOLD = ROOT / "data" / "gold_set.draft.json"
OUT = ROOT / "data" / "evidence_p3.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def match(extracted, truth):
    if extracted is None or truth is None:
        return False
    return round(float(extracted)) == round(float(truth))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    items = gold["items"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA)

        per_site = {}
        order = []
        rows = []
        for it in items:
            sid = it["site"]
            if sid not in per_site:
                per_site[sid] = {"n": 0, "cov": 0, "ok": 0, "render_ms": []}
                order.append(sid)
            s = per_site[sid]
            s["n"] += 1

            url = it["url"]
            t0 = time.perf_counter()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                try:
                    page.wait_for_load_state("networkidle", timeout=12000)
                except Exception:
                    time.sleep(3)  # settle fallback
                rendered = page.content()
                status = "ok"
            except Exception as exc:  # noqa: BLE001
                rendered = ""
                status = f"error: {type(exc).__name__}"
            elapsed_ms = (time.perf_counter() - t0) * 1000
            s["render_ms"].append(elapsed_ms)

            res = run_extractors(rendered, sid)
            best = res["best_deterministic"]["price"]
            truth = it.get("ground_truth")

            covered = best is not None
            correct = match(best, truth)
            if covered:
                s["cov"] += 1
            if correct:
                s["ok"] += 1

            rows.append({
                "site": sid, "index": it["index"], "url": url,
                "status": status, "render_ms": round(elapsed_ms, 1),
                "extracted": best, "truth": truth,
                "covered": covered, "correct": correct,
            })
            print(f"[{sid} #{it['index']}] {elapsed_ms:8.0f}ms  status={status}  "
                  f"extracted={best}  truth={truth}  {'OK' if correct else ('MISS' if not covered else 'WRONG')}")

        browser.close()

    summary = {}
    for sid in order:
        s = per_site[sid]
        n = s["n"]
        summary[sid] = {
            "n": n, "coverage": s["cov"], "correct": s["ok"],
            "accuracy": round(s["ok"] / n, 4) if n else 0,
            "avg_render_ms": round(sum(s["render_ms"]) / n, 1),
        }

    total_n = len(rows)
    total_cov = sum(1 for r in rows if r["covered"])
    total_ok = sum(1 for r in rows if r["correct"])
    avg_ms = sum(r["render_ms"] for r in rows) / total_n if total_n else 0

    evidence = {
        "spike": "SP1",
        "phase": "P3",
        "method": "A3_browser (Playwright render + deterministic extractors)",
        "metrics": {
            "n": total_n,
            "coverage": total_cov,
            "correct": total_ok,
            "accuracy": round(total_ok / total_n, 4),
            "accuracy_on_covered": round(total_ok / total_cov, 4) if total_cov else 0,
            "avg_render_ms": round(avg_ms, 1),
        },
        "per_site": summary,
        "rows": rows,
        "notes": [
            "Wall-clock render+extract latency (network + JS execution).",
            "sonepar rendered shell has no price without auth -> documented as 0 coverage; API covers it (see evidence_p3_apis).",
        ],
    }
    OUT.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 90)
    print(f"{'site':<14} {'n':>2} | {'cov':>3} {'acc':>5} | {'avg render ms':>12}")
    print("-" * 90)
    for sid in order:
        s = summary[sid]
        print(f"{sid:<14} {s['n']:>2} | {s['coverage']:>3} {s['accuracy']*100:>5.0f}% | {s['avg_render_ms']:>10.0f}")
    print("-" * 90)
    print(f"{'TOTAL':<14} {total_n:>2} | {total_cov:>3} {total_ok/total_n*100:>5.0f}% | {avg_ms:>10.0f}")
    print(f"\nEvidence -> {OUT}")


if __name__ == "__main__":
    main()
