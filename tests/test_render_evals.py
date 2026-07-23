from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "evals" / "cases.json"
sys.path.insert(0, str(ROOT / "evals"))

from run_render_evals import (  # noqa: E402
    compile_render_bundle,
    evaluate_render_corpus,
)

SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
from inspect_visual_semantics import inspect_payload  # noqa: E402


class RenderEvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(CORPUS.read_text(encoding="utf-8"))
        cls.temp = tempfile.TemporaryDirectory()
        cls.out_dir = Path(cls.temp.name) / "render-eval"
        cls.summary = evaluate_render_corpus(
            cls.payload,
            cls.out_dir,
            contact_sheet=True,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_all_eighty_five_cases_pass_full_forward_pipeline(self) -> None:
        failures = [
            (result["id"], result["errors"])
            for result in self.summary["results"]
            if not result["passed"]
        ]
        self.assertEqual(failures, [])
        self.assertEqual(self.summary["case_count"], 85)
        self.assertEqual(self.summary["passed"], 85)
        self.assertEqual(self.summary["failed"], 0)
        self.assertEqual(
            self.summary["mobile_gate"],
            {
                "required_widths": [320, 375, 390, 430],
                "artifact_count": 85,
                "preview_count": 340,
                "passed_artifacts": 85,
                "failed_artifacts": 0,
                "passed": True,
            },
        )

    def test_expected_primary_media_and_fallbacks_are_materialized(self) -> None:
        self.assertEqual(
            self.summary["media_counts"],
            {"image": 65, "text": 15, "video": 5},
        )
        self.assertEqual(self.summary["artifact_count"], 70)
        video_results = [
            result
            for result in self.summary["results"]
            if result["inference"]["actual"]["medium"] == "video"
        ]
        self.assertEqual(len(video_results), 5)
        for result in self.summary["results"]:
            with self.subTest(case=result["id"]):
                self.assertTrue(result["text_fallback"]["passed"])
                self.assertTrue(result["mobile_gate"]["passed"])
                if result["inference"]["actual"]["medium"] != "text":
                    self.assertTrue(result["media"]["traceability"])
                    self.assertEqual(
                        result["media"]["source_bindings"], "verified"
                    )
                    artifact = self.out_dir / result["paths"]["artifact"]
                    self.assertTrue(artifact.is_file())
                    self.assertGreater(
                        result["mobile_gate"]["artifact_count"],
                        0,
                    )
                    for mobile_artifact in result["mobile_gate"][
                        "artifacts"
                    ].values():
                        self.assertTrue(mobile_artifact["ok"])
                        self.assertEqual(
                            sorted(mobile_artifact["results"]),
                            ["320", "375", "390", "430"],
                        )
                        for width, preview in mobile_artifact[
                            "results"
                        ].items():
                            preview_path = self.out_dir / preview["path"]
                            self.assertTrue(preview_path.is_file())
                            self.assertEqual(preview["size"][0], int(width))
                            self.assertTrue(
                                preview["checks"]["actual_pixel_content"]
                            )
                            self.assertTrue(
                                preview["checks"]["metadata_readability"]
                            )
                else:
                    self.assertTrue(result["mobile_gate"]["not_applicable"])
        for result in video_results:
            self.assertTrue(result["image_fallback"]["passed"])
            fallback = self.out_dir / result["paths"]["image_fallback_artifact"]
            self.assertTrue(fallback.is_file())

    def test_manifest_and_contact_sheet_are_machine_readable(self) -> None:
        manifest_path = self.out_dir / "manifest.json"
        contact_sheet = self.out_dir / self.summary["contact_sheet"]
        self.assertTrue(manifest_path.is_file())
        self.assertTrue(contact_sheet.is_file())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "tg-watch.render-eval.v1")
        self.assertEqual(manifest["case_count"], 85)
        self.assertEqual(len(manifest["results"]), 85)
        self.assertEqual(manifest["mobile_gate"]["artifact_count"], 85)
        self.assertEqual(manifest["mobile_gate"]["preview_count"], 340)
        self.assertTrue(manifest["mobile_gate"]["passed"])

    def test_compiler_uses_executable_operations_not_free_form_formulas(self) -> None:
        operations = set()
        for case in self.payload["cases"]:
            spec = inspect_payload(
                case["sample"],
                primary_question=case["primary_question"],
            )
            if spec.selected_modality.value == "text":
                continue
            bundle = compile_render_bundle(spec)
            bindings = bundle["render_spec"]["source_bindings"]
            for binding in bindings.values():
                self.assertNotIn("formula", binding)
                if "inputs" in binding:
                    self.assertIn("operation", binding)
                    self.assertIn("verified_result", binding)
                    operations.add(binding["operation"])
        self.assertTrue(
            {
                "zip_items",
                "before_after_items",
                "node_objects",
                "edge_objects",
                "interval_band",
                "endpoint_points",
                "timeline_events",
                "format_value_unit",
            }
            <= operations
        )

    def test_cli_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "cli-output"
            mini_corpus = Path(temp) / "cases.json"
            mini_corpus.write_text(
                json.dumps(
                    {
                        "schema": "cli-smoke",
                        "case_count": 1,
                        "cases": [self.payload["cases"][0]],
                    }
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "evals" / "run_render_evals.py"),
                    "--cases",
                    str(mini_corpus),
                    "--out-dir",
                    str(output),
                    "--no-video-fallback",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("1/1 passed", completed.stdout)
            self.assertTrue((output / "manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
