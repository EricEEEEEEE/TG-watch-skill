from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import layout as L  # noqa: E402


class LayoutTests(unittest.TestCase):
    def test_wrap_text_handles_hard_newlines(self) -> None:
        lines = L.wrap_text("first line\nsecond line", 24, False, 320, 3)
        self.assertEqual(lines, ["first line", "second line"])

    def test_wrap_text_handles_long_cjk_without_tofu_crash(self) -> None:
        lines = L.wrap_text(
            "这是一个用于验证中文自动换行能力的长标题，必须在移动端保持完整可读。",
            28,
            True,
            260,
            4,
        )
        self.assertGreaterEqual(len(lines), 2)
        self.assertLessEqual(len(lines), 4)

    def test_hangul_is_routed_to_wide_script_fonts(self) -> None:
        self.assertTrue(L._has_hangul("한국어 시각 시스템"))
        self.assertTrue(L._has_cjk("한국어 시각 시스템"))
        lines = L.wrap_text("한국어시각시스템모바일검증", 28, True, 150, 5)
        self.assertGreaterEqual(len(lines), 2)

    def test_unbroken_latin_token_is_split_inside_the_measured_width(self) -> None:
        token = "A" * 160
        lines = L.wrap_text(token, 28, True, 180, 40)
        font = L.pick_font(token, 28, True)
        self.assertEqual("".join(lines), token)
        self.assertTrue(all(L._text_w(line, font) <= 180 for line in lines))

    def test_render_card_computes_height_from_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "card.png"
            pal = L.light_palette()
            L.render_card(
                out,
                palette=pal,
                width=600,
                children=[
                    L.Text("视觉结论", 36, pal.text, bold=True),
                    L.Gap(16),
                    L.Text("Evidence " * 20, 22, pal.muted, max_lines=5),
                ],
            )
            with Image.open(out) as image:
                self.assertEqual(image.width, 600)
                self.assertGreater(image.height, 200)


if __name__ == "__main__":
    unittest.main()
