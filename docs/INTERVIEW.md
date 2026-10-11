# Interview walkthrough — understand before claiming ownership

This is an AI-assisted portfolio implementation, not an employer deployment or clinical study. Review and rerun the code yourself before presenting it. Do not claim independent clinical validation, a production user base, semantic accuracy, or paid-model results that have not been recorded.

## Two-minute walkthrough

Start with the problem: fluent research summaries can contain invented citations or overstate what a paper measured. Demonstrate the offline packet: three abstracts with favorable, observational and null biomarker findings appear next to their exact excerpts. Explain that the offline baseline is verbatim extraction, not an LLM simulation.

Then describe the interfaces: explicit PubMed query and recorded provenance; transparent BM25 reranking; optional structured model synthesis; local schema/quote checks; human-review packet with source fingerprints. Open the evaluation: the synonym case fails; a false survival claim with a genuine quote also bypasses location checks. Explain why those two failures imply different fixes.

Finish with the engineering decisions: no third-party dependency requirement, Windows/Linux CI, bounded inputs and responses, fixed hosts, sanitized failures, no retry-induced spending, a conservative cost reservation, and real token/latency telemetry when a model is used. This is a bounded research prototype, not a medical product.

## Questions you should be able to answer

- Why BM25 before embeddings? A transparent, cheap baseline exposes retrieval failure; embeddings require an independently labeled comparison, not an assumption of improvement.
- Why no free-form answer? It could bypass claim-level citation checks. The display uses claims; limitation/reason text still needs review.
- Why no model-provided “high certainty”? It is not a validated clinical evidence grade.
- Does an exact quote prove a claim? No. The same source can be irrelevant, contradictory or too narrow. Demonstrate the counterexample.
- How is an empty result handled? Explicit abstention, with no paid model call; missing retrieved evidence does not prove no evidence exists.
- What if the API refuses or returns partial JSON? Fail closed, no synthetic fallback passed off as a real answer.
- How is cost managed? Bounded prompts/output, no retries, cumulative reservation and recorded usage. Client estimates are not provider billing caps.
- What about prompt injection? Source text is untrusted, no autonomous tools are available, and display text is escaped. Instruction-based defenses are not proven robust.
- What is the strongest next experiment? Larger independently labeled retrieval cases, controlled baseline comparison, and claim-level semantic review with a documented rubric and reviewers.

## Truthful résumé scope

After independently verifying and understanding this implementation, describe building an auditable Python evidence workflow with PubMed retrieval, BM25, structured generation, claim-level quote checks, reproducible evaluation and cross-platform tests. Any numerical result must name the small synthetic suite and its denominator. Do not write “eliminated hallucinations,” “clinically validated,” “deployed in hospital,” or imply the entire implementation was completed without assistance.
