# Health Evidence Agent

A citation-first AI agent that synthesizes a supplied set of biomedical studies into structured, auditable claims.

## Why this project exists

Biomedical summaries are easy to generate and hard to trust. This project treats evidence IDs as a contract: every generated claim must cite at least one supplied study, and unknown citations are rejected before output is returned.

The current MVP:

- accepts a research question and study abstracts as JSON;
- calls the OpenAI Responses API with a strict JSON schema;
- returns an answer, claim-level evidence IDs, certainty, and limitations;
- rejects missing or invented evidence IDs;
- runs without third-party Python packages.

## Run

Python 3.10+ is required.

```powershell
$env:OPENAI_API_KEY="your-api-key"
python agent.py examples/synthetic_evidence.json
```

Optionally choose another compatible model:

```powershell
$env:OPENAI_MODEL="gpt-5.4-mini"
```

## Test

Tests do not call the API or require an API key.

```powershell
python -m unittest discover -s tests -v
```

## Input format

```json
{
  "question": "A focused research question",
  "studies": [
    {
      "id": "S1",
      "title": "Study title",
      "year": 2025,
      "abstract": "Study abstract"
    }
  ]
}
```

## Roadmap

- [x] Citation validation and structured synthesis
- [x] Synthetic public example and CI test
- [ ] PubMed retrieval with reproducible search logs
- [ ] Evaluation set for citation validity and extraction accuracy
- [ ] Side-by-side evidence table and lightweight demo

## Safety and data

This repository is for research and education, not medical advice. Do not submit protected health information, confidential lab material, or unpublished study data. The included example is entirely fictional.

## License

MIT
