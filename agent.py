"""Auditable research evidence workflow. Offline by default; no clinical advice."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from clients import CostGuard, SCHEMA, synthesize
from evidence import abstain, digest, extractive_report, load_evidence, retrieve, validate_evidence, validate_report

ROOT = Path(__file__).resolve().parent


def run(data: dict[str, Any], mode: str = "extractive", k: int = 3,
        api_key: str = "", model: str = "gpt-5.4-mini", guard: CostGuard | None = None) -> dict[str, Any]:
    validate_evidence(data)
    start = time.perf_counter()
    ranked = retrieve(data["question"], data["studies"], k)
    selected = [r["study"] for r in ranked]
    prompt_data = {"question": data["question"], "studies": selected}
    if mode not in ("extractive", "openai"):
        raise ValueError("mode must be extractive or openai")
    if not selected:
        report = abstain("No documents had positive lexical relevance; no model call was made.")
        telemetry = {"mode": mode, "model_called": False, "input_tokens": 0, "output_tokens": 0,
                     "estimated_uncached_cost_usd": 0, "semantic_review": "not_automated"}
    elif mode == "extractive":
        report = extractive_report(data["question"], selected)
        telemetry = {"mode": mode, "model_called": False, "input_tokens": 0, "output_tokens": 0,
                     "estimated_uncached_cost_usd": 0, "semantic_review": "verbatim_excerpts_only"}
    else:
        if guard is None:
            raise ValueError("live mode requires an explicit cost guard")
        report, telemetry = synthesize(prompt_data, api_key, model, guard)
        telemetry["model_called"] = True
    validate_report(report, selected)
    telemetry["pipeline_seconds"] = round(time.perf_counter() - start, 4)
    return {"question": data["question"], "report": report, "sources": selected,
            "retrieval": [{"id": r["study"]["id"], "bm25_score": r["score"]} for r in ranked],
            "telemetry": telemetry, "input_sha256": digest(data), "schema_version": "2.0",
            "review_required": True, "data_provenance": data.get("provenance", {"source": "user_supplied"})}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", nargs="?", type=Path, default=ROOT / "examples/synthetic_evidence.json")
    parser.add_argument("--mode", choices=["extractive", "openai"], default="extractive")
    parser.add_argument("--question", help="Override the question, using the same source corpus")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"))
    parser.add_argument("--max-cost-usd", type=float, default=0.1)
    parser.add_argument("--input-price", type=float, default=0.75, help="Uncached USD per million input tokens")
    parser.add_argument("--output-price", type=float, default=4.5, help="USD per million output tokens")
    parser.add_argument("--output", type=Path, help="Write JSON, Markdown, HTML and a checksum manifest to a NEW directory")
    args = parser.parse_args()
    try:
        if args.mode == "openai" and args.model != "gpt-5.4-mini" and (args.input_price, args.output_price) == (0.75, 4.5):
            raise ValueError("another model requires explicitly verified price arguments")
        if args.output and args.output.exists():
            raise ValueError("output directory already exists; choose a new directory")
        data = load_evidence(args.evidence)
        if args.question is not None:
            data["question"] = args.question
        bundle = run(data, args.mode, args.k, os.getenv("OPENAI_API_KEY", ""), args.model,
                     CostGuard(args.max_cost_usd, args.input_price, args.output_price))
        if args.output:
            from reporting import write_bundle
            write_bundle(bundle, args.output)
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
