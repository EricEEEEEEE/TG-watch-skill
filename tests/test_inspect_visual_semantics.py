import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from inspect_visual_semantics import inspect_payload  # noqa: E402
from visual_spec import FeatureGate, Modality, SemanticRole, VisualIntent  # noqa: E402


class InspectVisualSemanticsTests(unittest.TestCase):
    def test_anchor_payload_selects_anchor_image(self):
        spec = inspect_payload(
            {
                "title": "rswETH / ETH",
                "summary": "Below anchor",
                "current_price": 3210,
                "fair_anchor_price": 3261,
                "discount_percent": 1.56,
                "source": "oracle",
            }
        )
        self.assertIn(SemanticRole.ANCHOR, spec.semantic_roles)
        self.assertIn(SemanticRole.DELTA, spec.semantic_roles)
        self.assertIn(VisualIntent.VALUE_ANCHOR, spec.intents)
        self.assertNotIn(VisualIntent.BEFORE_AFTER, spec.intents)
        self.assertEqual(spec.selected_modality, Modality.IMAGE)
        self.assertEqual(spec.grammar, "value-band")
        units = {datum.source_path: datum.unit for datum in spec.evidence}
        self.assertEqual(units["$.current_price"], None)
        self.assertEqual(units["$.discount_percent"], "%")

    def test_route_uses_video_only_when_motion_is_meaningful(self):
        payload = {
            "title": "Vehicle route",
            "origin": "A",
            "destination": "B",
            "distance_km": 18.2,
            "trajectory": [[1.29, 103.85], [1.32, 103.90], [1.36, 103.99]],
        }
        static = inspect_payload(payload)
        moving = inspect_payload(
            dict(payload, visual_hints={"motion_is_meaningful": True})
        )
        self.assertEqual(static.selected_modality, Modality.IMAGE)
        self.assertEqual(moving.selected_modality, Modality.VIDEO)
        self.assertGreaterEqual(moving.scores.video, moving.scores.image + 15)
        self.assertEqual(moving.grammar, "sequence-replay")
        self.assertFalse(
            any(
                datum.source_path.startswith("$.visual_hints")
                for datum in moving.evidence
            )
        )

    def test_motion_hint_needs_three_meaningful_states(self):
        spec = inspect_payload(
            {
                "title": "Two-point route",
                "origin": "A",
                "destination": "B",
                "visual_hints": {"motion_is_meaningful": True},
            }
        )
        self.assertNotEqual(spec.selected_modality, Modality.VIDEO)
        self.assertTrue(any("fewer than three" in item for item in spec.warnings))

    def test_short_keyword_does_not_match_inside_unrelated_word(self):
        spec = inspect_payload({"platform": "ios", "status": "healthy"})
        self.assertNotIn(SemanticRole.GEO_POINT, spec.semantic_roles)

    def test_simple_status_stays_text(self):
        spec = inspect_payload({"title": "Worker", "status": "healthy"})
        self.assertEqual(spec.selected_modality, Modality.TEXT)
        self.assertIn(VisualIntent.STATE, spec.intents)

    def test_label_value_state_becomes_neutral_headline_and_answer(self):
        spec = inspect_payload({"label": "API availability", "value": "healthy"})
        self.assertEqual(spec.headline, "API availability")
        self.assertEqual(spec.answer, "healthy")
        self.assertFalse(any("must not infer" in item for item in spec.warnings))

    def test_before_after_requires_both_sides(self):
        current_only = inspect_payload({"current_value": 12})
        comparison = inspect_payload({"previous_value": 10, "current_value": 12})
        self.assertNotIn(VisualIntent.BEFORE_AFTER, current_only.intents)
        self.assertIn(VisualIntent.BEFORE_AFTER, comparison.intents)

    def test_missing_conclusion_is_reported_without_fabrication(self):
        spec = inspect_payload({"temperature": 23.4})
        self.assertEqual(spec.answer, "")
        self.assertTrue(any("must not infer" in warning for warning in spec.warnings))

    def test_feature_gates_force_text_and_html(self):
        spec = inspect_payload(
            {"series": [1, 2, 3, 4]},
            feature_gate=FeatureGate(
                rich_messages=False, images=False, videos=False
            ),
        )
        self.assertEqual(spec.selected_modality, Modality.TEXT)
        self.assertEqual(spec.delivery_format, "html")
        self.assertIn("HTML", " ".join(spec.warnings))

    def test_evidence_is_traceable_and_keeps_late_provenance_fields(self):
        payload = {
            **{"metric_%d" % index: index for index in range(20)},
            "unit": "ms",
            "source": "late source",
            "timestamp": "2026-07-23T10:00:00+08:00",
            "confidence_interval": [1, 3],
        }
        spec = inspect_payload(payload)
        self.assertEqual(len(spec.evidence), len(payload))
        self.assertEqual(spec.evidence[0].source_path, "$.metric_0")
        paths = {datum.source_path for datum in spec.evidence}
        self.assertIn("$.unit", paths)
        self.assertIn("$.source", paths)
        self.assertIn("$.timestamp", paths)
        self.assertIn("$.confidence_interval", paths)
        roles = {datum.source_path: datum.role for datum in spec.evidence}
        self.assertEqual(roles["$.unit"], SemanticRole.UNIT)
        self.assertEqual(roles["$.source"], SemanticRole.SOURCE)
        self.assertEqual(roles["$.timestamp"], SemanticRole.TIME)
        self.assertEqual(
            roles["$.confidence_interval"],
            SemanticRole.UNCERTAINTY,
        )

    def test_evidence_values_are_lossless_even_when_display_copy_will_be_long(self):
        values = list(range(200))
        spec = inspect_payload(
            {"label": "Dense series", "series": values},
            primary_question="How has the value changed over time?",
        )
        evidence = {
            datum.source_path: datum.value
            for datum in spec.evidence
        }
        self.assertEqual(json.loads(evidence["$.series"]), values)
        self.assertNotIn("…", evidence["$.series"])

    def test_visual_plan_has_one_primary_and_at_most_two_secondary_intents(self):
        spec = inspect_payload(
            {
                "current_price": 92,
                "fair_anchor_price": 100,
                "discount_percent": 8,
                "threshold": 80,
                "series": [70, 82, 92],
                "latitude": 1.3,
                "longitude": 103.8,
                "nodes": ["source", "sink"],
                "edges": [["source", "sink"]],
                "confidence_interval": [88, 96],
            },
            primary_question="What is the discount or premium to the stated anchor?",
        )
        self.assertEqual(spec.intents[0], VisualIntent.DISCOUNT_PREMIUM)
        self.assertLessEqual(len(spec.intents), 3)

    def test_cli_supports_demo_and_json_file(self):
        command = [sys.executable, str(SCRIPTS / "inspect_visual_semantics.py")]
        demo = subprocess.run(
            command + ["--demo", "--compact"],
            check=True,
            capture_output=True,
            text=True,
        )
        parsed_demo = json.loads(demo.stdout)
        self.assertEqual(parsed_demo["selected_modality"], "image")

        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
            json.dump({"title": "Service", "status": "OK"}, handle)
            handle.flush()
            result = subprocess.run(
                command + [handle.name, "--compact"],
                check=True,
                capture_output=True,
                text=True,
            )
        self.assertEqual(json.loads(result.stdout)["selected_modality"], "text")

    def test_non_object_payload_is_rejected(self):
        with self.assertRaises(TypeError):
            inspect_payload(["not", "an", "object"])  # type: ignore


if __name__ == "__main__":
    unittest.main()
