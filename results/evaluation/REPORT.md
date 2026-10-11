# Evaluation readout

Mode: extractive

Small, authored synthetic regression cases, not independent or clinical validation.

Mean Recall@3: 0.857; MRR@3: 0.857; nDCG@3: 0.857 (7 answerable cases).

Status matches: 7/8.

Invalid contract payloads rejected: 20/20.

Semantic and clinical accuracy: NOT SCORED. A false survival claim with a genuine quote passes location checks; see the counterexample in evaluation.json.

## Retrieval failure analysis

| Case | Relevant | Retrieved | Recall@3 | Status match |
|---|---|---|---|---|
| R1 | S1, S2, S3 | S2, S3, S1 | 1.0 | True |
| R2 | S4 | S4 | 1.0 | True |
| R3 | S5 | S5 | 1.0 | True |
| R4 | S6 | S6 | 1.0 | True |
| R5 | S7 | S7 | 1.0 | True |
| R6 | S8 | S8 | 1.0 | True |
| R7 | none | none | None | True |
| R8 | S8 | none | 0.0 | False |

R8 is an intentional synonym gap: BM25 has no semantic embeddings and can miss an answerable question. This is retained, not tuned away.

Contract tests check defensive code, not LLM robustness. Live status matches are not semantic grading.
