"""
Consolidate P2+P3 evidence into one matrix (site x method) for the P5 MCDA.

Reads:
  * data/gold_set.draft.json      (ground truth)
  * data/evidence_p2.json         (A1 CSS, A2 structured)
  * data/evidence_p3.json         (A3 browser)
  * data/evidence_p3_apis.json    (A3 API)

Writes data/evidence_summary.json with, per site: each method's coverage, accuracy,
avg latency, plus a recommended method (highest accuracy; tie-break = lowest latency).

Usage:
    python scripts/summarize_evidence.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "evidence_summary.json"


def load(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p2 = load("evidence_p2.json")
    p3b = load("evidence_p3.json")
    p3a = load("evidence_p3_apis.json")
    p4 = load("evidence_p4.json")

    sites = list(p2["per_site"].keys())

    matrix = {}
    for sid in sites:
        n = p2["per_site"][sid]["n"]
        methods = {
            "A1_css": {
                "coverage": p2["per_site"][sid]["A1"]["coverage"],
                "correct": p2["per_site"][sid]["A1"]["correct"],
                "latency_ms": 2.6,  # CPU-only (from P2 total avg); placeholder for deterministic
            },
            "A2_structured": {
                "coverage": p2["per_site"][sid]["A2"]["coverage"],
                "correct": p2["per_site"][sid]["A2"]["correct"],
                "latency_ms": 2.6,
            },
            "A3_browser": {
                "coverage": p3b["per_site"][sid]["coverage"],
                "correct": p3b["per_site"][sid]["correct"],
                "latency_ms": p3b["per_site"][sid]["avg_render_ms"],
            },
            "A3_api": {
                "coverage": p3a["per_site"][sid]["coverage"],
                "correct": p3a["per_site"][sid]["correct"],
                "latency_ms": p3a["per_site"][sid]["avg_ms"],
            },
            "A4_llm": {
                "coverage": p4["per_site"][sid]["A4"]["coverage"],
                "correct": p4["per_site"][sid]["A4"]["correct"],
                "latency_ms": p4["metrics"]["avg_ms_per_item"],
            },
            "A5_verifier": {
                "coverage": p4["per_site"][sid]["A5"]["coverage"],
                "correct": p4["per_site"][sid]["A5"]["correct"],
                "latency_ms": p4["metrics"]["avg_ms_per_item"],
            },
        }
        for m, v in methods.items():
            v["accuracy"] = round(v["correct"] / n, 4) if n else 0

        # recommendation: highest accuracy; tie-break lowest latency
        best_method = max(methods, key=lambda m: (methods[m]["accuracy"], -methods[m]["latency_ms"]))
        matrix[sid] = {
            "n": n,
            "methods": methods,
            "recommended_method": best_method,
            "recommended_accuracy": methods[best_method]["accuracy"],
        }

    summary = {
        "spike": "SP1",
        "phases": ["P2", "P3", "P4"],
        "generated_for": "P5 MCDA",
        "matrix": matrix,
        "notes": [
            "A1/A2 latency is CPU-only (cached HTML); A3_browser is wall-clock render; A3_api is network call; A4/A5 is LLM round-trip.",
            "Accuracy = exact integer match vs gold set.",
            "sonepar A3_api = authenticated guest API (products/client/details).",
            "A4_llm = Gemini flash-lite; A5_verifier = second LLM call to verify/correct A4.",
        ],
    }
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # human-readable table
    print(f"{'site':<14} | {'A1':>4} {'A2':>4} {'A3browser':>9} {'A3api':>6} | recommended")
    print("-" * 70)
    for sid in sites:
        m = matrix[sid]["methods"]
        f = lambda k: f"{m[k]['accuracy']*100:3.0f}%"  # noqa: E731
        print(f"{sid:<14} | {f('A1_css'):>4} {f('A2_structured'):>4} {f('A3_browser'):>9} {f('A3_api'):>6} | "
              f"{matrix[sid]['recommended_method']}")
    print(f"\nSummary -> {OUT}")


if __name__ == "__main__":
    main()
