import html
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from render_rich_message import (  # noqa: E402
    build_rich_message,
    render_html_fallback,
    render_html_fallback_parts,
    render_message,
)
from visual_spec import (  # noqa: E402
    FeatureGate,
    ModalityScores,
    SemanticRole,
    VisualDatum,
    VisualIntent,
    make_visual_spec,
)


def make_spec(feature_gate=None, headline="A < B & C"):
    return make_visual_spec(
        primary_question="What changed?",
        headline=headline,
        answer="Risk < limit & source is live",
        semantic_roles=(SemanticRole.STATUS, SemanticRole.SOURCE),
        intents=(VisualIntent.STATE,),
        evidence=(
            VisualDatum(
                label="Value < now",
                value="12 & rising",
                role=SemanticRole.STATUS,
                source_path="$.value",
            ),
        ),
        scores=ModalityScores(90, 20, 0),
        feature_gate=feature_gate,
    )


class RenderRichMessageTests(unittest.TestCase):
    def test_rich_message_has_heading_evidence_and_traceability(self):
        rich = build_rich_message(make_spec())
        self.assertEqual(rich["schema"], "tg-watch.rich-message.v1")
        self.assertEqual(rich["blocks"][0]["type"], "heading")
        table = next(block for block in rich["blocks"] if block["type"] == "table")
        self.assertEqual(table["rows"][0]["source_path"], "$.value")
        self.assertEqual(rich["metadata"]["selected_modality"], "text")

    def test_html_fallback_escapes_all_untrusted_content(self):
        rendered = render_html_fallback(make_spec())
        self.assertIn(html.escape("A < B & C"), rendered)
        self.assertIn(html.escape("Risk < limit & source is live"), rendered)
        self.assertIn(html.escape("12 & rising"), rendered)
        self.assertNotIn("A < B & C", rendered)

    def test_auto_selects_rich_and_includes_html_fallback(self):
        rendered = render_message(
            make_spec(feature_gate=FeatureGate(rich_messages=True))
        )
        self.assertEqual(rendered["selected_format"], "rich_message")
        self.assertEqual(rendered["fallback"]["parse_mode"], "HTML")

    def test_feature_gate_selects_html_only(self):
        gate = FeatureGate()
        rendered = render_message(make_spec(feature_gate=gate))
        self.assertEqual(rendered["selected_format"], "html")
        self.assertEqual(rendered["parse_mode"], "HTML")
        self.assertNotIn("fallback", rendered)

    def test_unverified_default_is_html_only(self):
        self.assertFalse(FeatureGate().rich_messages)
        self.assertEqual(render_message(make_spec())["selected_format"], "html")

    def test_native_location_uses_traceable_coordinates_and_html_fallback(self):
        spec = make_visual_spec(
            primary_question="Where is the event?",
            headline="Event point",
            answer="",
            semantic_roles=(SemanticRole.GEO_POINT,),
            intents=(VisualIntent.GEO_LOCATION,),
            evidence=(
                VisualDatum(
                    label="Latitude",
                    value="1.3521",
                    role=SemanticRole.GEO_POINT,
                    source_path="$.latitude",
                ),
                VisualDatum(
                    label="Longitude",
                    value="103.8198",
                    role=SemanticRole.GEO_POINT,
                    source_path="$.longitude",
                ),
            ),
            scores=ModalityScores(90, 20, 0),
        )
        rendered = render_message(spec)
        self.assertEqual(rendered["selected_format"], "native_location")
        self.assertEqual(rendered["payload"]["latitude"], 1.3521)
        self.assertEqual(
            rendered["payload"]["source_paths"]["longitude"],
            "$.longitude",
        )
        self.assertEqual(rendered["fallback"]["format"], "html")

    def test_html_tight_budget_uses_lossless_continuations(self):
        gate = FeatureGate(rich_messages=False, max_html_chars=80)
        spec = make_spec(feature_gate=gate, headline="X" * 200)
        rendered = render_message(spec)
        parts = [rendered["payload"]] + rendered["continuations"]
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= 80 for part in parts))
        joined = "\n".join(parts)
        self.assertIn(html.escape(spec.answer), joined)
        self.assertIn(html.escape(spec.evidence[0].value), joined)
        self.assertEqual(rendered["part_count"], len(parts))

    def test_html_truncation_never_splits_an_entity(self):
        gate = FeatureGate(rich_messages=False, max_html_chars=45)
        spec = make_spec(feature_gate=gate, headline="<" * 200)
        parts = render_html_fallback_parts(spec)
        self.assertTrue(all(len(part) <= 45 for part in parts))
        self.assertTrue(all(not part.endswith(("&", "&a", "&am", "&amp", "&l", "&lt")) for part in parts))
        self.assertTrue(all(part.count("<b>") == part.count("</b>") for part in parts))

    def test_rich_text_respects_character_budget(self):
        gate = FeatureGate(rich_messages=True, max_rich_text_chars=24)
        spec = make_spec(feature_gate=gate, headline="A very long headline")
        rich = build_rich_message(spec)
        messages = [rich] + rich.get("continuations", [])
        recovered = []
        for message in messages:
            text_count = 0
            for block in message["blocks"]:
                text_count += len(block.get("text", ""))
                for row in block.get("rows", []):
                    text_count += sum(len(cell) for cell in row["cells"])
                    recovered.extend(row["cells"])
            self.assertLessEqual(text_count, 24)
            self.assertTrue(message["metadata"]["content_complete"])
        self.assertTrue(any("12 & rising" in value for value in recovered))

    def test_cli_renders_visual_spec_json(self):
        spec = make_spec()
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
            json.dump(spec.to_dict(), handle)
            handle.flush()
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "render_rich_message.py"),
                    handle.name,
                    "--format",
                    "rich",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        parsed = json.loads(result.stdout)
        self.assertEqual(parsed["schema"], "tg-watch.rich-message.v1")


if __name__ == "__main__":
    unittest.main()
