"""
P2 baseline: evaluate deterministic extraction (A1 CSS, A2 structured) against the gold set.

Reads the cached HTML snapshots (no network), runs both methods, compares the extracted
price with the ground truth, and writes data/evidence_p2.json + prints a summary table.

Usage:
    python scripts/run_baseline.py
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))

from price_extractor.deterministic import run_extractors  # noqa: E402

GOLD = ROOT / "data" / "gold_set.draft.json"
OUT = ROOT / "data" / "evidence_p2.json"


def match(extracted, truth):
    if extracted is None or truth is None:
        return False
    return round(float(extracted)) == round(float(truth))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    items = gold["items"]

    # per-site accumulators
    sites = {}
    order = []
    for it in items:
        sid = it["site"]
        if sid not in sites:
            sites[sid] = {"n": 0, "A1": {"ok": 0, "cov": 0}, "A2": {"ok": 0, "cov": 0},
                          "best": {"ok": 0, "cov": 0}, "total_ms": 0.0}
            order.append(sid)
        s = sites[sid]
        s["n"] += 1

        html = ""
        if it.get("html_file"):
            p = ROOT / it["html_file"]
            if p.exists():
                html = p.read_text(encoding="utf-8", errors="replace")

        t0 = time.perf_counter()
        res = run_extractors(html, it["site"])
        elapsed_ms = (time.perf_counter() - t0) * 1000
        s["total_ms"] += elapsed_ms

        truth = it.get("ground_truth")
        a1 = res["A1_css"]["price"]
        # A2 = structured data only (jsonld, else meta) — do NOT fall back to A1 here.
        a2 = (res["A2_jsonld"]["price"] if res["A2_jsonld"]["price"] is not None
              else res["A2_meta"]["price"])
        best = res["best_deterministic"]["price"]

        it["_p2"] = {
            "A1_css": res["A1_css"],
            "A2_jsonld": res["A2_jsonld"],
            "A2_meta": res["A2_meta"],
            "best": res["best_deterministic"],
            "extract_ms": round(elapsed_ms, 3),
        }
        if a1 is not None:
            s["A1"]["cov"] += 1
            if match(a1, truth):
                s["A1"]["ok"] += 1
        if a2 is not None:
            s["A2"]["cov"] += 1
            if match(a2, truth):
                s["A2"]["ok"] += 1
        if best is not None:
            s["best"]["cov"] += 1
            if match(best, truth):
                s["best"]["ok"] += 1

    # print summary
    print(f"{'site':<14} {'n':>2} | {'A1 cov':>7} {'A1 acc':>7} | {'A2 cov':>7} {'A2 acc':>7} | {'best cov':>8} {'best acc':>8} | {'ms/url':>7}")
    print("-" * 100)
    totals = {"n": 0, "A1": [0, 0], "A2": [0, 0], "best": [0, 0], "ms": 0.0}
    for sid in order:
        s = sites[sid]
        n = s["n"]
        a1cov, a1ok = s["A1"]["cov"], s["A1"]["ok"]
        a2cov, a2ok = s["A2"]["cov"], s["A2"]["ok"]
        bcov, bok = s["best"]["cov"], s["best"]["ok"]
        ms = s["total_ms"] / n
        print(f"{sid:<14} {n:>2} | {a1cov:>4}/{n:<3} {a1ok/n*100:>6.0f}% | {a2cov:>4}/{n:<3} {a2ok/n*100:>6.0f}% | {bcov:>4}/{n:<4} {bok/n*100:>6.0f}% | {ms:>6.2f}")
        totals["n"] += n
        totals["A1"][0] += a1cov; totals["A1"][1] += a1ok
        totals["A2"][0] += a2cov; totals["A2"][1] += a2ok
        totals["best"][0] += bcov; totals["best"][1] += bok
        totals["ms"] += s["total_ms"]

    n = totals["n"]
    print("-" * 100)
    print(f"{'TOTAL':<14} {n:>2} | {totals['A1'][0]:>4}/{n:<3} {totals['A1'][1]/n*100:>6.0f}% | {totals['A2'][0]:>4}/{n:<3} {totals['A2'][1]/n*100:>6.0f}% | {totals['best'][0]:>4}/{n:<4} {totals['best'][1]/n*100:>6.0f}% | {totals['ms']/n:>6.2f}")

    evidence = {
        "spike": "SP1",
        "phase": "P2",
        "methods_evaluated": ["A1_css", "A2_jsonld", "A2_meta"],
        "metrics": {
            "A1": {"coverage": totals["A1"][0], "correct": totals["A1"][1], "accuracy": round(totals["A1"][1] / n, 4)},
            "A2": {"coverage": totals["A2"][0], "correct": totals["A2"][1], "accuracy": round(totals["A2"][1] / n, 4)},
            "best_deterministic": {"coverage": totals["best"][0], "correct": totals["best"][1], "accuracy": round(totals["best"][1] / n, 4)},
            "n": n,
            "avg_extract_ms": round(totals["ms"] / n, 3),
        },
        "per_site": {sid: {
            "n": sites[sid]["n"],
            "A1": {"coverage": sites[sid]["A1"]["cov"], "correct": sites[sid]["A1"]["ok"]},
            "A2": {"coverage": sites[sid]["A2"]["cov"], "correct": sites[sid]["A2"]["ok"]},
            "best": {"coverage": sites[sid]["best"]["cov"], "correct": sites[sid]["best"]["ok"]},
        } for sid in order},
        "notes": [
            "CPU-only extraction time on cached HTML (no network); network latency measured in P3.",
            "sonepar excluded: SPA shell has no server-rendered price -> covered by A3 (API).",
            "Accuracy = exact integer match vs gold_set.draft.json ground_truth.",
        ],
    }
    OUT.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")

    # also persist the enriched gold set (with per-item _p2 results) for traceability
    GOLD.write_text(json.dumps(gold, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nEvidence -> {OUT}")
    print("Gold set enriched with per-item _p2 results.")


if __name__ == "__main__":
    main()
