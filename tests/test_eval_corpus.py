from __future__ import annotations

import json
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "evals" / "cases.json"
sys.path.insert(0, str(ROOT / "evals"))

from build_cases import build_cases  # noqa: E402
from run_evals import evaluate_corpus  # noqa: E402


class EvalCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(CORPUS.read_text(encoding="utf-8"))
        cls.cases = cls.payload["cases"]

    def test_contains_exactly_eighty_five_unique_cases(self) -> None:
        self.assertEqual(self.payload["case_count"], 85)
        self.assertEqual(len(self.cases), 85)
        self.assertEqual(len({case["id"] for case in self.cases}), 85)

    def test_each_intent_has_five_robustness_variants(self) -> None:
        counts = Counter(case["intent"] for case in self.cases)
        self.assertEqual(len(counts), 17)
        self.assertTrue(all(count == 5 for count in counts.values()))

    def test_all_three_media_are_covered(self) -> None:
        self.assertEqual(
            {case["expected_medium"] for case in self.cases},
            {"text", "image", "video"},
        )

    def test_every_case_is_traceable_and_actionable(self) -> None:
        required = {
            "id",
            "intent",
            "primary_question",
            "roles",
            "expected_medium",
            "expected_grammar",
            "sample",
            "variant",
            "locale",
            "uncertainty",
        }
        for case in self.cases:
            self.assertFalse(required - case.keys(), case["id"])
            self.assertTrue(case["roles"], case["id"])
            self.assertTrue(case["sample"], case["id"])

    def test_generated_corpus_matches_checked_in_cases(self) -> None:
        self.assertEqual(build_cases(), self.cases)

    def test_extreme_variants_mutate_relevant_fields(self) -> None:
        by_intent = {}
        for case in self.cases:
            by_intent.setdefault(case["intent"], {})[case["variant"]] = case
        for intent, variants in by_intent.items():
            basic = variants["basic"]["sample"]
            extreme = variants["extreme"]["sample"]
            self.assertNotEqual(basic, extreme, intent)
            self.assertNotIn("extreme_fixture", extreme, intent)
            self.assertEqual(set(basic), set(extreme), intent)

    def test_every_variant_changes_its_family_payload(self) -> None:
        by_intent = {}
        for case in self.cases:
            by_intent.setdefault(case["intent"], []).append(case)
        for intent, family in by_intent.items():
            fingerprints = {
                json.dumps(
                    case["sample"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                for case in family
            }
            self.assertEqual(len(fingerprints), 5, intent)

    def test_missing_optional_really_removes_a_field(self) -> None:
        by_intent = {}
        for case in self.cases:
            by_intent.setdefault(case["intent"], {})[case["variant"]] = case
        for intent, variants in by_intent.items():
            basic = variants["basic"]["sample"]
            missing = variants["missing_optional"]["sample"]
            self.assertLess(len(missing), len(basic), intent)
            self.assertEqual(set(basic) - set(missing), {"source"}, intent)

    def test_forward_evaluator_passes_all_eighty_five_cases(self) -> None:
        result = evaluate_corpus(self.payload)
        failures = [case for case in result["results"] if not case["passed"]]
        self.assertEqual(failures, [])
        self.assertEqual(result["passed"], 85)
        self.assertEqual(result["failed"], 0)

    def test_forward_eval_cli(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "evals" / "run_evals.py")],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("85/85 passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
