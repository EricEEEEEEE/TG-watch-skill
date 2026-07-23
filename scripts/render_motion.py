#!/usr/bin/env python3
"""Deterministic animated-GIF sequence renderer for RenderSpec."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

from PIL import Image, ImageDraw

try:
    import render_visual as V
except ImportError:  # pragma: no cover
    from . import render_visual as V


def _status_color(status: str, pal: Any) -> Tuple[int, int, int]:
    key = status.strip().lower()
    if key in {"good", "ok", "complete", "completed", "green"}:
        return pal.good
    if key in {"warn", "warning", "watch", "yellow"}:
        return pal.warn
    if key in {"bad", "critical", "error", "red"}:
        return pal.bad
    return pal.accent


def _normalize_frames(data: Mapping[str, Any]) -> List[Dict[str, Any]]:
    raw_frames = data.get("frames")
    if raw_frames is None and isinstance(data.get("points"), list):
        raw_frames = data["points"]
    if not isinstance(raw_frames, list) or len(raw_frames) < 3:
        raise V.RenderSpecError("sequence requires at least three data.frames")
    maximum = max(3, min(24, int(data.get("max_frames", 24))))
    if len(raw_frames) > maximum:
        raise V.RenderSpecError(
            f"sequence has {len(raw_frames)} frames; maximum is {maximum}; "
            "split the sequence instead of silently omitting frames"
        )
    result = []
    for index, raw in enumerate(raw_frames):
        if isinstance(raw, Mapping):
            item = dict(raw)
        else:
            item = {"value": raw}
        item["label"] = str(item.get("label", item.get("title", f"Step {index + 1}")))
        item["note"] = str(item.get("note", ""))
        item["status"] = str(item.get("status", ""))
        if "value" in item and item["value"] is not None:
            if isinstance(item["value"], (int, float)):
                item["value_text"] = V.format_value(
                    V.number(item["value"], f"data.frames[{index}].value"),
                    data,
                )
            else:
                item["value_text"] = str(item["value"])
        else:
            item["value_text"] = ""
        item["duration_ms"] = max(
            200,
            min(5000, int(item.get("duration_ms", data.get("duration_ms", 1800)))),
        )
        result.append(item)
    return result


def _normalize_durations(frames: List[Dict[str, Any]]) -> List[int]:
    """Scale frame timing into Telegram's auditable 6–12 second motion window."""
    original = [int(frame["duration_ms"]) for frame in frames]
    minimums = [200] * len(frames)
    minimums[-1] = 1500
    target = max(6000, min(12000, sum(original)))
    target = max(target, sum(minimums))
    weights = [max(1, value - minimum) for value, minimum in zip(original, minimums)]
    distributable = target - sum(minimums)
    weight_total = sum(weights)
    allocations = [
        int(distributable * weight / weight_total)
        for weight in weights
    ]
    durations = [
        minimum + allocation
        for minimum, allocation in zip(minimums, allocations)
    ]
    durations[-1] += target - sum(durations)
    durations = [int(round(duration / 10.0)) * 10 for duration in durations]
    durations[-1] += target - sum(durations)
    return durations


