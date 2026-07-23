import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, PngImagePlugin


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import render_visual as V  # noqa: E402
from validate_visual import contrast_ratio, validate_visual  # noqa: E402


def minimal_metadata(**overrides):
    metadata = {
        "render_spec_version": "1.0",
        "render_kind": "comparison",
        "title": "Fixture",
        "render_spec_sha256": "0" * 64,
        "content_bbox": "[20,20,380,380]",
        "card_bbox": "[20,20,380,380]",
        "canvas_background_color": "#ffffff",
        "background_color": "#ffffff",
        "foreground_color": "#111821",
        "cjk_required": "false",
        "cjk_sample": "",
        "font_path": "",
        "source_binding_status": "standalone-unbound",
        "source_binding_warning": "fixture",
        "traceability_status": "verified",
        "min_title_font_px": str(V.MIN_TITLE_FONT),
        "min_body_font_px": str(V.MIN_BODY_FONT),
        "min_metadata_font_px": str(V.MIN_METADATA_FONT),
        "text_truncated": "false",
    }
    metadata.update({key: str(value) for key, value in overrides.items()})
    return metadata


def write_png(path, metadata):
    image = Image.new("RGB", (400, 400), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 80, 320, 320), fill=(25, 45, 90))
    info = PngImagePlugin.PngInfo()
    for key, value in metadata.items():
        info.add_text(key, value)
    image.save(path, pnginfo=info)


class ValidateVisualTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_contrast_math_matches_black_white_reference(self):
        self.assertAlmostEqual(contrast_ratio((0, 0, 0), (255, 255, 255)), 21.0, places=2)

    def test_low_contrast_is_rejected(self):
        output = self.work / "low-contrast.png"
        write_png(
            output,
            minimal_metadata(
                background_color="#ffffff",
                foreground_color="#eeeeee",
            ),
        )
        result = validate_visual(output)
        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"]["base_contrast"])
        self.assertTrue(any("contrast" in error for error in result["errors"]))

    def test_cjk_without_loadable_font_is_rejected(self):
        output = self.work / "missing-cjk-font.png"
        write_png(
            output,
            minimal_metadata(
                cjk_required="true",
                font_path="/definitely/not/a/font.ttc",
            ),
        )
        result = validate_visual(output)
        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"]["cjk_font"])

    def test_invalid_content_boundary_is_rejected(self):
        output = self.work / "unsafe.png"
        write_png(output, minimal_metadata(content_bbox="[0,0,400,400]"))
        result = validate_visual(output)
        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"]["content_boundary"])

    def test_supplied_render_spec_digest_detects_mismatch(self):
        spec = {
            "version": "1.0",
            "kind": "trend",
            "title": "Original",
            "data": {"points": [1, 2, 3]},
            "meta": {"source": "fixture", "timestamp": "now"},
        }
        output = self.work / "trend.png"
        V.render(spec, output)
        changed = dict(spec)
        changed["title"] = "Changed"
        result = validate_visual(output, changed, allow_unverified=True)
        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"]["render_spec_digest"])
        self.assertFalse(result["checks"]["title_matches_spec"])

    def test_missing_artifact_has_structured_failure(self):
        result = validate_visual(self.work / "missing.png")
        self.assertFalse(result["ok"])
        self.assertEqual(result["checks"], {"exists": False})

    def test_standalone_artifact_requires_explicit_unverified_override(self):
        spec = {
            "version": "1.0",
            "kind": "trend",
            "title": "Prototype",
            "data": {"points": [1, 2, 3]},
            "meta": {"source": "fixture", "timestamp": "now"},
        }
        output = self.work / "prototype.png"
        V.render(spec, output)
        strict = validate_visual(output, spec)
        self.assertFalse(strict["ok"])
        self.assertFalse(strict["checks"]["traceability"])
        allowed = validate_visual(output, spec, allow_unverified=True)
        self.assertTrue(allowed["ok"], allowed)
        self.assertTrue(allowed["warnings"])


if __name__ == "__main__":
    unittest.main()
