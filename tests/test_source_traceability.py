import copy
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import render_visual as V  # noqa: E402
from inspect_visual_semantics import inspect_payload  # noqa: E402
from visual_spec import (  # noqa: E402
    ModalityScores,
    SemanticRole,
    VisualDatum,
    VisualIntent,
    make_visual_spec,
)


class SourceTraceabilityTests(unittest.TestCase):
    def _bundle(self):
        visual_spec = make_visual_spec(
            primary_question="How close is capacity to its threshold?",
            headline="Capacity",
            answer="",
            semantic_roles=(
                SemanticRole.CATEGORY,
                SemanticRole.SCALAR,
                SemanticRole.THRESHOLD,
                SemanticRole.UNIT,
                SemanticRole.SOURCE,
                SemanticRole.TIME,
            ),
            intents=(VisualIntent.THRESHOLD_DISTANCE,),
            evidence=(
                VisualDatum(
                    label="Label",
                    value="Capacity",
                    role=SemanticRole.CATEGORY,
                    source_path="$.label",
                ),
                VisualDatum(
                    label="Current",
                    value="73",
                    role=SemanticRole.SCALAR,
                    source_path="$.value",
                ),
                VisualDatum(
                    label="Threshold",
                    value="85",
                    role=SemanticRole.THRESHOLD,
                    source_path="$.threshold",
                ),
                VisualDatum(
                    label="Unit",
                    value="%",
                    role=SemanticRole.UNIT,
                    source_path="$.unit",
                ),
                VisualDatum(
                    label="Source",
                    value="metrics API",
                    role=SemanticRole.SOURCE,
                    source_path="$.source",
                ),
                VisualDatum(
                    label="Timestamp",
                    value="2026-07-23 09:30 SGT",
                    role=SemanticRole.TIME,
                    source_path="$.timestamp",
                ),
            ),
            scores=ModalityScores(text=30, image=90, video=0),
        )
        return {
            "visual_spec": visual_spec.to_dict(),
            "render_spec": {
                "version": "1.0",
                "kind": "threshold",
                "title": "Capacity",
                "subtitle": "",
                "data": {"value": 73, "threshold": 85, "unit": "%"},
                "meta": {
                    "source": "metrics API",
                    "timestamp": "2026-07-23 09:30 SGT",
                },
                "source_bindings": {
                    "title": {
                        "inputs": ["$.label"],
                        "operation": "copy",
                        "verified_result": "Capacity",
                    },
                    "data.value": {"source_path": "$.value"},
                    "data.threshold": {"source_path": "$.threshold"},
                    "data.unit": {"source_path": "$.unit"},
                    "meta.source": {"source_path": "$.source"},
                    "meta.timestamp": {"source_path": "$.timestamp"},
                },
            },
        }

    def test_valid_narrative_copy_is_verified(self):
        loaded = V.load_render_spec(self._bundle())
        self.assertEqual(loaded["_source_binding_status"], "verified")

    def test_spec_field_cannot_certify_an_invented_conclusion(self):
        bundle = self._bundle()
        bundle["visual_spec"]["headline"] = "BUY NOW · 999% GUARANTEED"
        bundle["visual_spec"]["answer"] = "Risk-free opportunity"
        bundle["render_spec"]["title"] = "BUY NOW · 999% GUARANTEED"
        bundle["render_spec"]["subtitle"] = "Risk-free opportunity"
        bundle["render_spec"]["source_bindings"]["title"] = {
            "spec_field": "headline"
        }
        bundle["render_spec"]["source_bindings"]["subtitle"] = {
            "spec_field": "answer"
        }
        with self.assertRaisesRegex(V.RenderSpecError, "not source-traceable"):
            V.load_render_spec(bundle)

    def test_copy_cannot_change_the_evidence_value(self):
        bundle = copy.deepcopy(self._bundle())
        bundle["render_spec"]["title"] = "Risk-free opportunity"
        with self.assertRaisesRegex(V.RenderSpecError, "target mismatch"):
            V.load_render_spec(bundle)

    def test_inspector_keeps_explicit_narrative_as_evidence(self):
        spec = inspect_payload(
            {
                "title": "Capacity",
                "summary": "73% used",
                "value": 73,
                "threshold": 85,
            },
            primary_question="How close is capacity to its threshold?",
        )
        evidence = {datum.source_path: datum.value for datum in spec.evidence}
        self.assertEqual(evidence["$.title"], "Capacity")
        self.assertEqual(evidence["$.summary"], "73% used")


if __name__ == "__main__":
    unittest.main()
