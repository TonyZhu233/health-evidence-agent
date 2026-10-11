# Validation record — 2026-10-11

## Local offline checks

- Python 3.13.9, Windows; fresh isolated `.venv`, standard library only.
- 47 unittest methods passed in the final local verification. CI also verifies the committed version; consult its actual run status, not only its configuration.
- Offline demo and 8-case evaluation ran successfully; generated packet checksums and quote locations were independently checked with `verify_artifacts.py`.
- Invalid reports: 20/20 rejected; mean retrieval Recall@3/MRR@3/nDCG@3: 0.857 on seven answerable synthetic questions; status match: 7/8.
- Known synonym retrieval miss and genuine-quote/false-claim semantic blind spot retained and documented.
- Desktop (1440 px) and mobile (390 px) review pages rendered in a headless browser and visually inspected; no horizontal page overflow. This is layout QA, not accessibility certification.

## Real PubMed smoke test

The actual ESearch → EFetch path was run on 2026-10-11 with:

```text
hypertension[Title] AND randomized controlled trial[Publication Type]
sort=relevance; retmax=3
```

It returned three usable records and zero exclusions: PMIDs `40888730`, `40587141`, `36516076`. Raw abstracts are kept only in a local Git-ignored run file, not redistributed here. This demonstrates a small real-service retrieval, not comprehensive search quality or a clinical finding. Search results can change over time.

## Real OpenAI validation

**Pending configuration of `OPENAI_API_KEY`.** API construction, schema, response/refusal/incomplete handling and cost checks have been exercised with mocks only. No claim of successful paid-model validation is made. Public CI is deliberately offline and never requires this credential. Six optional live behavior cases cover conflicting findings, survival extrapolation, personal dosing, a malicious-source canary, observational associations and an empty corpus; preparing these cases does not prove the model passes them.

## Boundaries

No clinical accuracy, independently reviewed semantic accuracy, real-world adoption, security certification, systematic-review completeness or employer deployment has been established. API price estimates are not provider invoices or an enforced billing limit.
