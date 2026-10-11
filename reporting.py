"""Static, escaped evidence-review artifacts; no scripts, remote assets or PHI."""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any


def markdown(bundle: dict[str, Any]) -> str:
    def safe(value: Any) -> str:
        return html.escape(str(value), quote=False).replace("|", "\\|").replace("[", "\\[").replace("]", "\\]")
    report = bundle["report"]
    lines = ["# Health Evidence Agent — review packet", "", "Research demonstration · NOT medical advice · human review required", "",
             f"Mode: **{safe(bundle['telemetry']['mode'])}** · Status: **{safe(report['status'])}**", "",
             "Quote-location checks passed. Semantic support and study quality are NOT automatically verified.", "",
             "## Question", "", safe(bundle["question"]), "", "## Claims and source excerpts", ""]
    if report["reason"]:
        lines += [safe(report["reason"]), ""]
    for i, claim in enumerate(report["claims"], 1):
        lines += [f"### Claim {i}", "", safe(claim["text"]), ""]
        for ref in claim["evidence"]:
            lines += [f"Source {safe(ref['id'])}: {safe(ref['quote'])}", ""]
    lines += ["## Limitations", ""] + [f"- {safe(v)}" for v in report["limitations"]]
    lines += ["", "## Retrieved sources", ""]
    for source in bundle["sources"]:
        lines += [f"### {safe(source['id'])} — {safe(source['title'])}", "", safe(source["abstract"]), ""]
    lines += ["## Run details", "", "```json", json.dumps(bundle["telemetry"], indent=2), "```", "",
              f"Input SHA-256: `{bundle['input_sha256']}`", ""]
    return "\n".join(lines)


def render_html(bundle: dict[str, Any]) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    report = bundle["report"]
    rows = []
    for claim in report["claims"]:
        quotes = "".join(f"<blockquote><strong>{esc(ref['id'])}</strong> · {esc(ref['quote'])}</blockquote>" for ref in claim["evidence"])
        rows.append(f"<tr><td>{esc(claim['text'])}</td><td>{quotes}<span class='tag'>Quote located · meaning needs review</span></td></tr>")
    sources = "".join(f"<details><summary>{esc(s['id'])} · {esc(s['title'])}</summary><p>{esc(s['abstract'])}</p></details>" for s in bundle["sources"])
    limitations = "".join(f"<li>{esc(v)}</li>" for v in report["limitations"])
    telemetry = esc(json.dumps(bundle["telemetry"], indent=2))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Health Evidence Agent · evidence review</title>
<style>body{{margin:0;background:#f3f6fa;color:#1b293c;font:16px/1.6 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:40px 24px}}h1{{font-size:38px;margin:10px 0}}h2{{margin-top:32px}}.eyebrow{{letter-spacing:.15em;color:#42667a;font-size:12px}}.notice{{background:#fff2d9;border-left:4px solid #bc7b14;padding:16px}}.tag{{display:inline-block;background:#eaf0f5;padding:3px 8px;font-size:12px;border-radius:5px}}.panel,details{{background:white;padding:18px;border:1px solid #d6e1e9;border-radius:8px;margin:12px 0}}table{{width:100%;border-collapse:collapse;background:white}}th,td{{padding:18px;text-align:left;border:1px solid #d6e1e9;vertical-align:top;width:50%}}th{{background:#183c50;color:white}}blockquote{{margin:0 0 12px;border-left:3px solid #69a0ab;padding-left:12px}}pre{{overflow:auto;font-size:13px}}p,td{{overflow-wrap:anywhere}}summary{{cursor:pointer}}@media(max-width:650px){{h1{{font-size:28px}}table,thead,tbody,tr,th,td{{display:block;width:auto}}}}</style></head>
<body><main><div class="eyebrow">RESEARCH TOOL / AUDITABLE EVIDENCE</div><h1>Health Evidence Agent</h1>
<p><span class="tag">{esc(bundle['telemetry']['mode'])}</span> <span class="tag">{esc(report['status'])}</span></p>
<div class="notice"><strong>Human review required. Not medical advice.</strong><br>Valid source IDs and located quotes do not prove semantic support, clinical validity or study quality. Synthetic examples are fictional.</div>
<section class="panel"><h2>Research question</h2><p>{esc(bundle['question'])}</p><p>{esc(report['reason'])}</p></section>
<h2>Claims ↔ source excerpts</h2><table><thead><tr><th>Claim / source excerpt</th><th>Located evidence · review against claim</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>Limitations</h2><ul>{limitations}</ul><h2>Retrieved sources</h2>{sources}
<h2>Run details</h2><pre class="panel">{telemetry}</pre><p>Input SHA-256: {esc(bundle['input_sha256'])}</p></main></body></html>"""


def write_bundle(bundle: dict[str, Any], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    files = {"report.json": json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
             "REPORT.md": markdown(bundle), "review.html": render_html(bundle)}
    hashes = {}
    for name, content in files.items():
        raw = content.encode("utf-8")
        (directory / name).write_bytes(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    (directory / "manifest.json").write_text(json.dumps({"schema_version": "2.0", "input_sha256": bundle["input_sha256"],
        "sha256": hashes}, indent=2) + "\n", encoding="utf-8")
