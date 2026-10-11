"""Tiny authored synthetic regression suite. Not a clinical or independent benchmark."""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent import ROOT, run
from clients import CostGuard
from evidence import digest, load_evidence, validate_report


def valid_example(data: dict[str, Any]) -> dict[str, Any]:
    source = data["studies"][0]
    return {"status": "answered", "reason": "", "claims": [{"text": source["abstract"],
            "evidence": [{"id": source["id"], "quote": source["abstract"]}]}], "limitations": ["Fictional test only."]}


def contract_cases(data: dict[str, Any]) -> list[dict[str, Any]]:
    base = valid_example(data)
    mutations = [
        ("invented_id", lambda r: r["claims"][0]["evidence"][0].update(id="FAKE")),
        ("invented_quote", lambda r: r["claims"][0]["evidence"][0].update(quote="This finding never occurred in the supplied abstract.")),
        ("short_quote", lambda r: r["claims"][0]["evidence"][0].update(quote="In this")),
        ("wrong_source", lambda r: r["claims"][0]["evidence"][0].update(id="S2")),
        ("empty_claims", lambda r: r.update(claims=[])),
        ("empty_claim_text", lambda r: r["claims"][0].update(text="")),
        ("nontext_claim", lambda r: r["claims"][0].update(text=123)),
        ("missing_claim_text", lambda r: r["claims"][0].pop("text")),
        ("no_references", lambda r: r["claims"][0].update(evidence=[])),
        ("nontext_id", lambda r: r["claims"][0]["evidence"][0].update(id=[])),
        ("nontext_quote", lambda r: r["claims"][0]["evidence"][0].update(quote=123)),
        ("extra_claim_field", lambda r: r["claims"][0].update(certainty="high")),
        ("extra_top_field", lambda r: r.update(answer="Uncited extra answer")),
        ("missing_limitations", lambda r: r.pop("limitations")),
        ("empty_limitations", lambda r: r.update(limitations=[])),
        ("nontext_limitation", lambda r: r.update(limitations=[123])),
        ("unknown_status", lambda r: r.update(status="verified")),
        ("abstain_with_claim", lambda r: r.update(status="insufficient_evidence", reason="Not enough evidence")),
        ("answered_with_reason", lambda r: r.update(reason="Uncited factual narrative")),
        ("duplicate_quote", lambda r: r["claims"][0]["evidence"].append(copy.deepcopy(r["claims"][0]["evidence"][0]))),
    ]
    rows = []
    for name, mutate in mutations:
        report = copy.deepcopy(base)
        mutate(report)
        rejected = False
        try:
            validate_report(report, data["studies"])
        except ValueError:
            rejected = True
        rows.append({"case": name, "expected": "reject", "observed": "reject" if rejected else "accept", "passed": rejected})
    validate_report(base, data["studies"])
    rows.append({"case": "valid_quote", "expected": "accept", "observed": "accept", "passed": True})
    # Deliberately document the validator's semantic blind spot rather than hide it.
    counterexample = copy.deepcopy(base)
    counterexample["claims"][0]["text"] = "Treatment A proves a survival benefit for every patient."
    validate_report(counterexample, data["studies"])
    rows.append({"case": "false_claim_real_quote", "expected": "accept_known_blind_spot", "observed": "accept",
                 "passed": None, "note": "Quote-location checks do NOT entail this false claim. Human semantic review is required."})
    return rows


