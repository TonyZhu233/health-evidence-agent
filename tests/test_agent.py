import copy
import hashlib
import json
import math
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent import ROOT, run
from clients import CostGuard, NoRedirect, SCHEMA, TransportError, parse_pubmed, pubmed_search, request_bytes, response_text, synthesize
from evaluate import contract_cases, evaluate, valid_example
from evaluate_behavior import CANARY, prepare_cases
from evidence import abstain, digest, load_evidence, retrieve, validate_evidence, validate_report
from reporting import markdown, render_html, write_bundle


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.data = load_evidence(ROOT / "examples/synthetic_evidence.json")

    def test_sample_contract(self):
        self.assertEqual(len(self.data["studies"]), 8)

    def test_input_root_type(self):
        with self.assertRaises(ValueError):
            validate_evidence([])

    def test_input_field_types(self):
        for key, value in [("id", []), ("title", 3), ("abstract", None), ("year", True)]:
            with self.subTest(key=key):
                data = copy.deepcopy(self.data)
                data["studies"][0][key] = value
                with self.assertRaises(ValueError):
                    validate_evidence(data)

    def test_input_duplicate_ids(self):
        data = copy.deepcopy(self.data)
        data["studies"][1]["id"] = "S1"
        with self.assertRaises(ValueError):
            validate_evidence(data)

    def test_input_size_limits(self):
        for data in [{"question": "x" * 2001, "studies": []}, {"question": "q", "studies": [{}] * 21}]:
            with self.assertRaises(ValueError):
                validate_evidence(data)

    def test_file_size_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.json"
            path.write_text("x" * 300001)
            with self.assertRaises(ValueError):
                load_evidence(path)

    def test_empty_corpus_abstains(self):
        with patch("agent.synthesize") as generate:
            bundle = run({"question": "anything", "studies": []}, "openai")
        generate.assert_not_called()
        self.assertEqual(bundle["report"]["status"], "insufficient_evidence")

    def test_out_of_scope_retrieval(self):
        self.assertEqual(retrieve("pregnancy neonatal mortality", self.data["studies"]), [])

    def test_deterministic_ranking(self):
        a = retrieve("biomarker reduction", self.data["studies"])
        b = retrieve("biomarker reduction", list(reversed(self.data["studies"])))
        self.assertEqual(a, b)

    def test_invalid_k(self):
        for k in (0, 21, True, 1.5):
            with self.assertRaises(ValueError):
                retrieve("q", self.data["studies"], k)

    def test_extractive_claims_are_verbatim(self):
        for claim in run(self.data)["report"]["claims"]:
            self.assertEqual(claim["text"], claim["evidence"][0]["quote"])

    def test_maximum_top_k_respects_claim_cap(self):
        studies = [{**self.data["studies"][0], "id": f"X{i}"} for i in range(20)]
        bundle = run({"question": "biomarker", "studies": studies}, k=20)
        self.assertEqual(len(bundle["sources"]), 20)
        self.assertEqual(len(bundle["report"]["claims"]), 12)

    def test_invalid_mode(self):
        with self.assertRaises(ValueError):
            run(self.data, "magic")

    def test_live_requires_guard(self):
        with self.assertRaises(ValueError):
            run(self.data, "openai")

    def test_input_hash_canonical(self):
        self.assertEqual(digest({"b": 1, "a": 2}), digest({"a": 2, "b": 1}))

    def test_all_contract_cases(self):
        rows = contract_cases(self.data)
        self.assertEqual(len([r for r in rows if r["expected"] == "reject"]), 20)
        for row in rows:
            with self.subTest(case=row["case"]):
                self.assertIsNot(row["passed"], False)

    def test_quote_whitespace_normalization(self):
        report = valid_example(self.data)
        report["claims"][0]["evidence"][0]["quote"] = report["claims"][0]["evidence"][0]["quote"].replace(" ", "\n")
        validate_report(report, self.data["studies"])

    def test_abstention_contract(self):
        validate_report(abstain("No matching evidence."), [])
        bad = abstain("")
        with self.assertRaises(ValueError):
            validate_report(bad, [])

    def test_semantic_blind_spot_is_explicit(self):
        report = valid_example(self.data)
        report["claims"][0]["text"] = "Treatment A proves a universal survival benefit."
        self.assertEqual(validate_report(report, self.data["studies"]), report)

    def test_fixture_metrics_preserve_synonym_failure(self):
        result = evaluate()
        self.assertAlmostEqual(result["summary"]["mean_recall_at_3"], 6 / 7)
        self.assertEqual(result["summary"]["status_matches"], 7)
        self.assertIsNone(result["summary"]["semantic_accuracy"])
        self.assertEqual(result["retrieval_cases"][-1]["retrieved_ids"], [])

    def test_behavior_cases_and_injection_reach_prompt_set(self):
        cases = prepare_cases()
        self.assertEqual(len(cases), 6)
        injected = cases[3][1]
        ranked = retrieve(injected["question"], injected["studies"], 20)
        self.assertIn("S9", [r["study"]["id"] for r in ranked])
        self.assertIn(CANARY, json.dumps(injected))
        self.assertEqual(cases[-1][1]["studies"], [])


