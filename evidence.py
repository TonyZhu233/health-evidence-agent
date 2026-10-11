"""Input contracts, lexical retrieval, and source-location checks (not entailment)."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

STOPWORDS = set("a an the in of to and or for with by on at is was were does do did what how which compared versus adults study studies synthetic fictional evidence research treatment usual care reduce improves improve effect effects".split())


def text_field(value: Any, name: str, limit: int = 10000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be non-empty text of at most {limit} characters")
    return value


def validate_evidence(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("evidence must be an object")
    text_field(data.get("question"), "question", 2000)
    studies = data.get("studies")
    if not isinstance(studies, list) or len(studies) > 20:
        raise ValueError("studies must be a list of at most 20 records; empty is allowed")
    ids = set()
    for study in studies:
        if not isinstance(study, dict):
            raise ValueError("each study must be an object")
        sid = text_field(study.get("id"), "id", 80)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", sid) or sid in ids:
            raise ValueError("study ids must be safe and unique")
        ids.add(sid)
        text_field(study.get("title"), "title", 500)
        text_field(study.get("abstract"), "abstract")
        year = study.get("year")
        if year is not None and (type(year) is not int or not 1800 <= year <= 2100):
            raise ValueError("year must be an integer between 1800 and 2100 or null")
    return data


def load_evidence(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 300000:
        raise ValueError("evidence file exceeds 300 KB")
    return validate_evidence(json.loads(path.read_text(encoding="utf-8-sig")))


def digest(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def retrieve(question: str, studies: list[dict[str, Any]], k: int = 3) -> list[dict[str, Any]]:
    """BM25, k1=1.5, b=0.75. Zero lexical overlap is not returned."""
    text_field(question, "question", 2000)
    if type(k) is not int or not 1 <= k <= 20:
        raise ValueError("k must be 1..20")
    if not studies:
        return []
    docs = [tokens(s["title"] + " " + s["abstract"]) for s in studies]
    counts = [Counter(doc) for doc in docs]
    mean_length = sum(map(len, docs)) / len(docs) or 1
    ranked = []
    for study, doc, count in zip(studies, docs, counts):
        score = 0.0
        for token in sorted(set(tokens(question))):
            freq = count[token]
            if freq:
                df = sum(token in c for c in counts)
                idf = math.log(1 + (len(docs) - df + 0.5) / (df + 0.5))
                score += idf * freq * 2.5 / (freq + 1.5 * (0.25 + 0.75 * len(doc) / mean_length))
        if score > 0:
            ranked.append({"study": study, "score": round(score, 8)})
    return sorted(ranked, key=lambda r: (-r["score"], r["study"]["id"]))[:k]


def normalize(text: str) -> str:
    return " ".join(text.split())


def validate_report(report: Any, studies: list[dict[str, Any]]) -> dict[str, Any]:
    """Fail closed on structure and quotes. Does NOT verify semantic support."""
    if not isinstance(report, dict) or set(report) != {"status", "reason", "claims", "limitations"}:
        raise ValueError("report must contain only status, reason, claims, limitations")
    if report["status"] not in ("answered", "insufficient_evidence"):
        raise ValueError("invalid status")
    if not isinstance(report["reason"], str) or len(report["reason"]) > 2000:
        raise ValueError("reason must be text of at most 2000 characters")
    if not isinstance(report["claims"], list) or len(report["claims"]) > 12:
        raise ValueError("claims must be a list of at most 12 items")
    limitations = report["limitations"]
    if not isinstance(limitations, list) or not 1 <= len(limitations) <= 10:
        raise ValueError("at least one limitation is required; maximum 10")
    for limitation in limitations:
        text_field(limitation, "limitation", 2000)
    if report["status"] == "insufficient_evidence":
        if report["claims"] or not report["reason"].strip():
            raise ValueError("abstention needs a reason and no claims")
    elif not report["claims"] or report["reason"] != "":
        raise ValueError("answered reports need claims and an empty reason")
    sources = {s["id"]: s for s in studies}
    for claim in report["claims"]:
        if not isinstance(claim, dict) or set(claim) != {"text", "evidence"}:
            raise ValueError("claim must contain text and evidence only")
        text_field(claim["text"], "claim text", 2000)
        refs = claim["evidence"]
        if not isinstance(refs, list) or not 1 <= len(refs) <= 5:
            raise ValueError("each claim needs 1..5 evidence references")
        seen = set()
        for ref in refs:
            if not isinstance(ref, dict) or set(ref) != {"id", "quote"}:
                raise ValueError("evidence reference needs id and quote only")
            sid = text_field(ref["id"], "citation id", 80)
            if sid not in sources:
                raise ValueError("unknown evidence id")
            quote = text_field(ref["quote"], "quote", 2000)
            if len(normalize(quote)) < 20 or normalize(quote) not in normalize(sources[sid]["abstract"]):
                raise ValueError("quote must locate at least 20 characters in the cited abstract")
            key = (sid, normalize(quote))
            if key in seen:
                raise ValueError("duplicate citation quote")
            seen.add(key)
    return report


def abstain(reason: str) -> dict[str, Any]:
    return {"status": "insufficient_evidence", "reason": reason, "claims": [],
            "limitations": ["No clinical advice; absence in the retrieved set is not absence of evidence."]}


def extractive_report(question: str, studies: list[dict[str, Any]]) -> dict[str, Any]:
    """No model: select one overlapping source sentence per retrieved abstract."""
    claims = []
    for study in studies:
        if len(claims) == 12:
            break
        sentences = re.split(r"(?<=[.!?])\s+", study["abstract"])
        choices = [(len(set(tokens(question)) & set(tokens(s))), s) for s in sentences if 20 <= len(s) <= 2000]
        if choices:
            overlap, sentence = max(choices, key=lambda pair: pair[0])
            if overlap:
                claims.append({"text": sentence, "evidence": [{"id": study["id"], "quote": sentence}]})
    if not claims:
        return abstain("No matching source sentences were found by the extractive baseline.")
    return {"status": "answered", "reason": "", "claims": claims,
            "limitations": ["Extractive baseline: verbatim source excerpts, not a clinical synthesis.",
                            "Lexical relevance and valid quotes do not establish study quality or semantic entailment."]}