def evaluate(mode: str = "extractive", guard: CostGuard | None = None) -> dict[str, Any]:
    data = load_evidence(ROOT / "examples/synthetic_evidence.json")
    cases = json.loads((ROOT / "evals/retrieval_cases.json").read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        current = {**data, "question": case["question"]}
        bundle = run(current, mode, 3, os.getenv("OPENAI_API_KEY", ""), "gpt-5.4-mini", guard)
        ids = [r["id"] for r in bundle["retrieval"]]
        relevant = set(case["relevant_ids"])
        hits = [int(sid in relevant) for sid in ids]
        recall = sum(hits) / len(relevant) if relevant else None
        rr = next((1 / rank for rank, hit in enumerate(hits, 1) if hit), 0) if relevant else None
        dcg = sum(hit / math.log2(rank + 1) for rank, hit in enumerate(hits, 1))
        ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(3, len(relevant)) + 1))
        rows.append({"id": case["id"], "question": case["question"], "relevant_ids": sorted(relevant),
                     "retrieved_ids": ids, "recall_at_3": recall, "reciprocal_rank": rr,
                     "ndcg_at_3": dcg / ideal if ideal else None, "status": bundle["report"]["status"],
                     "expected_status": case["expected_status"], "status_match": bundle["report"]["status"] == case["expected_status"],
                     "report": bundle["report"], "telemetry": bundle["telemetry"],
                     "semantic_support": "NOT_SCORED"})
    contracts = contract_cases(data)
    scored = [r for r in rows if r["recall_at_3"] is not None]
    rejected = [c for c in contracts if c["expected"] == "reject"]
    return {"mode": mode, "created_at_utc": datetime.now(timezone.utc).astimezone(timezone.utc).isoformat(),
            "corpus_sha256": digest(data), "cases_sha256": digest(cases),
            "scope": "Small, authored synthetic regression cases, not independent or clinical validation.",
            "summary": {"retrieval_cases": len(rows), "answerable_retrieval_cases": len(scored),
                        "mean_recall_at_3": sum(r["recall_at_3"] for r in scored) / len(scored),
                        "mrr_at_3": sum(r["reciprocal_rank"] for r in scored) / len(scored),
                        "mean_ndcg_at_3": sum(r["ndcg_at_3"] for r in scored) / len(scored),
                        "status_matches": sum(r["status_match"] for r in rows),
                        "invalid_reports_rejected": sum(c["passed"] for c in rejected), "invalid_report_cases": len(rejected),
                        "semantic_accuracy": None, "clinical_accuracy": None},
            "retrieval_cases": rows, "contract_cases": contracts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="8-case run; at most 8 paid calls, no retries")
    parser.add_argument("--max-cost-usd", type=float, default=0.25)
    parser.add_argument("--output", type=Path, default=Path("runs/eval-offline"))
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("output already exists; choose a new directory")
        result = evaluate("openai" if args.live else "extractive", CostGuard(args.max_cost_usd))
        args.output.mkdir(parents=True)
        (args.output / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        s = result["summary"]
        lines = ["# Evaluation readout", "", f"Mode: {result['mode']}", "", result["scope"], "",
                 f"Mean Recall@3: {s['mean_recall_at_3']:.3f}; MRR@3: {s['mrr_at_3']:.3f}; nDCG@3: {s['mean_ndcg_at_3']:.3f} ({s['answerable_retrieval_cases']} answerable cases).", "",
                 f"Status matches: {s['status_matches']}/{s['retrieval_cases']}.", "",
                 f"Invalid contract payloads rejected: {s['invalid_reports_rejected']}/{s['invalid_report_cases']}.", "",
                 "Semantic and clinical accuracy: NOT SCORED. A false survival claim with a genuine quote passes location checks; see the counterexample in evaluation.json.", "",
                 "## Retrieval failure analysis", "", "| Case | Relevant | Retrieved | Recall@3 | Status match |", "|---|---|---|---|---|"]
        for row in result["retrieval_cases"]:
            lines.append(f"| {row['id']} | {', '.join(row['relevant_ids']) or 'none'} | {', '.join(row['retrieved_ids']) or 'none'} | {row['recall_at_3']} | {row['status_match']} |")
        lines += ["", "R8 is an intentional synonym gap: BM25 has no semantic embeddings and can miss an answerable question. This is retained, not tuned away.", "",
                  "Contract tests check defensive code, not LLM robustness. Live status matches are not semantic grading.", ""]
        (args.output / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
        print(json.dumps(s, indent=2))
        return 0 if s["invalid_reports_rejected"] == s["invalid_report_cases"] else 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
