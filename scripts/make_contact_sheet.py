#!/usr/bin/env python3
"""Build a deterministic visual-review contact sheet from PNG/GIF artifacts."""
from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any, Iterable, List, Sequence, Tuple

from PIL import Image, ImageDraw, PngImagePlugin

try:
    import render_visual as V
except ImportError:  # pragma: no cover
    from . import render_visual as V


def _thumbnail(path: Path, size: Tuple[int, int]) -> Tuple[Image.Image, str]:
    with Image.open(path) as source:
        frame_count = int(getattr(source, "n_frames", 1))
        source.seek(0)
        image = source.convert("RGB")
        image.thumbnail(size, Image.Resampling.LANCZOS)
        label = str(source.format or path.suffix.lstrip(".")).upper()
        if frame_count > 1:
            label += f" · {frame_count} frames"
        return image.copy(), label


def make_contact_sheet(
    inputs: Sequence[Any],
    output: Any,
    *,
    columns: int = 3,
    cell_width: int = 420,
    cell_height: int = 330,
) -> Path:
    paths = [Path(item) for item in inputs]
    if not paths:
        raise V.RenderSpecError("contact sheet needs at least one input")
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise V.RenderSpecError("missing contact-sheet inputs: " + ", ".join(missing))
    columns = max(1, min(6, int(columns)))
    rows = int(math.ceil(len(paths) / columns))
    gap = 22
    outer = 30
    title_h = 70
    width = outer * 2 + columns * cell_width + (columns - 1) * gap
    height = outer * 2 + title_h + rows * cell_height + (rows - 1) * gap
    pal = V.L.light_palette()
    image = Image.new("RGB", (width, height), pal.bg)
    draw = ImageDraw.Draw(image)
    heading = "TG WATCH · VISUAL REVIEW"
    draw.text((outer, outer), heading, font=V.font(heading, 28, True), fill=pal.text)
    for index, path in enumerate(paths):
        row, column = divmod(index, columns)
        x = outer + column * (cell_width + gap)
        y = outer + title_h + row * (cell_height + gap)
        draw.rounded_rectangle(
            (x, y, x + cell_width, y + cell_height),
            radius=18,
            fill=pal.card,
            outline=pal.line,
            width=2,
        )
        thumb, format_label = _thumbnail(path, (cell_width - 30, cell_height - 82))
        tx = x + (cell_width - thumb.width) // 2
        ty = y + 16 + (cell_height - 82 - thumb.height) // 2
        image.paste(thumb, (tx, ty))
        V.fit_text(
            draw,
            (x + 16, y + cell_height - 52),
            path.name,
            max_width=cell_width - 150,
            size=16,
            min_size=11,
            color=pal.text,
            bold=True,
        )
        draw.text(
            (x + cell_width - 16, y + cell_height - 52),
            format_label,
            font=V.font(format_label, 13, True),
            fill=pal.muted,
            anchor="ra",
        )
    out = Path(output)
    if out.suffix.lower() != ".png":
        raise V.RenderSpecError("contact sheet output must use .png")
    out.parent.mkdir(parents=True, exist_ok=True)
    info = PngImagePlugin.PngInfo()
    info.add_text("artifact_kind", "contact-sheet")
    info.add_text("item_count", str(len(paths)))
    info.add_text("source_files", "\n".join(str(path) for path in paths))
    image.save(out, format="PNG", optimize=True, pnginfo=info)
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a PNG contact sheet for visual QA.")
    parser.add_argument("--input", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--cell-width", type=int, default=420)
    parser.add_argument("--cell-height", type=int, default=330)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(
        make_contact_sheet(
            args.input,
            args.out,
            columns=args.columns,
            cell_width=args.cell_width,
            cell_height=args.cell_height,
        )
    )


if __name__ == "__main__":
    main()
