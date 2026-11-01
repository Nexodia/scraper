"""
P5: MCDA + sensitivity analysis over the 5 extraction alternatives + the emergent hybrid (A6).

Scores (0-100, higher = better) are derived from the P2-P4 evidence files and qualitative
assessments documented in PLAN.md. This script is the reproducible calculation behind ADR-001.

Usage:
    python scripts/run_mcda.py
Output:
    data/evidence_mcda.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "evidence_mcda.json"

# ---------------------------------------------------------------- criteria + weights (PLAN §15)
CRITERIA = {
    "accuracy":     {"weight": 0.35, "direction": "maximize", "source": "evidence P2-P4"},
    "coverage":     {"weight": 0.20, "direction": "maximize", "source": "evidence P2-P4"},
    "cost":         {"weight": 0.15, "direction": "maximize", "source": "estimation", "note": "higher score = cheaper"},
    "latency":      {"weight": 0.10, "direction": "maximize", "source": "evidence P2-P4", "note": "higher score = faster"},
    "robustness":   {"weight": 0.10, "direction": "maximize", "source": "qualitative"},
    "compliance":   {"weight": 0.10, "direction": "maximize", "source": "checklist R8/R9"},
}

# ---------------------------------------------------------------- alternatives + scores
# Scores are 0-100; each criterion already normalized so higher is better.
ALTERNATIVES = {
    "A1_css": {
        "desc": "Classic crawler: CSS selectors on visible DOM",
        "scores": {
            # accuracy 48% (12/25), coverage 60% (15/25) from evidence_p2
            "accuracy": 48, "coverage": 60,
            "cost": 100,      # free, CPU only
            "latency": 90,    # ~1.5s fetch + 2.6ms CPU
            "robustness": 40, # breaks on markup change
            "compliance": 100,
        },
    },
    "A2_structured": {
        "desc": "Structured data: JSON-LD + meta tags",
        "scores": {
            # accuracy 56% (14/25), coverage 60% (15/25)
            "accuracy": 56, "coverage": 60,
            "cost": 100,
            "latency": 90,
            "robustness": 60,  # breaks if structured data removed
            "compliance": 100,
        },
    },
    "A3_browser": {
        "desc": "Headless browser (Playwright) render + extract",
        "scores": {
            # accuracy 76% (19/25), coverage 80% (20/25)
            "accuracy": 76, "coverage": 80,
            "cost": 90,     # server CPU, no API cost
            "latency": 50,  # ~9.4s wall
            "robustness": 50,  # selector fragility + bot-detection risk
            "compliance": 80,  # browser may trip anti-bot; heavier footprint
        },
    },
    "A4_llm": {
        "desc": "LLM extraction (Gemini flash-lite, structured output)",
        "scores": {
            # accuracy 76% (19/25), coverage 80% (20/25)
            "accuracy": 76, "coverage": 80,
            "cost": 70,     # ~1.2M tokens / 25 items (~$0.09); per-page token cost
            "latency": 45,  # ~11.5s/item
            "robustness": 90,  # resilient to markup drift
            "compliance": 100,
        },
    },
    "A5_verifier": {
        "desc": "A4 + agentic verifier (second LLM pass)",
        "scores": {
            # accuracy 76% (19/25) — verifier added 0; coverage 80%
            "accuracy": 76, "coverage": 80,
            "cost": 40,     # 2x LLM calls
            "latency": 30,  # ~23s/item (two passes)
            "robustness": 90,
            "compliance": 100,
        },
    },
    "A6_hybrid": {
        "desc": "Deterministic-first per-site routing + authenticated API for SPA; LLM as optional fallback",
        "scores": {
            # accuracy 96% (24/25): dartel A2 5/5, vitelenergia A2 4/5, tecnored A2 5/5,
            #   rhona A1 5/5, sonepar API 5/5. Only miss = multi-variant ambiguity (unfixable).
            "accuracy": 96, "coverage": 100,
            "cost": 95,     # deterministic + API = effectively free
            "latency": 92,  # ~1.5s fetch; sonepar API ~1s
            "robustness": 75,  # deterministic sites can drift; LLM fallback available
            "compliance": 100,
        },
    },
}


def weighted_score(scores):
    return sum(CRITERIA[c]["weight"] * scores[c] for c in CRITERIA)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    base = {a: weighted_score(ALTERNATIVES[a]["scores"]) for a in ALTERNATIVES}
    ranked = sorted(base, key=base.get, reverse=True)

    print(f"{'alt':<14} {'score':>7}  rank")
    print("-" * 30)
    for i, a in enumerate(ranked, 1):
        print(f"{a:<14} {base[a]:>7.2f}  #{i}")

    # ---------------------------------------------------------------- sensitivity: vary each weight +/-0.10
    sensitivity = {}
    for crit in CRITERIA:
        other_shift = 0.10 / (len(CRITERIA) - 1)  # redistribute so weights sum to 1
        for direction, delta in (("up", 0.10), ("down", -0.10)):
            w = {c: CRITERIA[c]["weight"] for c in CRITERIA}
            w[crit] += delta
            for c in CRITERIA:
                if c != crit:
                    w[c] -= other_shift
            scores = {a: sum(w[c] * ALTERNATIVES[a]["scores"][c] for c in CRITERIA)
                      for a in ALTERNATIVES}
            top = max(scores, key=scores.get)
            sensitivity[f"{crit}_{direction}"] = {"top": top, "scores": {k: round(v, 2) for k, v in scores.items()}}
            flip = top != ranked[0]
            print(f"  weight {crit:<10} {direction:>4}: top={top:<14} {'FLIP' if flip else 'stable'}")

    evidence = {
        "spike": "SP1",
        "phase": "P5",
        "criteria": CRITERIA,
        "alternatives": {a: {"desc": v["desc"], "scores": v["scores"],
                             "weighted_score": round(base[a], 2)} for a, v in ALTERNATIVES.items()},
        "ranking": ranked,
        "decision": ranked[0],
        "sensitivity": sensitivity,
        "notes": [
            "Scores 0-100 (higher=better); cost/latency inverted so higher is better.",
            "Accuracy/coverage from evidence_p2/p3/p4; cost/latency/robustness from measurement + qualitative assessment.",
            "A6 hybrid = per-site deterministic routing + Sonepar API; LLM only as fallback (not in default path).",
            "Sensitivity varies each weight by +/-0.10, redistributing the delta across other criteria.",
        ],
    }
    OUT.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDecision: {ranked[0]} (score {base[ranked[0]]:.2f})")
    print(f"Evidence -> {OUT}")


if __name__ == "__main__":
    main()
