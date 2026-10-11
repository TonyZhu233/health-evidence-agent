# Architecture and contracts

## Retrieval and provenance

`retrieve_pubmed.py` sends an explicit query to ESearch, fetches only returned numeric PMIDs from EFetch, and saves query provenance alongside the usable records. Both service URLs are fixed in code. No user-provided arbitrary URL is fetched. Redirects are rejected. Network calls have a 45-second timeout and a 2 MB response cap. EFetch XML may contain its usual DTD declaration, but entity declarations are rejected; external DTDs are not fetched by ElementTree.

Records without title/abstract are excluded with a reason; missing requested IDs are tracked. Year can be null when a simple year is unavailable. Nested title/abstract markup is converted to text. Service/query failures fail rather than silently synthesize an empty search result. Query warnings are retained. Rights and human search-review obligations remain with the user.

Local retrieval uses BM25 (`k1=1.5`, `b=0.75`) on title + abstract. Tokenization is English-oriented lowercase alphanumeric splitting plus an explicit stopword list, with no stemming or embeddings. Scores are rounded to eight decimals; ID breaks ties. Terms are processed in sorted order. Zero-score documents are not returned. Top-k is bounded to 1–20; three is the default. A high relevance score is not a source-quality score or a probability.

## Generation and validation

The offline baseline selects one overlapping sentence per retrieved document (at most 12 claims) and copies it verbatim as both claim and quote. It may display conflicting source excerpts without reconciling them. It is useful for testing wiring, provenance and UI, not answering a clinical question.

The paid adapter sends only question, IDs, titles and abstracts. Other metadata is not sent. Structured Outputs uses `text.format` with closed, required objects; status is `answered` or `insufficient_evidence`. `store=false`, no tools, no automatic retry, 2,000 output-token cap. The generation instructions ask for at most six claims, preservation of conflicts and study limitations, abstention for unsupported/personalized questions and no following embedded abstract instructions. These are **instructions**, not a security proof.

Local validation runs independently of the remote schema. It enforces the exact top-level/nested keys, non-empty text, maximum sizes, at least one limitation, answered/nonempty-claim and abstention/no-claim contracts, known source IDs, no repeated source/quote within a claim, and an exact quote location after whitespace normalization. Quotes must span at least 20 characters; case, punctuation and wording still need to match. Neither substring matching nor strict JSON proves entailment. A valid quote can be irrelevant to or contradict the claim.

Failed network calls, model refusals, incomplete responses and invalid reports emit errors without publishing a report. Error messages do not echo raw response bodies, keys or request headers. There is no fallback that substitutes synthetic content for a failed real model call.

## Artifact and privacy boundary

A successful packet contains selected abstracts and its report, with input SHA-256, retrieval scores, provenance and runtime telemetry. A manifest hashes the JSON/Markdown/HTML bytes. `verify_artifacts.py` checks integrity and repeats quote validation; it cannot reconstruct the full original corpus from selected documents or validate a tampered source without an external trust anchor. Checksums are reproducibility aids, not signed authenticity.

HTML escapes source text and has a restrictive CSP, no scripts or third-party assets. Markdown escapes embedded HTML, brackets and table separators. All outputs are human-review packets, not automatically approved statements. `runs/` is Git-ignored; users must still prevent manual uploads of private data. API retention, rights, and access obligations are not solved by a Git ignore rule.

## Cost guard

For each call, reserve uncached input price × (serialized request UTF-8 bytes + 4,096-token overhead allowance), plus output price × 2,000 tokens. Reservations accumulate even after failures. Known usage gets an uncached cost estimate, without pretending this equals the provider invoice. Pricing/model changes, service overhead, regional premiums and billing behavior can invalidate assumptions. Provider-side project budgets and manual review remain necessary. The evaluation has at most eight calls and no retries.