def _threshold_context(
    data: Mapping[str, Any],
    frames: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if "threshold" not in data:
        return {}
    threshold = V.number(data["threshold"], "data.threshold")
    values = []
    for index, frame in enumerate(frames):
        if "value" not in frame or frame["value"] is None:
            raise V.RenderSpecError(
                "numeric data.threshold requires numeric values in every sequence frame"
            )
        values.append(V.number(frame["value"], f"data.frames[{index}].value"))
    explicit_domain = data.get("domain")
    if (
        isinstance(explicit_domain, (list, tuple))
        and len(explicit_domain) == 2
    ):
        low = V.number(explicit_domain[0], "data.domain[0]")
        high = V.number(explicit_domain[1], "data.domain[1]")
        outside = [
            value
            for value in values + [threshold]
            if value < low or value > high
        ]
        if outside:
            raise V.RenderSpecError(
                "data.domain excludes sequence frame values or threshold"
            )
    else:
        low = min(values + [threshold])
        high = max(values + [threshold])
        spread = high - low
        padding = spread * 0.08 if spread else max(abs(high) * 0.1, 1.0)
        low -= padding
        high += padding
    if high <= low:
        raise V.RenderSpecError("sequence shared-scale domain must increase")
    return {
        "threshold": threshold,
        "values": values,
        "domain": (low, high),
    }


def _scale_x(value: float, domain: Tuple[float, float], left: int, right: int) -> int:
    ratio = (value - domain[0]) / (domain[1] - domain[0])
    return int(left + V.clamp(ratio, 0.0, 1.0) * (right - left))


def _motion_axis_value(value: float, data: Mapping[str, Any]) -> str:
    if value and (abs(value) >= 1_000_000 or abs(value) < 0.001):
        suffix = str(data.get("suffix", data.get("unit", "")))
        spacer = " " if suffix and not suffix.startswith(("%", "x", "°")) else ""
        return f"{value:.3g}{spacer}{suffix}".strip()
    tick_data = dict(data)
    tick_data["decimals"] = min(2, int(data.get("decimals", 2)))
    return V.format_value(value, tick_data)


def _draw_frame(
    spec: Mapping[str, Any],
    item: Mapping[str, Any],
    index: int,
    total: int,
    threshold_context: Mapping[str, Any],
) -> Tuple[Image.Image, Tuple[int, int, int, int], Any]:
    image, draw, content, pal = V.canvas(spec, 1150, default_width=1200)
    left, top, right, bottom = content
    color = _status_color(str(item.get("status", "")), pal)
    text_color = V.readable_color(color, pal.panel, pal.text)
    progress = (index + 1) / total

    # Step identity is visible without motion, making every frame meaningful.
    step_label = f"STEP {index + 1} / {total}"
    draw.text(
        (left, top),
        step_label,
        font=V.font(step_label, V.MIN_METADATA_FONT, True),
        fill=pal.muted,
    )
    label = str(item["label"])
    V.fit_text(
        draw,
        (left, top + 52),
        label,
        max_width=right - left,
        size=V.MIN_TITLE_FONT,
        min_size=V.MIN_BODY_FONT,
        color=pal.text,
        bold=True,
    )
    value_text = str(item.get("value_text", ""))
    panel_top = top + 128
    panel_bottom = panel_top + 390
    draw.rounded_rectangle(
        (left, panel_top, right, panel_bottom),
        radius=24,
        fill=pal.panel,
        outline=pal.line,
        width=2,
    )
    if value_text:
        V.fit_text(
            draw,
            (left + 34, panel_top + 40),
            value_text,
            max_width=right - left - 68,
            size=76,
            min_size=48,
            color=text_color,
            bold=True,
        )
    note = str(item.get("note", ""))
    if note:
        lines = V.L.wrap_text(
            note,
            V.MIN_BODY_FONT,
            False,
            right - left - 68,
            2 if threshold_context else 3,
        )
        if any(line.endswith("…") for line in lines):
            image.info["text_truncated"] = "true"
        y = panel_top + (150 if value_text else 58)
        for line in lines:
            draw.text(
                (left + 34, y),
                line,
                font=V.font(line, V.MIN_BODY_FONT),
                fill=pal.muted,
            )
            y += 44
    if item.get("status"):
        status = str(item["status"])
        status_font = V.font(status, V.MIN_METADATA_FONT, True)
        status_w = min(300, int(draw.textlength(status, font=status_font)) + 38)
        draw.rounded_rectangle(
            (right - status_w - 24, panel_top + 22, right - 24, panel_top + 72),
            radius=24,
            fill=color,
        )
        draw.text(
            (right - status_w - 5, panel_top + 30),
            status,
            font=status_font,
            fill=V.accessible_foreground(color),
        )

    if threshold_context:
        data = spec["data"]
        scale_left, scale_right = left + 38, right - 38
        scale_y = panel_bottom - 58
        domain = threshold_context["domain"]
        threshold = threshold_context["threshold"]
        current = threshold_context["values"][index]
        threshold_x = _scale_x(threshold, domain, scale_left, scale_right)
        current_x = _scale_x(current, domain, scale_left, scale_right)
        threshold_color = V.readable_color(pal.muted, pal.panel, pal.text)
        draw.line(
            (scale_left, scale_y, scale_right, scale_y),
            fill=pal.line,
            width=7,
        )
        draw.line(
            (threshold_x, scale_y - 19, threshold_x, scale_y + 19),
            fill=threshold_color,
            width=5,
        )
        draw.ellipse(
            (current_x - 13, scale_y - 13, current_x + 13, scale_y + 13),
            fill=pal.panel,
            outline=pal.accent,
            width=6,
        )
        threshold_text = "THRESHOLD · " + V.format_value(threshold, data)
        V.fit_text(
            draw,
            (scale_left, scale_y - 62),
            threshold_text,
            max_width=scale_right - scale_left,
            size=V.MIN_METADATA_FONT,
            min_size=V.MIN_METADATA_FONT,
            color=threshold_color,
            bold=True,
        )
        low_label = _motion_axis_value(domain[0], data)
        high_label = _motion_axis_value(domain[1], data)
        draw.text(
            (scale_left, scale_y + 24),
            low_label,
            font=V.font(low_label, V.MIN_METADATA_FONT),
            fill=pal.muted,
        )
        draw.text(
            (scale_right, scale_y + 24),
            high_label,
            font=V.font(high_label, V.MIN_METADATA_FONT),
            fill=pal.muted,
            anchor="ra",
        )
        image.info.update(
            {
                "motion_threshold_visible": "true",
                "motion_threshold_value": V.format_value(threshold, data),
                "motion_scale_domain": json.dumps(
                    list(domain),
                    separators=(",", ":"),
                ),
                "threshold_marker_bbox": json.dumps(
                    [threshold_x - 8, scale_y - 22, threshold_x + 8, scale_y + 22],
                    separators=(",", ":"),
                ),
                "motion_scale_bbox": json.dumps(
                    [scale_left, scale_y - 66, scale_right, scale_y + 58],
                    separators=(",", ":"),
                ),
            }
        )

    # Sequence rail: past, current, and future are redundantly encoded by fill and shape.
    rail_y = panel_bottom + 118
    rail_left, rail_right = left + 32, right - 32
    draw.line((rail_left, rail_y, rail_right, rail_y), fill=pal.line, width=8)
    completed_x = int(rail_left + progress * (rail_right - rail_left))
    draw.line((rail_left, rail_y, completed_x, rail_y), fill=color, width=8)
    for step in range(total):
        x = int(rail_left + (step / max(1, total - 1)) * (rail_right - rail_left))
        if step < index:
            draw.ellipse((x - 9, rail_y - 9, x + 9, rail_y + 9), fill=color)
        elif step == index:
            draw.ellipse((x - 15, rail_y - 15, x + 15, rail_y + 15),
                         fill=pal.card, outline=color, width=6)
        else:
            draw.ellipse((x - 8, rail_y - 8, x + 8, rail_y + 8),
                         fill=pal.card, outline=pal.line, width=3)
    draw.text(
        (rail_left, rail_y + 35),
        str(spec["data"].get("start_label", "Start")),
        font=V.font("Start", V.MIN_METADATA_FONT),
        fill=pal.muted,
    )
    draw.text(
        (rail_right, rail_y + 35),
        str(spec["data"].get("end_label", "End")),
        font=V.font("End", V.MIN_METADATA_FONT),
        fill=pal.muted,
        anchor="ra",
    )
    return image, content, pal


def render_motion(spec_source: Any, output: Any) -> Path:
    spec = V.load_render_spec(spec_source)
    if spec["kind"] != "sequence":
        raise V.RenderSpecError(f"{spec['kind']} is not a motion kind")
    out = Path(output)
    if out.suffix.lower() != ".gif":
        raise V.RenderSpecError("sequence visuals must use a .gif output path")
    frames_data = _normalize_frames(spec["data"])
    threshold_context = _threshold_context(spec["data"], frames_data)
    rendered_rgb = []
    content = None
    pal = None
    for index, item in enumerate(frames_data):
        image, content, pal = _draw_frame(
            spec,
            item,
            index,
            len(frames_data),
            threshold_context,
        )
        rendered_rgb.append(image)
    durations = _normalize_durations(frames_data)
    poster = out.with_name(f"{out.stem}-poster.png")
    final = out.with_name(f"{out.stem}-final.png")
    threshold_metadata = {
        key: value
        for key, value in rendered_rgb[0].info.items()
        if key.startswith("motion_") or key == "threshold_marker_bbox"
    }
    V.save_png(
        rendered_rgb[0],
        poster,
        spec,
        content,
        pal,
        extra_metadata={
            "motion_role": "poster",
            "motion_source": out.name,
            **threshold_metadata,
        },
    )
    V.save_png(
        rendered_rgb[-1],
        final,
        spec,
        content,
        pal,
        extra_metadata={
            "motion_role": "final",
            "motion_source": out.name,
            **threshold_metadata,
        },
    )
    rendered = [
        image.convert("P", palette=Image.Palette.ADAPTIVE, colors=255)
        for image in rendered_rgb
    ]
    metadata = V.metadata_for(spec, content, pal)
    metadata["card_bbox"] = str(rendered_rgb[0].info.get("card_bbox", ""))
    metadata.update({str(key): str(value) for key, value in threshold_metadata.items()})
    metadata["text_truncated"] = (
        "true"
        if any(frame.info.get("text_truncated") == "true" for frame in rendered_rgb)
        else "false"
    )
    metadata.update(
        {
            "frame_count": str(len(rendered)),
            "first_frame_label": str(frames_data[0]["label"]),
            "last_frame_label": str(frames_data[-1]["label"]),
            "total_duration_ms": str(sum(durations)),
            "poster_artifact": poster.name,
            "final_artifact": final.name,
        }
    )
    comment = ("tg-watch:" + json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))).encode("utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    rendered[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=rendered[1:],
        duration=durations,
        loop=0,
        disposal=2,
        optimize=False,
        comment=comment,
    )
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a sequence RenderSpec or bundle to animated GIF.")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(render_motion(args.spec, args.out))


if __name__ == "__main__":
    main()
