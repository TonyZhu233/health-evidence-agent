import json
import tempfile
import unittest
from pathlib import Path

from agent import load_evidence, validate_report


class EvidenceAgentTests(unittest.TestCase):
    def test_load_and_validate_cited_report(self):
        evidence = {
            "question": "Does the intervention improve the outcome?",
            "studies": [{"id": "S1", "title": "Synthetic trial", "abstract": "A synthetic result."}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            path.write_text(json.dumps(evidence), encoding="utf-8")
            loaded = load_evidence(path)

        report = {
            "answer": "The synthetic study suggests a possible benefit [S1].",
            "claims": [{"claim": "A possible benefit was observed.", "evidence_ids": ["S1"], "certainty": "low"}],
            "limitations": ["Synthetic evidence cannot support clinical decisions."],
        }
        self.assertEqual(validate_report(report, {"S1"}), report)
        self.assertEqual(loaded["studies"][0]["id"], "S1")

    def test_rejects_unknown_citation(self):
        report = {
            "answer": "Unsupported answer.",
            "claims": [{"claim": "Unsupported claim.", "evidence_ids": ["S9"], "certainty": "high"}],
            "limitations": [],
        }
        with self.assertRaisesRegex(ValueError, "unknown evidence"):
            validate_report(report, {"S1"})


if __name__ == "__main__":
    unittest.main()