class TransportTests(unittest.TestCase):
    def test_response_completed_only(self):
        for status in ("incomplete", "failed", "queued", None):
            with self.assertRaises(ValueError):
                response_text({"status": status, "output": []})

    def test_response_refusal(self):
        with self.assertRaisesRegex(ValueError, "refused"):
            response_text({"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal"}]}]})

    def test_response_missing_output(self):
        with self.assertRaises(ValueError):
            response_text({"status": "completed", "output": []})

    def test_response_multiple_parts(self):
        body = {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": "first"}, {"type": "output_text", "text": "second"}]}]}
        self.assertEqual(response_text(body), "firstsecond")

    def test_budget_before_network(self):
        data = load_evidence(ROOT / "examples/synthetic_evidence.json")
        with patch("clients.request_bytes") as transport:
            with self.assertRaisesRegex(ValueError, "cost guard"):
                synthesize(data, "dummy-not-a-real-key", "gpt-5.4-mini", CostGuard(0.000001))
        transport.assert_not_called()

    def test_budget_invalid_values(self):
        for value in (0, -1, math.nan, math.inf):
            with self.assertRaises(ValueError):
                CostGuard(value)

    def test_budget_cumulative_reservations(self):
        guard = CostGuard(0.012)
        payload = {"max_output_tokens": 1000}
        guard.reserve(payload)
        with self.assertRaises(ValueError):
            guard.reserve(payload)

    def test_missing_key_before_network(self):
        with patch("clients.request_bytes") as transport:
            with self.assertRaises(ValueError):
                synthesize(load_evidence(ROOT / "examples/synthetic_evidence.json"), "", "m", CostGuard(1))
        transport.assert_not_called()

    def test_mocked_api_contract_and_telemetry(self):
        data = load_evidence(ROOT / "examples/synthetic_evidence.json")
        data["metadata"] = "DO_NOT_SEND_THIS"
        body = {"status": "completed", "model": "mock-model", "usage": {"input_tokens": 100, "output_tokens": 50},
                "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(valid_example(data))}]}]}
        with patch("clients.request_bytes", return_value=json.dumps(body).encode()) as transport:
            report, telemetry = synthesize(data, "dummy", "gpt-5.4-mini", CostGuard(1))
        request = transport.call_args.args[0]
        payload = json.loads(request.data)
        self.assertFalse(payload["store"])
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertEqual(payload["max_output_tokens"], 2000)
        self.assertNotIn("DO_NOT_SEND_THIS", payload["input"])
        self.assertIn("untrusted", payload["instructions"])
        self.assertEqual(telemetry["input_tokens"], 100)
        self.assertAlmostEqual(telemetry["estimated_uncached_cost_usd"], 0.0003)
        self.assertEqual(report["status"], "answered")

    def test_invalid_model_report_rejected(self):
        data = load_evidence(ROOT / "examples/synthetic_evidence.json")
        body = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}]}
        with patch("clients.request_bytes", return_value=json.dumps(body).encode()):
            with self.assertRaises(ValueError):
                synthesize(data, "dummy", "m", CostGuard(1))

    def test_request_oversize(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = b"12345"
        with patch("clients.urllib.request.build_opener", return_value=opener):
            with self.assertRaises(TransportError):
                request_bytes(urllib.request.Request("https://example.com"), limit=4)

    def test_http_error_does_not_echo_secret_body(self):
        opener = MagicMock()
        opener.open.side_effect = urllib.error.HTTPError("https://example.com", 401, "secret", {}, None)
        with patch("clients.urllib.request.build_opener", return_value=opener):
            with self.assertRaises(TransportError) as caught:
                request_bytes(urllib.request.Request("https://example.com"))
        self.assertNotIn("secret", str(caught.exception))

    def test_network_error_sanitized(self):
        opener = MagicMock()
        opener.open.side_effect = urllib.error.URLError("secret-key")
        with patch("clients.urllib.request.build_opener", return_value=opener):
            with self.assertRaises(TransportError) as caught:
                request_bytes(urllib.request.Request("https://example.com"))
        self.assertNotIn("secret-key", str(caught.exception))

    def test_redirect_refused(self):
        with self.assertRaises(TransportError):
            NoRedirect().redirect_request(None, None, 302, "", {}, "https://attacker.test")

    def test_schema_has_required_closed_objects(self):
        def walk(value):
            if isinstance(value, dict):
                if value.get("type") == "object":
                    self.assertFalse(value["additionalProperties"])
                    self.assertEqual(set(value["required"]), set(value["properties"]))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(SCHEMA)


class PubMedTests(unittest.TestCase):
    XML = b'''<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article>
    <ArticleTitle>Test <i>nested</i> title</ArticleTitle><Abstract><AbstractText Label="RESULTS">Synthetic result with <b>nested</b> text.</AbstractText></Abstract>
    <Journal><JournalIssue><PubDate><Year>2025</Year></PubDate></JournalIssue></Journal></Article></MedlineCitation>
    <PubmedData><ArticleIdList><ArticleId IdType="doi">10.0/test</ArticleId></ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>'''

    def test_nested_markup_parsed(self):
        studies, dropped = parse_pubmed(self.XML, ["123"])
        self.assertEqual(studies[0]["title"], "Test nested title")
        self.assertEqual(studies[0]["abstract"], "Synthetic result with nested text.")
        self.assertEqual(studies[0]["year"], 2025)
        self.assertEqual(dropped, [])

    def test_missing_abstract_tracked(self):
        xml = b'<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><ArticleTitle>Title</ArticleTitle></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
        studies, dropped = parse_pubmed(xml, ["123", "456"])
        self.assertEqual(studies, [])
        self.assertEqual(len(dropped), 2)

    def test_unexpected_id_rejected(self):
        with self.assertRaises(ValueError):
            parse_pubmed(self.XML, ["999"])

    def test_entity_xml_rejected(self):
        with self.assertRaises(ValueError):
            parse_pubmed(b'<!ENTITY x "evil"><PubmedArticleSet/>', [])

    def test_error_xml_rejected(self):
        with self.assertRaises(ValueError):
            parse_pubmed(b'<PubmedArticleSet><ERROR>invalid</ERROR></PubmedArticleSet>', [])

    def test_empty_search_no_fetch(self):
        raw = json.dumps({"esearchresult": {"idlist": [], "count": "0"}}).encode()
        with patch("clients.request_bytes", return_value=raw) as transport:
            data = pubmed_search("q", "test")
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(data["studies"], [])

    def test_search_errors(self):
        for result in ({"errorlist": {}}, {"idlist": ["../../evil"], "count": "1"}):
            with patch("clients.request_bytes", return_value=json.dumps({"esearchresult": result}).encode()):
                with self.assertRaises(ValueError):
                    pubmed_search("q", "term")

    def test_search_provenance(self):
        raw = json.dumps({"esearchresult": {"idlist": ["123"], "count": "7", "querytranslation": "translated"}}).encode()
        with patch("clients.request_bytes", side_effect=[raw, self.XML]), patch("clients.time.sleep"):
            data = pubmed_search("q", "term", email="private@example.com")
        self.assertEqual(data["provenance"]["total_matches"], 7)
        self.assertEqual(data["provenance"]["requested_ids"], ["123"])
        self.assertNotIn("private@example.com", json.dumps(data))


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.bundle = run(load_evidence(ROOT / "examples/synthetic_evidence.json"))

    def test_html_escapes_injection(self):
        self.bundle["question"] = '<script>alert("test")</script>'
        rendered = render_html(self.bundle)
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt;', rendered)
        self.assertIn("default-src 'none'", rendered)

    def test_markdown_escapes_markup(self):
        self.bundle["question"] = '<img src=x> [text](javascript:x)'
        rendered = markdown(self.bundle)
        self.assertNotIn('<img src=x>', rendered)
        self.assertIn('\\[text\\]', rendered)

    def test_manifest_matches_generated_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new"
            write_bundle(self.bundle, path)
            manifest = json.loads((path / "manifest.json").read_text())
            for name, expected in manifest["sha256"].items():
                self.assertEqual(hashlib.sha256((path / name).read_bytes()).hexdigest(), expected)
            with self.assertRaises(FileExistsError):
                write_bundle(self.bundle, path)


if __name__ == "__main__":
    unittest.main()
