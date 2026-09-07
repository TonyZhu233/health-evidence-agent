"""Citation-first biomedical evidence synthesis with the OpenAI Responses API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "certainty": {
                        "type": "string",
                        "enum": ["low", "moderate", "high"],
                    },
                },
                "required": ["claim", "evidence_ids", "certainty"],
                "additionalProperties": False,
            },
        },
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "claims", "limitations"],
    "additionalProperties": False,
}


def load_evidence(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("question"), str) or not data["question"].strip():
        raise ValueError("question must be a non-empty string")
    studies = data.get("studies")
    if not isinstance(studies, list) or not studies:
        raise ValueError("studies must be a non-empty list")

    required = ("id", "title", "abstract")
    for study in studies:
        if not isinstance(study, dict) or any(not str(study.get(k, "")).strip() for k in required):
            raise ValueError(f"each study needs non-empty fields: {', '.join(required)}")
    ids = [study["id"] for study in studies]
    if len(ids) != len(set(ids)):
        raise ValueError("study ids must be unique")
    return data


def validate_report(report: dict[str, Any], evidence_ids: set[str]) -> dict[str, Any]:
    if set(report) != {"answer", "claims", "limitations"}:
        raise ValueError("report must contain only answer, claims, and limitations")
    if not isinstance(report["answer"], str) or not report["answer"].strip():
        raise ValueError("answer must be a non-empty string")
    if not isinstance(report["claims"], list) or not isinstance(report["limitations"], list):
        raise ValueError("claims and limitations must be lists")

    for claim in report["claims"]:
        refs = claim.get("evidence_ids", []) if isinstance(claim, dict) else []
        unknown = set(refs) - evidence_ids
        if not refs or unknown:
            raise ValueError(f"claim has missing or unknown evidence ids: {sorted(unknown)}")
        if claim.get("certainty") not in {"low", "moderate", "high"}:
            raise ValueError("certainty must be low, moderate, or high")
    return report


def _response_text(response: dict[str, Any]) -> str:
    for item in response.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content["text"]
    raise ValueError("API response did not contain output text")


def synthesize(data: dict[str, Any], api_key: str, model: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "store": False,
        "instructions": (
            "You synthesize biomedical evidence. Use only the supplied studies. "
            "Every factual claim must cite one or more supplied study IDs. "
            "Do not give medical advice; state uncertainty and study limitations."
        ),
        "input": json.dumps(data, ensure_ascii=False),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "evidence_report",
                "strict": True,
                "schema": SCHEMA,
            }
        },
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error {exc.code}: {details}") from exc
    report = json.loads(_response_text(body))
    return validate_report(report, {study["id"] for study in data["studies"]})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="JSON file with a question and studies")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"))
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        parser.error("set OPENAI_API_KEY before running the agent")
    try:
        report = synthesize(load_evidence(args.evidence), api_key, args.model)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
