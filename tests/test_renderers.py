import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, PngImagePlugin


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import make_contact_sheet  # noqa: E402
import render_chart  # noqa: E402
import render_map  # noqa: E402
import render_visual as V  # noqa: E402
import validate_visual  # noqa: E402


def render_spec(kind, data, title=None):
    return {
        "version": "1.0",
        "kind": kind,
        "title": title or f"{kind.title()} 视觉",
        "subtitle": "Deterministic fixture",
        "theme": "light",
        "data": data,
        "meta": {"source": "unit fixture", "timestamp": "2026-07-23 10:00 SGT"},
    }


def visual_decision(grammar, headline, answer, evidence, *, intent, modality="image"):
    if modality == "video":
        scores = {"text": 40, "image": 65, "video": 90}
        fallback = ["video", "image", "text"]
    else:
        scores = {"text": 50, "image": 80, "video": 20}
        fallback = ["image", "text"]
    roles = []
    for item in evidence:
        role = item["role"]
        if role not in roles:
            roles.append(role)
    return {
        "schema_version": "1.0",
        "primary_question": "What does the supplied evidence show?",
        "headline": headline,
        "answer": answer,
        "semantic_roles": roles or ["scalar"],
        "intents": [intent],
        "evidence": evidence,
        "scores": scores,
        "selected_modality": modality,
        "fallback_chain": fallback,
        "selection_reason": "Fixture score selects the audited renderer.",
        "grammar": grammar,
        "feature_gate": {"rich_messages": False, "images": True, "videos": True},
        "warnings": [],
    }


class RendererTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_all_static_render_kinds_produce_valid_png(self):
        cases = {
            "hero": {
                "value": "Operational",
                "value_label": "CURRENT STATE",
                "context": "Caller supplied context for the single dominant value.",
                "status": "Verified input",
            },
            "anchor": {
                "current": 92,
                "anchors": [
                    {"label": "Fair", "value": 100, "primary": True},
                    {"label": "Floor", "value": 80},
                ],
                "bands": [{"label": "Value zone", "low": 78, "high": 105}],
                "prefix": "$",
            },
            "threshold": {
                "value": 72,
                "thresholds": [
                    {"label": "Watch", "value": 80},
                    {"label": "Limit", "value": 95},
                ],
                "domain": [0, 100],
                "suffix": "%",
                "status": "Caller supplied state",
            },
            "comparison": {
                "items": [
                    {"label": "Alpha", "value": 12},
                    {"label": "Beta", "value": 28},
                    {"label": "Gamma", "value": 19},
                ],
                "unit": "ms",
            },
            "ranking": {
                "items": [
                    {"label": "One", "value": 4},
                    {"label": "Two", "value": 9},
                    {"label": "Three", "value": 6},
                ]
            },
            "trend": {
                "points": [
                    {"label": "09:00", "value": 10},
                    {"label": "10:00", "value": 14},
                    {"label": "11:00", "value": 12},
                    {"label": "12:00", "value": 18},
                ],
                "unit": "req/s",
            },
            "timeline": {
                "events": [
                    {"time": "09:00", "label": "Observed", "note": "Input event"},
                    {"time": "09:05", "label": "Changed", "note": "Input state change"},
                    {"time": "09:08", "label": "Current", "note": "Latest supplied state"},
                ]
            },
            "composition": {
                "items": [
                    {"label": "Compute", "value": 55},
                    {"label": "Storage", "value": 30},
                    {"label": "Network", "value": 15},
                ],
                "suffix": "%",
            },
            "uncertainty": {
                "estimate": 50,
                "intervals": [
                    {"label": "Likely", "low": 44, "high": 58},
                    {"label": "Wide", "low": 36, "high": 66},
                ],
                "unit": "ms",
            },
            "network": {
                "nodes": [
                    {"id": "a", "label": "Collector"},
                    {"id": "b", "label": "Processor"},
                    {"id": "c", "label": "Telegram"},
                    {"id": "d", "label": "Archive"},
                ],
                "edges": [
                    {"source": "a", "target": "b", "label": "input"},
                    {"source": "b", "target": "c", "label": "output"},
                    {"source": "b", "target": "d"},
                ],
            },
            "point": {
                "points": [
                    {"label": "Primary", "lat": 1.300, "lon": 103.850},
                    {"label": "Reference", "lat": 1.315, "lon": 103.870},
                ]
            },
            "route": {
                "points": [
                    {"label": "Start", "lat": 1.290, "lon": 103.850},
                    {"label": "Middle", "lat": 1.305, "lon": 103.875},
                    {"label": "End", "lat": 1.335, "lon": 103.910},
                ]
            },
            "radius": {
                "center": {"label": "Center", "lat": 1.300, "lon": 103.850},
                "radius_km": 4,
                "points": [
                    {"label": "A", "lat": 1.315, "lon": 103.860},
                    {"label": "B", "lat": 1.285, "lon": 103.835},
                ],
            },
        }
        outputs = []
        for kind, data in cases.items():
            with self.subTest(kind=kind):
                spec = render_spec(kind, data)
                output = self.work / f"{kind}.png"
                self.assertEqual(V.render(spec, output), output)
                result = validate_visual.validate_visual(
                    output,
                    spec,
                    allow_unverified=True,
                )
                self.assertTrue(result["ok"], result)
                self.assertTrue(result["checks"]["mobile_typography"])
                self.assertEqual(result["metadata"]["render_kind"], kind)
                self.assertEqual(int(result["metadata"]["min_title_font_px"]), V.MIN_TITLE_FONT)
                self.assertEqual(int(result["metadata"]["min_body_font_px"]), V.MIN_BODY_FONT)
                self.assertEqual(int(result["metadata"]["min_metadata_font_px"]), V.MIN_METADATA_FONT)
                outputs.append(output)

        sheet = self.work / "contact-sheet.png"
        make_contact_sheet.make_contact_sheet(outputs, sheet, columns=3)
        with Image.open(sheet) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.info["artifact_kind"], "contact-sheet")
            self.assertEqual(image.info["item_count"], str(len(outputs)))

        mobile = validate_visual.validate_mobile_previews(
            outputs[0],
            self.work / "mobile-static",
        )
        self.assertTrue(mobile["ok"], mobile)
        self.assertEqual(mobile["required_widths"], [320, 375, 390, 430])
        self.assertEqual(mobile["preview_count"], 4)
        for width in mobile["required_widths"]:
            preview = mobile["results"][str(width)]
            self.assertTrue(preview["ok"], preview)
            self.assertEqual(preview["size"][0], width)
            self.assertTrue(preview["checks"]["actual_pixel_content"])
            self.assertTrue(preview["checks"]["actual_safe_margin"])
            self.assertTrue(preview["checks"]["metadata_readability"])
            self.assertGreaterEqual(
                preview["display_font_px"]["metadata"],
                9.5,
            )
            self.assertEqual(preview["font_floor_px"]["metadata"], 9.5)
            with Image.open(preview["path"]) as image:
                self.assertEqual(image.width, width)

    def test_sequence_produces_meaningful_animated_gif(self):
        spec = render_spec(
            "sequence",
            {
                "frames": [
                    {"label": "Start", "value": 10, "note": "Initial supplied value"},
                    {"label": "Crossing", "value": 20, "note": "Middle supplied value"},
                    {"label": "End", "value": 35, "note": "Final supplied value"},
                ],
                "threshold": 20,
                "unit": "%",
                "start_label": "Observed",
                "end_label": "Latest",
            },
        )
        output = self.work / "sequence.gif"
        V.render(spec, output)
        result = validate_visual.validate_visual(
            output,
            spec,
            allow_unverified=True,
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["format"], "GIF")
        self.assertEqual(result["frames"], 3)
        self.assertTrue(result["checks"]["first_last_distinct"])
        self.assertEqual(result["metadata"]["first_frame_label"], "Start")
        self.assertEqual(result["metadata"]["last_frame_label"], "End")
        self.assertTrue(result["checks"]["motion_duration"])
        self.assertTrue(result["checks"]["static_fallbacks"])
        self.assertTrue(result["checks"]["motion_threshold_marker"])
        self.assertTrue(result["checks"]["motion_threshold_encoding"])
        self.assertEqual(result["metadata"]["motion_threshold_visible"], "true")
        self.assertTrue((self.work / "sequence-poster.png").is_file())
        self.assertTrue((self.work / "sequence-final.png").is_file())
        poster_result = validate_visual.validate_visual(
            self.work / "sequence-poster.png",
            spec,
            allow_unverified=True,
        )
        self.assertTrue(poster_result["ok"], poster_result)
        self.assertTrue(poster_result["checks"]["motion_threshold_encoding"])
        mobile = validate_visual.validate_mobile_previews(
            output,
            self.work / "mobile-sequence",
        )
        self.assertTrue(mobile["ok"], mobile)
        self.assertEqual(mobile["preview_count"], 4)
        for width in mobile["required_widths"]:
            preview = mobile["results"][str(width)]
            self.assertEqual(preview["format"], "GIF")
            self.assertEqual(preview["frames"], 3)
            self.assertTrue(preview["checks"]["animation_preserved"])
            with Image.open(preview["path"]) as image:
                self.assertEqual(image.width, width)
                self.assertEqual(image.n_frames, 3)

    def test_mobile_gate_rejects_a_metadata_only_blank_card(self):
        spec = render_spec("hero", {"value": "Operational"})
        source = self.work / "source.png"
        V.render(spec, source)
        with Image.open(source) as image:
            metadata = {
                str(key): str(value)
                for key, value in image.info.items()
                if isinstance(value, (str, int, float))
            }
            blank = Image.new(
                "RGB",
                image.size,
                validate_visual._rgb(metadata["canvas_background_color"]),
            )
        draw = ImageDraw.Draw(blank)
        draw.rectangle(
            tuple(json.loads(metadata["card_bbox"])),
            fill=validate_visual._rgb(metadata["background_color"]),
        )
        info = PngImagePlugin.PngInfo()
        for key, value in metadata.items():
            info.add_text(key, value)
        blank_path = self.work / "metadata-only.png"
        blank.save(blank_path, format="PNG", pnginfo=info)
        mobile = validate_visual.validate_mobile_previews(
            blank_path,
            self.work / "mobile-blank",
        )
        self.assertFalse(mobile["ok"])
        self.assertTrue(
            any(
                not result["checks"]["actual_pixel_content"]
                for result in mobile["results"].values()
            )
        )

    def test_bundle_validates_modality_grammar_and_evidence_bindings(self):
        render = render_spec(
            "anchor",
            {
                "current": 92,
                "anchors": [{"label": "Fair", "value": 100, "primary": True}],
                "prefix": "$",
            },
        )
        render["source_bindings"] = {
            "title": {
                "inputs": ["$.display.title"],
                "operation": "copy",
                "verified_result": render["title"],
            },
            "subtitle": {
                "inputs": ["$.display.subtitle"],
                "operation": "copy",
                "verified_result": render["subtitle"],
            },
            "data.current": {"source_path": "$.price.current"},
            "data.anchors[0].label": {"source_path": "$.price.fair_label"},
            "data.anchors[0].value": {"jsonpath": "$.price.fair"},
            "meta.source": {"source_path": "$.source"},
            "meta.timestamp": {"source_path": "$.timestamp"},
        }
        decision = visual_decision(
            "value-band",
            render["title"],
            render["subtitle"],
            [
                {
                    "label": "Title",
                    "value": render["title"],
                    "role": "category",
                    "source_path": "$.display.title",
                },
                {
                    "label": "Subtitle",
                    "value": render["subtitle"],
                    "role": "status",
                    "source_path": "$.display.subtitle",
                },
                {"label": "Current", "value": "92", "role": "scalar", "source_path": "$.price.current"},
                {"label": "Fair", "value": "100", "role": "anchor", "source_path": "$.price.fair"},
                {"label": "Fair label", "value": "Fair", "role": "category", "source_path": "$.price.fair_label"},
                {"label": "Source", "value": "unit fixture", "role": "source", "source_path": "$.source"},
                {
                    "label": "Timestamp",
                    "value": "2026-07-23 10:00 SGT",
                    "role": "time",
                    "source_path": "$.timestamp",
                },
            ],
            intent="value_anchor",
        )
        bundle = {"visual_spec": decision, "render_spec": render}
        output = self.work / "bundle.png"
        V.render(bundle, output)
        result = validate_visual.validate_visual(output, bundle)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["metadata"]["source_binding_status"], "verified")
        self.assertIn("visual_spec_sha256", result["metadata"])
        self.assertIn("source_bindings_sha256", result["metadata"])

        wrong_modality = copy.deepcopy(bundle)
        wrong_modality["visual_spec"]["selected_modality"] = "text"
        with self.assertRaisesRegex(V.RenderSpecError, "selected_modality"):
            V.load_render_spec(wrong_modality)

        wrong_grammar = copy.deepcopy(bundle)
        wrong_grammar["visual_spec"]["grammar"] = "ranked-bars"
        wrong_grammar["visual_spec"]["intents"] = ["ranking"]
        with self.assertRaisesRegex(V.RenderSpecError, "maps to"):
            V.load_render_spec(wrong_grammar)

        unknown_grammar = copy.deepcopy(bundle)
        unknown_grammar["visual_spec"]["grammar"] = "invented-raster"
        with self.assertRaisesRegex(V.RenderSpecError, "invalid VisualSpec"):
            V.load_render_spec(unknown_grammar)

        bad_binding = copy.deepcopy(bundle)
        bad_binding["render_spec"]["source_bindings"]["data.current"] = {
            "source_path": "$.not.evidence"
        }
        with self.assertRaisesRegex(V.RenderSpecError, "absent from VisualSpec evidence"):
            V.load_render_spec(bad_binding)

        mismatched_value = copy.deepcopy(bundle)
        current_evidence = next(
            item
            for item in mismatched_value["visual_spec"]["evidence"]
            if item["source_path"] == "$.price.current"
        )
        current_evidence["value"] = "93"
        with self.assertRaisesRegex(V.RenderSpecError, "direct binding value mismatch"):
            V.load_render_spec(mismatched_value)

        missing_leaf = copy.deepcopy(bundle)
        del missing_leaf["render_spec"]["source_bindings"]["data.anchors[0].value"]
        with self.assertRaisesRegex(
            V.RenderSpecError,
            "trust evidence is not consumed|factual leaves missing",
        ):
            V.load_render_spec(missing_leaf)

    def test_bundle_without_bindings_is_rejected(self):
        bundle = {
            "visual_spec": visual_decision(
                "threshold-bullet",
                "Threshold 视觉",
                "Deterministic fixture",
                [
                    {"label": "Value", "value": "5", "role": "scalar", "source_path": "$.value"},
                    {"label": "Limit", "value": "10", "role": "threshold", "source_path": "$.limit"},
                ],
                intent="threshold_distance",
            ),
            "render_spec": render_spec(
                "threshold",
                {"value": 5, "threshold": 10, "domain": [0, 12]},
            ),
        }
        with self.assertRaisesRegex(V.RenderSpecError, "source_bindings is required"):
            V.render(bundle, self.work / "missing-bindings.png")

    def test_derived_bindings_titles_and_trust_roles_are_audited(self):
        render = render_spec(
            "comparison",
            {
                "items": [
                    {"label": "A", "value": 12},
                    {"label": "B", "value": 18},
                ],
                "unit": "ms",
            },
        )
        evidence = [
            {
                "label": "Title",
                "value": render["title"],
                "role": "category",
                "source_path": "$.display.title",
            },
            {
                "label": "Subtitle",
                "value": render["subtitle"],
                "role": "status",
                "source_path": "$.display.subtitle",
            },
            {"label": "Categories", "value": ["A", "B"], "role": "category", "source_path": "$.categories"},
            {"label": "Values", "value": [12, 18], "role": "series", "source_path": "$.values"},
            {"label": "Unit", "value": "ms", "role": "unit", "source_path": "$.unit"},
            {"label": "Source", "value": "unit fixture", "role": "source", "source_path": "$.source"},
            {"label": "Time", "value": "2026-07-23 10:00 SGT", "role": "time", "source_path": "$.time"},
        ]
        decision = visual_decision(
            "aligned-bars",
            render["title"],
            render["subtitle"],
            evidence,
            intent="comparison",
        )
        render["source_bindings"] = {
            "title": {
                "inputs": ["$.display.title"],
                "operation": "copy",
                "verified_result": render["title"],
            },
            "subtitle": {
                "inputs": ["$.display.subtitle"],
                "operation": "copy",
                "verified_result": render["subtitle"],
            },
            "data.items": {
                "inputs": ["$.categories", "$.values"],
                "operation": "zip_items",
                "verified_result": render["data"]["items"],
            },
            "data.unit": {"source_path": "$.unit"},
            "meta.source": {"source_path": "$.source"},
            "meta.timestamp": {"source_path": "$.time"},
        }
        bundle = {"visual_spec": decision, "render_spec": render}
        self.assertEqual(V.load_render_spec(bundle)["kind"], "comparison")

        forged = copy.deepcopy(bundle)
        forged["render_spec"]["source_bindings"]["data.items"]["verified_result"][0]["value"] = 999
        with self.assertRaisesRegex(V.RenderSpecError, "verified_result mismatch"):
            V.load_render_spec(forged)

        unknown = copy.deepcopy(bundle)
        unknown["render_spec"]["source_bindings"]["data.items"]["operation"] = "eval_formula"
        with self.assertRaisesRegex(V.RenderSpecError, "unknown derived binding operation"):
            V.load_render_spec(unknown)

        spoofed_title = copy.deepcopy(bundle)
        spoofed_title["render_spec"]["title"] = "URGENT SELL"
        with self.assertRaisesRegex(V.RenderSpecError, "target mismatch"):
            V.load_render_spec(spoofed_title)

        unconsumed = copy.deepcopy(bundle)
        del unconsumed["render_spec"]["data"]["unit"]
        del unconsumed["render_spec"]["source_bindings"]["data.unit"]
        with self.assertRaisesRegex(V.RenderSpecError, "trust evidence is not consumed"):
            V.load_render_spec(unconsumed)

        with self.assertRaisesRegex(V.RenderSpecError, "invalid VisualSpec"):
            V.load_render_spec(
                {
                    "visual_spec": {"selected_modality": "image", "grammar": "aligned-bars"},
                    "render_spec": render,
                }
            )

    def test_bar_domain_cannot_hide_zero_or_outliers(self):
        truncated_bar = render_spec(
            "comparison",
            {
                "items": [{"label": "A", "value": 12}, {"label": "B", "value": 18}],
                "domain": [10, 20],
            },
        )
        with self.assertRaisesRegex(V.RenderSpecError, "excludes plotted values"):
            V.render(truncated_bar, self.work / "truncated.png")

        clipped_anchor = render_spec(
            "anchor",
            {
                "current": 150,
                "anchors": [{"label": "Fair", "value": 100}],
                "domain": [80, 120],
            },
        )
        with self.assertRaisesRegex(V.RenderSpecError, "excludes plotted values"):
            V.render(clipped_anchor, self.work / "clipped.png")

    def test_inferred_map_distance_is_explicitly_geodesic(self):
        spec = render_spec(
            "route",
            {
                "points": [
                    {"label": "A", "lat": 1.290, "lon": 103.850},
                    {"label": "B", "lat": 1.320, "lon": 103.890},
                ]
            },
        )
        output = self.work / "route.png"
        V.render(spec, output)
        with Image.open(output) as image:
            self.assertEqual(
                image.info["distance_semantics"],
                "geodesic-straight-line-segments",
            )

        supplied = render_spec(
            "route",
            {
                "points": [
                    {"label": "A", "lat": 1.290, "lon": 103.850},
                    {"label": "B", "lat": 1.320, "lon": 103.890},
                ],
                "distance": 999.99,
                "unit": "km",
            },
        )
        supplied_output = self.work / "supplied-route.png"
        V.render(supplied, supplied_output)
        with Image.open(supplied_output) as image:
            self.assertEqual(image.info["distance_semantics"], "supplied-distance")

    def test_geo_projection_unwraps_antimeridian_and_preserves_scale(self):
        points = [
            {
                "label": "West",
                "lat": 10.0,
                "lon": 179.9,
                "x": 179.9,
                "y": 10.0,
                "geo": True,
            },
            {
                "label": "East",
                "lat": 10.0,
                "lon": -179.9,
                "x": -179.9,
                "y": 10.0,
                "geo": True,
            },
        ]
        prepared = render_map._prepare_coordinates(points, sequential=True)
        self.assertLess(abs(prepared[1]["x"] - prepared[0]["x"]), 1.0)
        fitted = render_map._fit_bounds((0.0, 0.0, 1.0, 1.0), (0, 0, 800, 400))
        self.assertAlmostEqual(
            (fitted[2] - fitted[0]) / (fitted[3] - fitted[1]),
            2.0,
            places=6,
        )

    def test_dense_network_uses_adjacency_matrix(self):
        nodes = [{"id": str(index), "label": f"Node {index}"} for index in range(6)]
        edges = [
            {"source": str(left), "target": str(right)}
            for left in range(6)
            for right in range(left + 1, 6)
        ]
        spec = render_spec("network", {"nodes": nodes, "edges": edges})
        output = self.work / "dense-network.png"
        V.render(spec, output)
        with Image.open(output) as image:
            self.assertEqual(image.info["network_encoding"], "adjacency-matrix")

    def test_irregular_time_trend_and_directed_network_are_explicit(self):
        values, mode = render_chart._trend_x_values(
            [
                {"label": "09:00", "value": 1},
                {"label": "09:10", "value": 2},
                {"label": "11:00", "value": 3},
            ],
            ["09:00", "09:10", "11:00"],
        )
        self.assertEqual(mode, "time")
        self.assertEqual(values[1] - values[0], 600)
        self.assertEqual(values[2] - values[1], 6600)
        network = render_spec(
            "network",
            {
                "directed": True,
                "nodes": [
                    {"id": "a", "label": "A"},
                    {"id": "b", "label": "B"},
                    {"id": "c", "label": "C"},
                ],
                "edges": [
                    {"source": "a", "target": "b"},
                    {"source": "b", "target": "c"},
                ],
            },
        )
        output = self.work / "directed.png"
        V.render(network, output)
        with Image.open(output) as image:
            self.assertEqual(image.info["network_directed"], "true")

    def test_canonical_new_grammars_map_one_to_one(self):
        cases = {
            "hero-card": "hero",
            "stacked-composition": "composition",
            "range-band": "uncertainty",
            "node-link": "network",
            "point-map": "point",
        }
        for grammar, kind in cases.items():
            with self.subTest(grammar=grammar):
                bundle = {
                    "visual_spec": visual_decision(
                        grammar,
                        "Fixture",
                        "",
                        [
                            {
                                "label": "Title",
                                "source_path": "$.display.title",
                                "value": "Fixture",
                                "role": "category",
                            },
                            {
                                "label": "Value",
                                "source_path": "$.payload",
                                "value": "1",
                                "role": "scalar",
                            },
                        ],
                        intent={
                            "hero-card": "state",
                            "stacked-composition": "composition",
                            "range-band": "uncertainty",
                            "node-link": "network",
                            "point-map": "geo_location",
                        }[grammar],
                    ),
                    "render_spec": {
                        "version": "1.0",
                        "kind": kind,
                        "title": "Fixture",
                        "data": {"value": 1},
                        "meta": {},
                        "source_bindings": {
                            "title": {
                                "inputs": ["$.display.title"],
                                "operation": "copy",
                                "verified_result": "Fixture",
                            },
                            "data.value": {"source_path": "$.payload"}
                        },
                    },
                }
                loaded = V.load_render_spec(bundle)
                self.assertEqual(loaded["kind"], kind)

    def test_numeric_and_long_title_guards(self):
        unsupported = render_spec("hero", {"value": "ok"})
        unsupported["version"] = "2.0"
        with self.assertRaisesRegex(V.RenderSpecError, "unsupported RenderSpec version"):
            V.load_render_spec(unsupported)

        with self.assertRaisesRegex(V.RenderSpecError, "not boolean"):
            V.number(True, "data.value")
        self.assertEqual(
            V.format_value(1.234, {"decimals": 100}),
            "1.23400000",
        )
        self.assertEqual(V.format_value(99.99, {}), "99.99")
        self.assertEqual(V.format_value(123.456, {}), "123.456")
        self.assertEqual(V.format_value(999.9, {}), "999.9")
        wrapped = V.L.wrap_text("A" * 80, 34, False, 200, 20)
        probe = Image.new("RGB", (8, 8))
        probe_draw = ImageDraw.Draw(probe)
        for line in wrapped:
            self.assertLessEqual(
                probe_draw.textlength(line, font=V.font(line, 34)),
                200,
            )
        for color in ((37, 99, 235), (5, 150, 105), (217, 119, 6), (245, 245, 245)):
            self.assertGreaterEqual(
                V.color_contrast(color, V.accessible_foreground(color)),
                4.5,
            )
        spec = render_spec(
            "hero",
            {"value": 42, "context": "Context"},
            title="这是一个非常长的中文标题用于验证四十八像素字号能够自动换成两行而不是溢出卡片边界",
        )
        output = self.work / "long-title.png"
        V.render(spec, output)
        with Image.open(output) as image:
            self.assertGreater(image.height, 780)
            self.assertEqual(image.info["text_truncated"], "false")

        hangul = render_spec("hero", {"value": 42}, title="상태 확인")
        hangul_output = self.work / "hangul.png"
        V.render(hangul, hangul_output)
        result = validate_visual.validate_visual(
            hangul_output,
            hangul,
            allow_unverified=True,
        )
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["checks"]["cjk_font"])

    def test_hero_long_status_wraps_inside_its_expanded_pill(self):
        long_status = (
            "Verified input · upstream reconciliation pending · source freshness "
            "confirmed · neutral status supplied by the caller"
        )
        spec = render_spec(
            "hero",
            {
                "value": "Operational",
                "status": long_status,
                "context": "The long status must remain visible and contained.",
            },
        )
        output = self.work / "hero-long-status.png"
        V.render(spec, output)
        result = validate_visual.validate_visual(
            output,
            spec,
            allow_unverified=True,
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["metadata"]["status_layout"], "wrapped")
        self.assertGreaterEqual(int(result["metadata"]["status_line_count"]), 2)
        pill = json.loads(result["metadata"]["status_pill_bbox"])
        boxes = json.loads(result["metadata"]["status_text_boxes"])
        self.assertTrue(boxes)
        for box in boxes:
            self.assertGreaterEqual(box[0], pill[0])
            self.assertGreaterEqual(box[1], pill[1])
            self.assertLessEqual(box[2], pill[2])
            self.assertLessEqual(box[3], pill[3])

        too_long = render_spec(
            "hero",
            {"value": "Operational", "status": "X" * 1000},
        )
        with self.assertRaisesRegex(V.RenderSpecError, "more than three badge lines"):
            V.render(too_long, self.work / "hero-status-rejected.png")

    def test_over_capacity_visuals_fail_instead_of_silent_slicing(self):
        cases = [
            render_spec(
                "composition",
                {"items": [{"label": str(i), "value": i + 1} for i in range(9)]},
            ),
            render_spec(
                "timeline",
                {"events": [{"time": str(i), "label": str(i)} for i in range(10)]},
            ),
            render_spec(
                "uncertainty",
                {
                    "estimate": 5,
                    "intervals": [
                        {"label": str(i), "low": i, "high": i + 2}
                        for i in range(7)
                    ],
                },
            ),
            render_spec(
                "sequence",
                {"frames": [{"label": str(i), "value": i} for i in range(25)]},
            ),
        ]
        for index, spec in enumerate(cases):
            with self.subTest(kind=spec["kind"]):
                suffix = ".gif" if spec["kind"] == "sequence" else ".png"
                with self.assertRaisesRegex(V.RenderSpecError, "maximum"):
                    V.render(spec, self.work / f"over-{index}{suffix}")

    def test_uncertainty_extreme_endpoint_labels_are_staggered_and_disjoint(self):
        spec = render_spec(
            "uncertainty",
            {
                "estimate": -12345.67,
                "intervals": [
                    {
                        "label": "Confidence interval",
                        "low": -999999.5,
                        "high": 9999999999.999,
                    }
                ],
                "unit": "ms",
                "decimals": 3,
            },
        )
        output = self.work / "uncertainty-extreme.png"
        V.render(spec, output)
        result = validate_visual.validate_visual(
            output,
            spec,
            allow_unverified=True,
        )
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["checks"]["interval_label_separation"])
        self.assertEqual(
            result["metadata"]["interval_label_layout"],
            "staggered",
        )
        boxes = json.loads(result["metadata"]["interval_label_boxes"])[0]
        low_box, high_box = boxes
        self.assertLessEqual(low_box[3] + 12, high_box[1])

    def test_silent_truncation_is_marked_and_rejected(self):
        spec = render_spec(
            "point",
            {
                "points": [
                    {
                        "label": "This location label is deliberately far too long for a mobile map marker",
                        "lat": 1.3,
                        "lon": 103.85,
                    }
                ]
            },
        )
        output = self.work / "truncated-label.png"
        V.render(spec, output)
        result = validate_visual.validate_visual(
            output,
            spec,
            allow_unverified=True,
        )
        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"]["no_text_truncation"])

    def test_render_visual_cli_accepts_render_spec_json(self):
        spec = render_spec(
            "trend",
            {"points": [1, 3, 2, 5], "unit": "items"},
        )
        source = self.work / "render-spec.json"
        source.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        output = self.work / "cli.png"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "render_visual.py"),
                "--spec",
                str(source),
                "--out",
                str(output),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
