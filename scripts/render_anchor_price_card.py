#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:
    raise SystemExit("Pillow is required: python3 -m pip install pillow") from exc


WIDTH = 1200
HEIGHT = 720
BG = (17, 24, 36)
PANEL = (25, 35, 51)
PANEL_2 = (14, 21, 33)
LINE = (48, 61, 80)
MUTED = (137, 151, 172)
TEXT = (236, 241, 247)
GREEN = (51, 221, 127)
ACCENT = (246, 170, 63)


FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def draw_text(draw: ImageDraw.ImageDraw, xy, value: str, size: int, fill=TEXT, bold: bool = False):
    draw.text(xy, value, font=get_font(size, bold=bold), fill=fill)


def money(value: float) -> str:
    return f"${value:,.2f}"


def render(args: argparse.Namespace) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), (8, 12, 18))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((28, 28, WIDTH - 28, HEIGHT - 28), radius=34, fill=BG)
    draw.rectangle((28, 28, 40, HEIGHT - 28), fill=ACCENT)

    draw_text(draw, (70, 70), "DE WRAPPED ASSET ALERT", 25, MUTED, bold=True)
    draw_text(draw, (70, 128), args.pair, 54, TEXT, bold=True)
    draw_text(draw, (70, 188), f"#{args.sequence} - {args.severity} - {args.timestamp}", 21, MUTED, bold=True)

    draw.rounded_rectangle((70, 230, 540, 354), radius=18, fill=PANEL, outline=LINE, width=2)
    draw_text(draw, (100, 266), "DISCOUNT" if args.discount >= 0 else "PREMIUM", 22, MUTED, bold=True)
    draw_text(draw, (100, 304), f"{abs(args.discount):.2f}%", 48, ACCENT, bold=True)

    draw.rounded_rectangle((585, 230, 1130, 354), radius=18, fill=PANEL, outline=LINE, width=2)
    draw_text(draw, (615, 266), "NET / 100K", 22, MUTED, bold=True)
    draw_text(draw, (615, 304), f"${args.net_100k:,.0f}", 48, GREEN, bold=True)

    small = [
        ("CURRENT", money(args.current)),
        (f"FAIR {args.method}", money(args.fair)),
        ("REDEEM", args.redeem),
        ("HEDGE", args.hedge),
    ]
    box_w = 255
    for i, (label, value) in enumerate(small):
        x = 70 + i * (box_w + 20)
        draw.rounded_rectangle((x, 386, x + box_w, 474), radius=16, fill=PANEL_2, outline=LINE, width=2)
        draw_text(draw, (x + 24, 410), label, 18, MUTED, bold=True)
        draw_text(draw, (x + 24, 440), value, 25, TEXT, bold=True)

    draw_text(draw, (70, 520), "Profit ladder", 32, TEXT, bold=True)
    ladder = [
        ("10k", args.net_100k * 0.095),
        ("50k", args.net_100k * 0.525),
        ("100k", args.net_100k),
    ]
    max_net = max(v for _, v in ladder) or 1
    for i, (label, net) in enumerate(ladder):
        y = 575 + i * 34
        draw_text(draw, (70, y - 8), label, 21, MUTED, bold=True)
        draw.rounded_rectangle((150, y, 780, y + 18), radius=9, fill=(43, 51, 70))
        draw.rounded_rectangle((150, y, 150 + int(630 * net / max_net), y + 18), radius=9, fill=GREEN)
        draw_text(draw, (820, y - 8), f"${net:,.0f}", 21, TEXT, bold=True)

    draw_text(draw, (70, HEIGHT - 38), f"{args.venue} - {args.source_note}", 20, MUTED)
    return img


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a Telegram anchor-price alert card.")
    parser.add_argument("--out", required=True)
    parser.add_argument("--pair", default="rswETH / ETH")
    parser.add_argument("--sequence", default="2/3")
    parser.add_argument("--severity", default="P1")
    parser.add_argument("--timestamp", default="05-21 15:41 SGT")
    parser.add_argument("--discount", type=float, default=1.56)
    parser.add_argument("--current", type=float, default=3210.0)
    parser.add_argument("--fair", type=float, default=3261.0)
    parser.add_argument("--method", default="7D P95")
    parser.add_argument("--net-100k", type=float, default=800.0)
    parser.add_argument("--redeem", default="10d")
    parser.add_argument("--hedge", default="YES")
    parser.add_argument("--venue", default="Curve/Uniswap V3")
    parser.add_argument("--source-note", default="Swell LRT redeem 7-14d")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    render(args).save(out)


if __name__ == "__main__":
    main()
