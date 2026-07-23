import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from visual_spec import (  # noqa: E402
    FeatureGate,
    Modality,
    ModalityScores,
    SemanticRole,
    VisualDatum,
    VisualIntent,
    VisualSpec,
    grammar_for,
    make_visual_spec,
    select_modality,
)


class VisualSpecTests(unittest.TestCase):
    def test_video_requires_fifteen_point_advantage(self):
        selected, fallback, _ = select_modality(ModalityScores(40, 70, 84))
        self.assertEqual(selected, Modality.IMAGE)
        self.assertEqual(fallback, (Modality.IMAGE, Modality.TEXT))

        selected, fallback, _ = select_modality(ModalityScores(40, 70, 85))
        self.assertEqual(selected, Modality.VIDEO)
        self.assertEqual(
            fallback, (Modality.VIDEO, Modality.IMAGE, Modality.TEXT)
        )

    def test_video_must_also_beat_text(self):
        selected, _, _ = select_modality(ModalityScores(95, 40, 80))
        self.assertEqual(selected, Modality.TEXT)

    def test_video_must_beat_the_best_static_medium_by_fifteen(self):
        selected, _, _ = select_modality(ModalityScores(90, 50, 95))
        self.assertEqual(selected, Modality.TEXT)
        selected, _, _ = select_modality(ModalityScores(80, 50, 95))
        self.assertEqual(selected, Modality.VIDEO)

    def test_feature_gates_force_supported_fallback(self):
        scores = ModalityScores(30, 70, 90)
        selected, fallback, _ = select_modality(
            scores, FeatureGate(images=False, videos=False)
        )
        self.assertEqual(selected, Modality.TEXT)
        self.assertEqual(fallback, (Modality.TEXT,))

        selected, fallback, _ = select_modality(
            ModalityScores(30, 90, 100),
            FeatureGate(images=False, videos=True),
        )
        self.assertEqual(selected, Modality.VIDEO)
        self.assertEqual(fallback, (Modality.VIDEO, Modality.TEXT))

    def test_video_validation_ignores_an_unsupported_image_score(self):
        spec = make_visual_spec(
            primary_question="What changed?",
            headline="What changed",
            answer="",
            semantic_roles=(SemanticRole.SEQUENCE,),
            intents=(VisualIntent.STATE_CHANGE,),
            evidence=(),
            scores=ModalityScores(20, 100, 40),
            feature_gate=FeatureGate(images=False, videos=True),
        )
        self.assertEqual(spec.selected_modality, Modality.VIDEO)
        self.assertEqual(spec.fallback_chain, (Modality.VIDEO, Modality.TEXT))

    def test_image_tie_prefers_simpler_text(self):
        selected, _, _ = select_modality(ModalityScores(70, 70, 0))
        self.assertEqual(selected, Modality.TEXT)

    def test_score_validation(self):
        with self.assertRaises(ValueError):
            ModalityScores(-1, 20, 30)
        with self.assertRaises(ValueError):
            ModalityScores(10, 20, 101)
        with self.assertRaises(TypeError):
            ModalityScores.from_dict({"text": "10", "image": 20, "video": 30})

    def test_feature_gate_rejects_string_booleans(self):
        with self.assertRaises(TypeError):
            FeatureGate.from_dict({"images": "false"})
        with self.assertRaises(TypeError):
            FeatureGate.from_dict({"max_html_chars": "4096"})
        with self.assertRaisesRegex(ValueError, "supported ceiling"):
            FeatureGate(max_html_chars=4097)
        with self.assertRaisesRegex(ValueError, "supported ceiling"):
            FeatureGate(max_rich_text_chars=32769)

    def test_rich_messages_are_opt_in(self):
        self.assertFalse(FeatureGate().rich_messages)

    def test_round_trip_preserves_valid_schema(self):
        spec = make_visual_spec(
            primary_question="How far from the anchor?",
            headline="Asset A",
            answer="1.5% below anchor",
            semantic_roles=(SemanticRole.SCALAR, SemanticRole.ANCHOR),
            intents=(VisualIntent.VALUE_ANCHOR,),
            evidence=(
                VisualDatum(
                    label="Current",
                    value="98.5",
                    unit="USD",
                    role=SemanticRole.SCALAR,
                    source_path="$.current",
                ),
            ),
            scores=ModalityScores(50, 90, 0),
        )
        restored = VisualSpec.from_dict(spec.to_dict())
        self.assertEqual(restored, spec)
        self.assertEqual(restored.delivery_format, "photo")

    def test_constructor_rejects_inconsistent_selected_modality(self):
        with self.assertRaisesRegex(ValueError, "selected_modality"):
            VisualSpec(
                primary_question="Current state?",
                headline="State",
                answer="OK",
                semantic_roles=(SemanticRole.STATUS,),
                intents=(VisualIntent.STATE,),
                evidence=(),
                scores=ModalityScores(90, 10, 0),
                selected_modality=Modality.IMAGE,
                fallback_chain=(Modality.IMAGE, Modality.TEXT),
                selection_reason="invalid",
                grammar="hero-evidence-source",
                feature_gate=FeatureGate(),
            )

    def test_constructor_rejects_inconsistent_grammar(self):
        with self.assertRaisesRegex(ValueError, "grammar"):
            VisualSpec(
                primary_question="Current state?",
                headline="State",
                answer="OK",
                semantic_roles=(SemanticRole.STATUS,),
                intents=(VisualIntent.STATE,),
                evidence=(),
                scores=ModalityScores(90, 10, 0),
                selected_modality=Modality.TEXT,
                fallback_chain=(Modality.TEXT,),
                selection_reason="text is sufficient",
                grammar="value-band",
                feature_gate=FeatureGate(),
            )

    def test_constructor_rejects_more_than_two_secondary_intents(self):
        base = make_visual_spec(
            primary_question="What changed?",
            headline="Change",
            answer="Supplied change",
            semantic_roles=(SemanticRole.SCALAR,),
            intents=(VisualIntent.COMPARISON,),
            evidence=(),
            scores=ModalityScores(30, 90, 0),
        ).to_dict()
        base["intents"] = [
            "comparison",
            "trend",
            "uncertainty",
            "before_after",
        ]
        with self.assertRaisesRegex(ValueError, "at most two secondary"):
            VisualSpec.from_dict(base)

    def test_duplicate_semantics_are_normalized_by_factory(self):
        spec = make_visual_spec(
            primary_question="State?",
            headline="State",
            answer="OK",
            semantic_roles=(SemanticRole.STATUS, SemanticRole.STATUS),
            intents=(VisualIntent.STATE, VisualIntent.STATE),
            evidence=(),
            scores=ModalityScores(90, 10, 0),
        )
        self.assertEqual(spec.semantic_roles, (SemanticRole.STATUS,))
        self.assertEqual(spec.intents, (VisualIntent.STATE,))

        raw = spec.to_dict()
        raw["semantic_roles"].append("status")
        with self.assertRaisesRegex(ValueError, "semantic_roles"):
            VisualSpec.from_dict(raw)

    def test_text_grammar_respects_rich_message_gate(self):
        self.assertEqual(
            grammar_for(Modality.TEXT, (VisualIntent.STATE,), True),
            "verdict-key-values",
        )
        self.assertEqual(
            grammar_for(Modality.TEXT, (VisualIntent.STATE,), False),
            "verdict-key-values",
        )
        self.assertEqual(
            grammar_for(Modality.TEXT, (VisualIntent.DIGEST,), True),
            "rich-digest",
        )
        self.assertEqual(
            grammar_for(Modality.TEXT, (VisualIntent.DIGEST,), False),
            "html-digest",
        )

    def test_evidence_paths_are_unique_jsonpaths_and_roles_are_declared(self):
        base = make_visual_spec(
            primary_question="State?",
            headline="State",
            answer="OK",
            semantic_roles=(SemanticRole.STATUS,),
            intents=(VisualIntent.STATE,),
            evidence=(
                VisualDatum(
                    label="State",
                    value="OK",
                    role=SemanticRole.STATUS,
                    source_path="$.state",
                ),
            ),
            scores=ModalityScores(90, 10, 0),
        ).to_dict()
        duplicate = dict(base)
        duplicate["evidence"] = base["evidence"] * 2
        with self.assertRaisesRegex(ValueError, "source_path values must be unique"):
            VisualSpec.from_dict(duplicate)

        undeclared = dict(base)
        undeclared["evidence"] = [
            {
                "label": "Source",
                "value": "fixture",
                "role": "source",
                "source_path": "$.source",
            }
        ]
        with self.assertRaisesRegex(ValueError, "evidence roles"):
            VisualSpec.from_dict(undeclared)

        with self.assertRaisesRegex(ValueError, "JSONPath"):
            VisualDatum(
                label="Bad",
                value="x",
                role=SemanticRole.STATUS,
                source_path="state",
            )


if __name__ == "__main__":
    unittest.main()
