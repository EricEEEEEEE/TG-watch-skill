from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "scripts" / "render_anchor_price_card.py"


class AnchorRendererTests(unittest.TestCase):
    def test_renders_light_and_dark_cjk_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for theme in ("light", "dark"):
                out = Path(tmp) / f"anchor-{theme}.png"
                subprocess.run(
                    [
                        "python3",
                        str(RENDERER),
                        "--out",
                        str(out),
                        "--demo",
                        "--theme",
                        theme,
                        "--eyebrow",
                        "价值锚定观察",
                        "--pair",
                        "测试资产 / 基准",
                        "--venue",
                        "示例市场",
                        "--source-note",
                        "测试数据，不代表真实价格",
                    ],
                    check=True,
                    cwd=ROOT,
                )
                with Image.open(out) as image:
                    self.assertEqual(image.width, 1200)
                    self.assertGreater(image.height, 500)
                    self.assertEqual(image.format, "PNG")

    def test_refuses_to_invent_business_values_without_explicit_demo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    "python3",
                    str(RENDERER),
                    "--out",
                    str(Path(tmp) / "anchor.png"),
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing caller-supplied visual inputs", result.stderr)


if __name__ == "__main__":
    unittest.main()
