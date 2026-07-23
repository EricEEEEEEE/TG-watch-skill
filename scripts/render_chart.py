#!/usr/bin/env python3
"""Static chart recipes for the TG Watch RenderSpec renderer."""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from PIL import ImageDraw

try:
    import render_visual as V
except ImportError:  # pragma: no cover
    from . import render_visual as V

RGB = Tuple[int, int, int]


def _item_value(item: Any, field: str) -> float:
    if isinstance(item, Mapping):
        return V.number(item.get("value"), field)
    return V.number(item, field)


def _domain(values: Sequence[float], explicit: Any = None) -> Tuple[float, float]:
    if isinstance(explicit, Sequence) and not isinstance(explicit, str) and len(explicit) == 2:
        low = V.number(explicit[0], "data.domain[0]")
        high = V.number(explicit[1], "data.domain[1]")
        outside = [value for value in values if value < low or value > high]
        if outside:
            raise V.RenderSpecError(
                "data.domain excludes plotted values: "
                + ", ".join(f"{value:g}" for value in outside[:4])
            )
    else:
        low, high = min(values), max(values)
        spread = high - low
        pad = spread * 0.12 if spread else max(abs(high) * 0.1, 1.0)
        low, high = low - pad, high + pad
    if high <= low:
        raise V.RenderSpecError("chart domain maximum must be greater than minimum")
    return low, high


def _x(value: float, domain: Tuple[float, float], left: int, right: int) -> int:
    ratio = (value - domain[0]) / (domain[1] - domain[0])
    return int(left + V.clamp(ratio, 0.0, 1.0) * (right - left))


def _axis_value(value: float, data: Mapping[str, Any]) -> str:
    """Format derived ticks compactly while leaving source values lossless."""
    if value and (abs(value) >= 1_000_000 or abs(value) < 0.001):
        body = f"{value:.3g}"
        prefix = str(data.get("prefix", ""))
        suffix = str(data.get("suffix", data.get("unit", "")))
        spacer = " " if suffix and not suffix.startswith(("%", "x", "°")) else ""
        return f"{prefix}{body}{spacer}{suffix}".strip()
    tick_data = dict(data)
    tick_data["decimals"] = min(2, int(data.get("decimals", 2)))
    return V.format_value(value, tick_data)


def _draw_interval_endpoint_labels(
    draw: ImageDraw.ImageDraw,
    *,
    low_x: int,
    high_x: int,
    y: int,
    low_text: str,
    high_text: str,
    color: RGB,
) -> Tuple[str, List[List[int]], int]:
    """Draw exact interval endpoints with a guaranteed visual separation."""
    label_font = V.font(low_text + high_text, V.MIN_METADATA_FONT)
    low_box = draw.textbbox(
        (low_x, y),
        low_text,
        font=label_font,
        anchor="lt",
    )
    high_box = draw.textbbox(
        (high_x, y),
        high_text,
        font=label_font,
        anchor="rt",
    )
    horizontal_gap = high_box[0] - low_box[2]
    mode = "inline"
    if horizontal_gap < 18:
        mode = "staggered"
        high_y = low_box[3] + 18
        high_box = draw.textbbox(
            (high_x, high_y),
            high_text,
            font=label_font,
            anchor="rt",
        )
        gap = high_box[1] - low_box[3]
    else:
        high_y = y
        gap = horizontal_gap
    draw.text(
        (low_x, y),
        low_text,
        font=label_font,
        fill=color,
        anchor="lt",
    )
    draw.text(
        (high_x, high_y),
        high_text,
        font=label_font,
        fill=color,
        anchor="rt",
    )
    return (
        mode,
        [list(map(int, low_box)), list(map(int, high_box))],
        int(gap),
    )


def _axis_scalar(value: Any) -> Tuple[float, str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return V.number(value, "trend x"), "numeric"
    text = str(value).strip()
    try:
        return float(text), "numeric"
    except ValueError:
        pass
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            return parsed.timestamp(), "time"
        deterministic_seconds = (
            parsed.toordinal() * 86400
            + parsed.hour * 3600
            + parsed.minute * 60
            + parsed.second
            + parsed.microsecond / 1_000_000
        )
        return deterministic_seconds, "time"
    except ValueError:
        pass
    for pattern in ("%H:%M", "%H:%M:%S"):
        try:
            parsed = datetime.strptime(text, pattern)
            return (
                parsed.hour * 3600 + parsed.minute * 60 + parsed.second,
                "time",
            )
        except ValueError:
            continue
    raise ValueError(text)


def _trend_x_values(raw_points: Sequence[Any], labels: Sequence[str]) -> Tuple[List[float], str]:
    explicit = []
    has_explicit = False
    for raw in raw_points:
        if isinstance(raw, Mapping) and any(key in raw for key in ("x", "time", "timestamp")):
            has_explicit = True
            explicit.append(raw.get("x", raw.get("time", raw.get("timestamp"))))
        else:
            explicit.append(None)
    candidates = explicit if has_explicit else list(labels)
    parsed = []
    modes = set()
    for candidate in candidates:
        if candidate is None:
            if has_explicit:
                raise V.RenderSpecError("trend points must all provide x/time/timestamp")
            return [float(index) for index in range(len(labels))], "categorical"
        try:
            value, mode = _axis_scalar(candidate)
        except ValueError:
            if has_explicit:
                raise V.RenderSpecError(f"unparseable trend x value: {candidate!r}")
            return [float(index) for index in range(len(labels))], "categorical"
        parsed.append(value)
        modes.add(mode)
    if len(modes) > 1:
        raise V.RenderSpecError("trend x values mix numeric and time scales")
    if any(right <= left for left, right in zip(parsed, parsed[1:])):
        raise V.RenderSpecError("trend x values must be strictly increasing in source order")
    return parsed, next(iter(modes), "categorical")


def _pill(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    text: str,
    *,
    bg: RGB,
    fg: RGB,
    max_width: int = 300,
) -> None:
    x, y = xy
    label_font = V.font(text, V.MIN_METADATA_FONT, True)
    width = min(max_width, int(draw.textlength(text, font=label_font)) + 34)
    draw.rounded_rectangle((x, y, x + width, y + 52), radius=26, fill=bg)
    draw.text((x + 17, y + 9), text, font=label_font, fill=fg)


def _hero(
    draw: ImageDraw.ImageDraw,
    box: Tuple[int, int, int, int],
    label: str,
    value: str,
    *,
    pal: Any,
    value_color: RGB = None,
    note: str = "",
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=20, fill=pal.panel, outline=pal.line, width=2)
    draw.text(
        (x1 + 28, y1 + 24),
        label,
        font=V.font(label, V.MIN_BODY_FONT, True),
        fill=pal.muted,
    )
    V.fit_text(
        draw,
        (x1 + 28, y1 + 75),
        value,
        max_width=x2 - x1 - 48,
        size=62,
        min_size=42,
        color=V.readable_color(value_color or pal.text, pal.panel, pal.text),
        bold=True,
    )
    if note:
        note_lines = V.L.wrap_text(
            note,
            V.MIN_METADATA_FONT,
            False,
            x2 - x1 - 48,
            2,
        )
        if any(line.endswith("…") for line in note_lines):
            draw._image.info["text_truncated"] = "true"
        note_y = y2 - 40 - (len(note_lines) - 1) * 38
        for line in note_lines:
            draw.text(
                (x1 + 28, note_y),
                line,
                font=V.font(line, V.MIN_METADATA_FONT),
                fill=pal.muted,
            )
            note_y += 38


def _render_anchor(spec: Mapping[str, Any], output: Any) -> Path:
    data = spec["data"]
    current = _item_value(data.get("current"), "data.current")
    raw_anchors = data.get("anchors", [])
    if (not raw_anchors) and "anchor" in data:
        raw_anchor = data["anchor"]
        if isinstance(raw_anchor, Mapping):
            raw_anchors = [dict(raw_anchor)]
        else:
            raw_anchors = [
                {
                    "label": str(data.get("anchor_label", "Anchor")),
                    "value": raw_anchor,
                    "primary": True,
                }
            ]
    if not isinstance(raw_anchors, list) or not raw_anchors:
        raise V.RenderSpecError("anchor visual requires data.anchors")
    anchors: List[Dict[str, Any]] = []
    for index, raw in enumerate(raw_anchors):
        if not isinstance(raw, Mapping):
            raise V.RenderSpecError("each anchor must be an object")
        anchors.append(
            {
                "label": str(raw.get("label", f"Anchor {index + 1}")),
                "value": _item_value(raw, f"data.anchors[{index}].value"),
                "primary": bool(raw.get("primary", index == 0)),
                "color": V.parse_color(raw.get("color"), (120, 132, 149)),
            }
        )
    bands = data.get("bands", [])
    if not isinstance(bands, list):
        raise V.RenderSpecError("data.bands must be an array")
    values = [current] + [item["value"] for item in anchors]
    parsed_bands = []
    for index, band in enumerate(bands):
        if not isinstance(band, Mapping):
            raise V.RenderSpecError("each band must be an object")
        low = V.number(band.get("low"), f"data.bands[{index}].low")
        high = V.number(band.get("high"), f"data.bands[{index}].high")
        if high < low:
            low, high = high, low
        values.extend([low, high])
        parsed_bands.append(
            {
                "label": str(band.get("label", "Range")),
                "low": low,
                "high": high,
                "color": V.parse_color(band.get("color"), (191, 219, 254)),
            }
        )
    domain = _domain(values, data.get("domain"))
    image, draw, content, pal = V.canvas(spec, 980)
    left, top, right, bottom = content
    primary = next((item for item in anchors if item["primary"]), anchors[0])
    current_decimal = Decimal(str(current))
    primary_decimal = Decimal(str(primary["value"]))
    delta = current_decimal - primary_decimal
    delta_pct = delta / primary_decimal * 100 if primary_decimal else None
    note = f"Δ {V.format_value(delta, data)}"
    if delta_pct is not None and abs(delta_pct) <= Decimal("9999"):
        note += f" ({delta_pct:+.1f}%)"
    _hero(
        draw,
        (left, top, left + int((right - left) * 0.49), top + 210),
        str(data.get("current_label", "CURRENT")),
        V.format_value(current, data),
        pal=pal,
        value_color=pal.accent,
        note=note,
    )
    _hero(
        draw,
        (left + int((right - left) * 0.52), top, right, top + 210),
        "PRIMARY ANCHOR",
        V.format_value(primary["value"], data),
        pal=pal,
        note=primary["label"],
    )

    axis_left, axis_right = left + 46, right - 46
    track_y = top + 405
    axis_label = str(data.get("axis_label", "Value range"))
    draw.text((axis_left, top + 292), axis_label,
              font=V.font(axis_label, 38, True), fill=pal.text)
    draw.rounded_rectangle(
        (axis_left, track_y, axis_right, track_y + 30),
        radius=15,
        fill=pal.line,
    )
    for band in parsed_bands:
        bx1 = _x(band["low"], domain, axis_left, axis_right)
        bx2 = _x(band["high"], domain, axis_left, axis_right)
        band_color = V.visible_mark_color(band["color"], pal.card, pal.accent)
        draw.rounded_rectangle((bx1, track_y, max(bx1 + 8, bx2), track_y + 30),
                               radius=15, fill=band_color)
        V.fit_text(
            draw,
            ((bx1 + bx2) // 2, track_y + 65),
            band["label"],
            max_width=max(80, bx2 - bx1 + 80),
            size=V.MIN_METADATA_FONT,
            min_size=V.MIN_METADATA_FONT,
            color=pal.muted,
            anchor="ma",
        )

    markers = anchors + [
        {
            "label": str(data.get("current_label", "Current")),
            "value": current,
            "color": pal.accent,
            "primary": False,
            "current": True,
        }
    ]
    for index, marker in enumerate(markers):
        mx = _x(marker["value"], domain, axis_left, axis_right)
        is_current = bool(marker.get("current"))
        color = V.visible_mark_color(
            marker["color"] if not is_current else pal.accent,
            pal.card,
            pal.accent,
        )
        label_color = V.readable_color(color, pal.card, pal.text)
        draw.line((mx, track_y - 22, mx, track_y + 50), fill=color, width=5 if is_current else 3)
        draw.ellipse((mx - 8, track_y + 7, mx + 8, track_y + 23), fill=color)
        label_y = track_y - 106 if index % 2 == 0 else track_y + 105
        value_y = label_y + 40
        marker_anchor = (
            "la"
            if mx <= axis_left + (axis_right - axis_left) * 0.25
            else "ra"
            if mx >= axis_left + (axis_right - axis_left) * 0.75
            else "ma"
        )
        draw.text((mx, label_y), marker["label"],
                  font=V.font(marker["label"], V.MIN_METADATA_FONT, True),
                  fill=label_color, anchor=marker_anchor)
        draw.text((mx, value_y), V.format_value(marker["value"], data),
                  font=V.font("0", V.MIN_METADATA_FONT, True),
                  fill=pal.text, anchor=marker_anchor)

    draw.text((axis_left, bottom - 55), V.format_value(domain[0], data),
              font=V.font("0", V.MIN_METADATA_FONT), fill=pal.muted)
    draw.text((axis_right, bottom - 55), V.format_value(domain[1], data),
              font=V.font("0", V.MIN_METADATA_FONT), fill=pal.muted, anchor="ra")
    return V.save_png(image, output, spec, content, pal, extra_metadata={"item_count": len(markers)})


def _render_threshold(spec: Mapping[str, Any], output: Any) -> Path:
    data = spec["data"]
    value = _item_value(data.get("value"), "data.value")
    raw_thresholds = data.get("thresholds")
    if raw_thresholds is None and "threshold" in data:
        raw_thresholds = [{"label": "Threshold", "value": data["threshold"]}]
    if not isinstance(raw_thresholds, list) or not raw_thresholds:
        raise V.RenderSpecError("threshold visual requires data.threshold or data.thresholds")
    thresholds = []
    for index, raw in enumerate(raw_thresholds):
        if isinstance(raw, Mapping):
            threshold_value = _item_value(raw, f"data.thresholds[{index}].value")
            label = str(raw.get("label", f"Threshold {index + 1}"))
            requested_color = V.parse_color(raw.get("color"), (217, 119, 6))
            color = requested_color
        else:
            threshold_value = V.number(raw, f"data.thresholds[{index}]")
            label = f"Threshold {index + 1}"
            color = (217, 119, 6)
        thresholds.append({"value": threshold_value, "label": label, "color": color})
    values = [value] + [item["value"] for item in thresholds]
    domain = _domain(values, data.get("domain"))
    image, draw, content, pal = V.canvas(spec, 900)
    left, top, right, bottom = content
    status = str(data.get("status", "")).strip()
    _hero(
        draw,
        (left, top, right, top + 210),
        str(data.get("value_label", "CURRENT VALUE")),
        V.format_value(value, data),
        pal=pal,
        value_color=V.readable_color(
            V.parse_color(data.get("value_color"), pal.accent),
            pal.panel,
            pal.text,
        ),
        note=status,
    )
    track_left, track_right = left + 48, right - 48
    track_y = top + 390
    axis_label = str(data.get("axis_label", "Threshold distance"))
    draw.text((track_left, top + 258), axis_label,
              font=V.font(axis_label, 38, True), fill=pal.text)
    draw.rounded_rectangle((track_left, track_y, track_right, track_y + 38),
                           radius=19, fill=pal.line)
    vx = _x(value, domain, track_left, track_right)
    fill_left, fill_right = min(track_left, vx), max(track_left, vx)
    if fill_right - fill_left > 3:
        draw.rounded_rectangle((fill_left, track_y, fill_right, track_y + 38),
                               radius=19, fill=pal.accent)
    draw.ellipse((vx - 13, track_y + 6, vx + 13, track_y + 32),
                 fill=pal.card, outline=pal.accent, width=5)
    draw.text((vx, track_y - 54), V.format_value(value, data),
              font=V.font("0", V.MIN_BODY_FONT, True), fill=pal.accent, anchor="ma")
    for index, item in enumerate(thresholds):
        mark_color = V.visible_mark_color(item["color"], pal.card, pal.warn)
        text_color = V.readable_color(item["color"], pal.card, pal.text)
        tx = _x(item["value"], domain, track_left, track_right)
        draw.line((tx, track_y - 12, tx, track_y + 63), fill=mark_color, width=4)
        label_y = track_y + 92 + (index % 2) * 78
        draw.text((tx, label_y), item["label"],
                  font=V.font(item["label"], V.MIN_METADATA_FONT, True),
                  fill=text_color, anchor="ma")
        draw.text((tx, label_y + 40), V.format_value(item["value"], data),
                  font=V.font("0", V.MIN_METADATA_FONT), fill=pal.text, anchor="ma")
    draw.text((track_left, bottom - 45), V.format_value(domain[0], data),
              font=V.font("0", V.MIN_METADATA_FONT), fill=pal.muted)
    draw.text((track_right, bottom - 45), V.format_value(domain[1], data),
              font=V.font("0", V.MIN_METADATA_FONT), fill=pal.muted, anchor="ra")
    return V.save_png(image, output, spec, content, pal, extra_metadata={"item_count": len(thresholds)})


def _render_comparison(spec: Mapping[str, Any], output: Any) -> Path:
    data = spec["data"]
    raw_items = data.get("items", [])
    if not isinstance(raw_items, list) or len(raw_items) < 2:
        raise V.RenderSpecError("comparison/ranking requires at least two data.items")
    items = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, Mapping):
            raise V.RenderSpecError("each comparison item must be an object")
        items.append(
            {
                "label": str(raw.get("label", f"Item {index + 1}")),
                "value": _item_value(raw, f"data.items[{index}].value"),
                "note": str(raw.get("note", "")),
                "color": V.parse_color(raw.get("color"), (37, 99, 235)),
            }
        )
    if spec["kind"] == "ranking" and not data.get("preserve_order", False):
        items.sort(key=lambda item: item["value"], reverse=True)
    maximum = int(data.get("max_items", 8))
    if maximum < 2:
        raise V.RenderSpecError("data.max_items must be at least 2")
    if len(items) > maximum:
        raise V.RenderSpecError(
            f"{spec['kind']} has {len(items)} items; maximum is {maximum}; "
            "split the visual instead of silently omitting items"
        )
    values = [item["value"] for item in items]
    domain = _domain(values + [0.0], data.get("domain"))
    row_h = 110
    image, draw, content, pal = V.canvas(spec, 400 + row_h * len(items))
    left, top, right, bottom = content
    label_w = min(
        430,
        max(
            330,
            max(
                int(draw.textlength(
                    f"{index + 1:02d}  {item['label']}"
                    if spec["kind"] == "ranking"
                    else item["label"],
                    font=V.font(item["label"], V.MIN_BODY_FONT, True),
                )) + 34
                for index, item in enumerate(items)
            ),
        ),
    )
    value_w = 190
    bar_left, bar_right = left + label_w, right - value_w
    zero_x = _x(0.0, domain, bar_left, bar_right) if domain[0] <= 0 <= domain[1] else bar_left
    if domain[0] <= 0 <= domain[1]:
        draw.line((zero_x, top, zero_x, bottom - 18), fill=pal.line, width=2)
    for index, item in enumerate(items):
        y = top + index * row_h
        rank = f"{index + 1:02d}" if spec["kind"] == "ranking" else ""
        label = f"{rank}  {item['label']}".strip()
        V.fit_text(draw, (left, y + 15), label, max_width=label_w - 22,
                   size=V.MIN_BODY_FONT, min_size=V.MIN_BODY_FONT,
                   color=pal.text, bold=True)
        vx = _x(item["value"], domain, bar_left, bar_right)
        x1, x2 = sorted((zero_x, vx))
        if x2 - x1 < 5:
            x2 = x1 + 5
        bar_color = V.visible_mark_color(item["color"], pal.card, pal.accent)
        draw.rounded_rectangle((x1, y + 24, x2, y + 68), radius=22,
                               fill=bar_color)
        draw.text((right, y + 23), V.format_value(item["value"], data, compact=True),
                  font=V.font("0", V.MIN_BODY_FONT, True), fill=pal.text, anchor="ra")
        if item["note"]:
            V.fit_text(draw, (bar_left, y + 75), item["note"],
                       max_width=bar_right - bar_left, size=V.MIN_METADATA_FONT,
                       min_size=V.MIN_METADATA_FONT, color=pal.muted)
    return V.save_png(image, output, spec, content, pal, extra_metadata={"item_count": len(items)})


def _render_trend(spec: Mapping[str, Any], output: Any) -> Path:
    data = spec["data"]
    raw_points = data.get("points", [])
    if not isinstance(raw_points, list) or len(raw_points) < 2:
        raise V.RenderSpecError("trend requires at least two data.points")
    points = []
    for index, raw in enumerate(raw_points):
        if isinstance(raw, Mapping):
            value = V.number(raw.get("value", raw.get("y")), f"data.points[{index}].value")
            label = str(raw.get("label", raw.get("x", index + 1)))
        else:
            value = V.number(raw, f"data.points[{index}]")
            label = str(index + 1)
        points.append((label, value))
    values = [point[1] for point in points]
    x_values, x_scale = _trend_x_values(raw_points, [point[0] for point in points])
    domain = _domain(values, data.get("domain"))
    image, draw, content, pal = V.canvas(spec, 980)
    left, top, right, bottom = content
    hero_h = 210
    last = values[-1]
    change = Decimal(str(last)) - Decimal(str(values[0]))
    _hero(
        draw,
        (left, top, right, top + hero_h),
        str(data.get("value_label", "LATEST")),
        V.format_value(last, data),
        pal=pal,
        value_color=pal.accent,
        note=f"period change {V.format_value(change, data)}",
    )
    tick_values = [
        domain[1] - step * (domain[1] - domain[0]) / 4
        for step in range(5)
    ]
    tick_labels = [_axis_value(value, data) for value in tick_values]
    tick_gutter = max(
        118,
        max(
            int(draw.textlength(label, font=V.font(label, V.MIN_METADATA_FONT)))
            for label in tick_labels
        ) + 30,
    )
    plot = (left + tick_gutter, top + hero_h + 72, right - 28, bottom - 62)
    px1, py1, px2, py2 = plot
    for step in range(5):
        gy = int(py1 + step * (py2 - py1) / 4)
        draw.line((px1, gy, px2, gy), fill=pal.line, width=1)
        draw.text((px1 - 16, gy), tick_labels[step],
                  font=V.font("0", V.MIN_METADATA_FONT), fill=pal.muted, anchor="rm")
    coordinates = []
    x_low, x_high = x_values[0], x_values[-1]
    for index, (_, value) in enumerate(points):
        x = px1 + (x_values[index] - x_low) / (x_high - x_low) * (px2 - px1)
        y = py2 - (value - domain[0]) / (domain[1] - domain[0]) * (py2 - py1)
        coordinates.append((int(x), int(y)))
    fill_polygon = [(coordinates[0][0], py2)] + coordinates + [(coordinates[-1][0], py2)]
    fill_color = tuple(int((channel + 255 * 3) / 4) for channel in pal.accent)
    draw.polygon(fill_polygon, fill=fill_color)
    draw.line(coordinates, fill=pal.accent, width=6, joint="curve")
    for x, y in coordinates:
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=pal.card,
                     outline=pal.accent, width=4)
    draw.text((px1, py2 + 18), points[0][0],
              font=V.font(points[0][0], V.MIN_METADATA_FONT),
              fill=pal.muted)
    draw.text((px2, py2 + 18), points[-1][0],
              font=V.font(points[-1][0], V.MIN_METADATA_FONT),
              fill=pal.muted, anchor="ra")
    return V.save_png(
        image,
        output,
        spec,
        content,
        pal,
        extra_metadata={"item_count": len(points), "x_scale": x_scale},
    )


def _render_timeline(spec: Mapping[str, Any], output: Any) -> Path:
    data = spec["data"]
    raw_events = data.get("events", [])
    if not isinstance(raw_events, list) or not raw_events:
        raise V.RenderSpecError("timeline requires data.events")
    maximum = int(data.get("max_items", 9))
    if maximum < 1:
        raise V.RenderSpecError("data.max_items must be at least 1")
    if len(raw_events) > maximum:
        raise V.RenderSpecError(
            f"timeline has {len(raw_events)} events; maximum is {maximum}; "
            "split the visual instead of silently omitting events"
        )
    events = raw_events
    row_h = 150
    image, draw, content, pal = V.canvas(spec, 340 + row_h * len(events))
    left, top, right, bottom = content
    line_x = left + 30
    for index, raw in enumerate(events):
        if not isinstance(raw, Mapping):
            raise V.RenderSpecError("each timeline event must be an object")
        y = top + index * row_h
        label = str(raw.get("label", raw.get("title", f"Event {index + 1}")))
        time_label = str(raw.get("time", raw.get("timestamp", "")))
        note = str(raw.get("note", ""))
        color = V.visible_mark_color(
            V.parse_color(raw.get("color"), pal.accent),
            pal.card,
            pal.accent,
        )
        time_color = V.readable_color(color, pal.card, pal.text)
        if index < len(events) - 1:
            draw.line((line_x, y + 44, line_x, y + row_h + 44), fill=pal.line, width=5)
        draw.ellipse((line_x - 14, y + 30, line_x + 14, y + 58),
                     fill=pal.card, outline=color, width=6)
        if time_label:
            draw.text((line_x + 42, y + 2), time_label,
                      font=V.font(time_label, V.MIN_METADATA_FONT, True), fill=time_color)
        V.fit_text(draw, (line_x + 42, y + 45), label,
                   max_width=right - line_x - 52, size=38, min_size=V.MIN_BODY_FONT,
                   color=pal.text, bold=True)
        if note:
            V.fit_text(draw, (line_x + 42, y + 96), note,
                       max_width=right - line_x - 52, size=V.MIN_BODY_FONT,
                       min_size=V.MIN_BODY_FONT,
                       color=pal.muted)
    return V.save_png(image, output, spec, content, pal, extra_metadata={"item_count": len(events)})


def _render_hero(spec: Mapping[str, Any], output: Any) -> Path:
    data = spec["data"]
    if "value" not in data or data.get("value") is None:
        raise V.RenderSpecError("hero requires data.value")
    raw_value = data["value"]
    if isinstance(raw_value, bool):
        raise V.RenderSpecError("data.value must not be boolean")
    if isinstance(raw_value, (int, float)):
        value_text = V.format_value(V.number(raw_value, "data.value"), data)
    else:
        value_text = str(raw_value)
    image, draw, content, pal = V.canvas(spec, 780)
    left, top, right, bottom = content
    status = str(data.get("status", "")).strip()
    status_lines = []
    if status:
        status_lines = V.L.wrap_text(
            status,
            V.MIN_METADATA_FONT,
            True,
            right - left - 122,
            3,
        )
        if any(line.endswith("…") for line in status_lines):
            raise V.RenderSpecError(
                "data.status needs more than three badge lines; "
                "shorten or split it instead of silently truncating"
            )
        if len(status_lines) > 1:
            image, draw, content, pal = V.canvas(
                spec,
                780 + (len(status_lines) - 1) * 39,
            )
            left, top, right, bottom = content
    panel = (left, top, right, bottom)
    draw.rounded_rectangle(panel, radius=28, fill=pal.panel, outline=pal.line, width=2)
    label = str(data.get("value_label", "CURRENT"))
    draw.text(
        (left + 40, top + 36),
        label,
        font=V.font(label, V.MIN_BODY_FONT, True),
        fill=pal.muted,
    )
    V.fit_text(
        draw,
        (left + 40, top + 102),
        value_text,
        max_width=right - left - 80,
        size=96,
        min_size=54,
        color=V.readable_color(
            V.parse_color(data.get("value_color"), pal.accent),
            pal.panel,
            pal.text,
        ),
        bold=True,
    )
    status_pill_bbox = None
    status_text_boxes = []
    if status:
        status_color = V.visible_mark_color(
            V.parse_color(data.get("status_color"), pal.accent),
            pal.panel,
            pal.accent,
        )
        status_width = min(
            right - left - 80,
            max(
                120,
                max(
                    int(
                        draw.textlength(
                            line,
                            font=V.font(line, V.MIN_METADATA_FONT, True),
                        )
                    )
                    for line in status_lines
                )
                + 42,
            ),
        )
        status_height = 20 + len(status_lines) * 39
        status_pill_bbox = (
            left + 40,
            top + 230,
            left + 40 + status_width,
            top + 230 + status_height,
        )
        draw.rounded_rectangle(
            status_pill_bbox,
            radius=25,
            fill=status_color,
        )
        status_y = top + 240
        for line in status_lines:
            status_font = V.font(line, V.MIN_METADATA_FONT, True)
            text_xy = (left + 61, status_y)
            text_box = draw.textbbox(
                text_xy,
                line,
                font=status_font,
                anchor="lt",
            )
            status_text_boxes.append(list(map(int, text_box)))
            draw.text(
                text_xy,
                line,
                font=status_font,
                fill=V.accessible_foreground(status_color),
                anchor="lt",
            )
            status_y += 39
    context = str(data.get("context", data.get("note", ""))).strip()
    if context:
        context_top = (
            status_pill_bbox[3] + 44
            if status_pill_bbox is not None
            else top + 260
        )
        lines = V.L.wrap_text(context, V.MIN_BODY_FONT, False, right - left - 80, 4)
        if any(line.endswith("…") for line in lines):
            image.info["text_truncated"] = "true"
        for line in lines:
            draw.text(
                (left + 40, context_top),
                line,
                font=V.font(line, V.MIN_BODY_FONT),
                fill=pal.text,
            )
            context_top += 47
    return V.save_png(
        image,
        output,
        spec,
        content,
        pal,
        extra_metadata={
            "item_count": 1,
            "status_layout": (
                "wrapped"
                if len(status_lines) > 1
                else "single-line" if status_lines else "none"
            ),
            "status_line_count": len(status_lines),
            "status_pill_bbox": (
                json.dumps(status_pill_bbox, separators=(",", ":"))
                if status_pill_bbox is not None
                else ""
            ),
            "status_text_boxes": json.dumps(
                status_text_boxes,
                separators=(",", ":"),
            ),
        },
    )


def _render_composition(spec: Mapping[str, Any], output: Any) -> Path:
    data = spec["data"]
    raw_items = data.get("items", [])
    if not isinstance(raw_items, list) or len(raw_items) < 2:
        raise V.RenderSpecError("composition requires at least two data.items")
    if len(raw_items) > 8:
        raise V.RenderSpecError(
            f"composition has {len(raw_items)} items; maximum is 8; "
            "split the visual instead of silently omitting items"
        )
    items = []
    default_colors = [
        (37, 99, 235),
        (5, 150, 105),
        (217, 119, 6),
        (124, 58, 237),
        (220, 38, 38),
        (8, 145, 178),
        (190, 24, 93),
        (77, 124, 15),
    ]
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, Mapping):
            raise V.RenderSpecError("each composition item must be an object")
        value = _item_value(raw, f"data.items[{index}].value")
        if value < 0:
            raise V.RenderSpecError("composition values must be non-negative")
        items.append(
            {
                "label": str(raw.get("label", f"Part {index + 1}")),
                "value": value,
                "color": V.parse_color(raw.get("color"), default_colors[index]),
            }
        )
    total = sum(item["value"] for item in items)
    if total <= 0:
        raise V.RenderSpecError("composition total must be greater than zero")
    row_h = 88
    image, draw, content, pal = V.canvas(spec, 560 + row_h * len(items))
    left, top, right, bottom = content
    heading = str(data.get("composition_label", "Composition"))
    draw.text((left, top), heading, font=V.font(heading, 40, True), fill=pal.text)
    total_text = str(data.get("total_label", f"Total {V.format_value(total, data)}"))
    draw.text(
        (right, top + 6),
        total_text,
        font=V.font(total_text, V.MIN_METADATA_FONT, True),
        fill=pal.muted,
        anchor="ra",
    )
    track_top = top + 76
    track_h = 68
    cursor = left
    for index, item in enumerate(items):
        segment_color = V.visible_mark_color(item["color"], pal.card, pal.accent)
        ratio = item["value"] / total
        segment_right = right if index == len(items) - 1 else int(cursor + ratio * (right - left))
        draw.rectangle((cursor, track_top, segment_right, track_top + track_h), fill=segment_color)
        if segment_right - cursor >= 96:
            percent = f"{ratio * 100:.0f}%"
            draw.text(
                ((cursor + segment_right) // 2, track_top + track_h // 2),
                percent,
                font=V.font(percent, V.MIN_METADATA_FONT, True),
                fill=V.accessible_foreground(segment_color),
                anchor="mm",
            )
        cursor = segment_right
    draw.rounded_rectangle(
        (left, track_top, right, track_top + track_h),
        radius=22,
        outline=pal.line,
        width=2,
    )
    list_top = track_top + 118
    for index, item in enumerate(items):
        y = list_top + index * row_h
        ratio = item["value"] / total
        draw.rounded_rectangle(
            (left, y + 7, left + 34, y + 41),
            radius=9,
            fill=item["color"],
        )
        V.fit_text(
            draw,
            (left + 52, y + 4),
            item["label"],
            max_width=right - left - 380,
            size=V.MIN_BODY_FONT,
            min_size=V.MIN_BODY_FONT,
            color=pal.text,
            bold=True,
        )
        formatted = V.format_value(item["value"], data)
        percent_only = (
            str(data.get("suffix", data.get("unit", ""))).strip() == "%"
            and abs(total - 100.0) < 1e-9
        )
        value_text = formatted if percent_only else f"{formatted} · {ratio * 100:.1f}%"
        draw.text(
            (right, y + 4),
            value_text,
            font=V.font(value_text, V.MIN_BODY_FONT, True),
            fill=pal.text,
            anchor="ra",
        )
    return V.save_png(
        image,
        output,
        spec,
        content,
        pal,
        extra_metadata={"item_count": len(items), "composition_total": total},
    )


def _render_uncertainty(spec: Mapping[str, Any], output: Any) -> Path:
    data = spec["data"]
    estimate = _item_value(data.get("estimate"), "data.estimate")
    raw_intervals = data.get("intervals")
    if raw_intervals is None and "low" in data and "high" in data:
        raw_intervals = [{"label": str(data.get("interval_label", "Range")),
                          "low": data["low"], "high": data["high"]}]
    if not isinstance(raw_intervals, list) or not raw_intervals:
        raise V.RenderSpecError("uncertainty requires data.intervals or data.low/data.high")
    if len(raw_intervals) > 6:
        raise V.RenderSpecError(
            f"uncertainty has {len(raw_intervals)} intervals; maximum is 6; "
            "split the visual instead of silently omitting intervals"
        )
    intervals = []
    values = [estimate]
    for index, raw in enumerate(raw_intervals):
        if not isinstance(raw, Mapping):
            raise V.RenderSpecError("each uncertainty interval must be an object")
        low = V.number(raw.get("low"), f"data.intervals[{index}].low")
        high = V.number(raw.get("high"), f"data.intervals[{index}].high")
        if high < low:
            raise V.RenderSpecError("uncertainty interval high must be >= low")
        intervals.append(
            {
                "label": str(raw.get("label", f"Range {index + 1}")),
                "low": low,
                "high": high,
                "color": V.parse_color(raw.get("color"), (37, 99, 235)),
            }
        )
        values.extend([low, high])
    domain = _domain(values, data.get("domain"))
    row_h = 170
    image, draw, content, pal = V.canvas(spec, 620 + row_h * len(intervals))
    left, top, right, bottom = content
    _hero(
        draw,
        (left, top, right, top + 200),
        str(data.get("estimate_label", "ESTIMATE")),
        V.format_value(estimate, data),
        pal=pal,
        value_color=pal.accent,
        note=str(data.get("note", "")),
    )
    label_w = min(
        410,
        max(
            250,
            max(
                int(draw.textlength(
                    interval["label"],
                    font=V.font(interval["label"], V.MIN_BODY_FONT, True),
                )) + 36
                for interval in intervals
            ),
        ),
    )
    axis_left, axis_right = left + label_w, right - 52
    rows_top = top + 262
    endpoint_layouts = []
    endpoint_boxes = []
    endpoint_gaps = []
    for index, interval in enumerate(intervals):
        y = rows_top + index * row_h
        V.fit_text(
            draw,
            (left, y + 12),
            interval["label"],
            max_width=label_w - 32,
            size=V.MIN_BODY_FONT,
            min_size=V.MIN_BODY_FONT,
            color=pal.text,
            bold=True,
        )
        low_x = _x(interval["low"], domain, axis_left, axis_right)
        high_x = _x(interval["high"], domain, axis_left, axis_right)
        estimate_x = _x(estimate, domain, axis_left, axis_right)
        draw.line((axis_left, y + 38, axis_right, y + 38), fill=pal.line, width=4)
        draw.rounded_rectangle(
            (low_x, y + 24, max(low_x + 8, high_x), y + 52),
            radius=14,
            fill=V.visible_mark_color(interval["color"], pal.card, pal.accent),
        )
        draw.line((estimate_x, y + 10, estimate_x, y + 66), fill=pal.text, width=5)
        draw.ellipse(
            (estimate_x - 8, y + 30, estimate_x + 8, y + 46),
            fill=pal.card,
            outline=pal.text,
            width=4,
        )
        endpoint_mode, boxes, endpoint_gap = _draw_interval_endpoint_labels(
            draw,
            low_x=low_x,
            high_x=high_x,
            y=y + 70,
            low_text=V.format_value(interval["low"], data),
            high_text=V.format_value(interval["high"], data),
            color=pal.muted,
        )
        endpoint_layouts.append(endpoint_mode)
        endpoint_boxes.append(boxes)
        endpoint_gaps.append(endpoint_gap)
    draw.text(
        (axis_left, bottom - 35),
        V.format_value(domain[0], data),
        font=V.font("0", V.MIN_METADATA_FONT),
        fill=pal.muted,
    )
    draw.text(
        (axis_right, bottom - 35),
        V.format_value(domain[1], data),
        font=V.font("0", V.MIN_METADATA_FONT),
        fill=pal.muted,
        anchor="ra",
    )
    return V.save_png(
        image,
        output,
        spec,
        content,
        pal,
        extra_metadata={
            "item_count": len(intervals),
            "interval_label_layout": (
                "staggered" if "staggered" in endpoint_layouts else "inline"
            ),
            "interval_label_boxes": json.dumps(
                endpoint_boxes,
                separators=(",", ":"),
            ),
            "interval_label_min_gap_px": min(endpoint_gaps),
        },
    )


def _render_network(spec: Mapping[str, Any], output: Any) -> Path:
    data = spec["data"]
    raw_nodes = data.get("nodes", [])
    raw_edges = data.get("edges", [])
    if not isinstance(raw_nodes, list) or not 2 <= len(raw_nodes) <= 12:
        raise V.RenderSpecError("network requires 2–12 data.nodes")
    if not isinstance(raw_edges, list):
        raise V.RenderSpecError("network data.edges must be an array")
    nodes = []
    node_ids = set()
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, Mapping):
            raise V.RenderSpecError("each network node must be an object")
        node_id = str(raw.get("id", index + 1))
        if node_id in node_ids:
            raise V.RenderSpecError(f"duplicate network node id: {node_id}")
        node_ids.add(node_id)
        nodes.append(
            {
                "id": node_id,
                "label": str(raw.get("label", node_id)),
                "color": V.parse_color(raw.get("color"), (37, 99, 235)),
            }
        )
    edges = []
    pairs = set()
    for index, raw in enumerate(raw_edges):
        if not isinstance(raw, Mapping):
            raise V.RenderSpecError("each network edge must be an object")
        source, target = str(raw.get("source", "")), str(raw.get("target", ""))
        if source not in node_ids or target not in node_ids:
            raise V.RenderSpecError(f"network edge {index} references an unknown node")
        if source == target:
            raise V.RenderSpecError("network self-edges are not supported")
        pair = tuple(sorted((source, target)))
        pairs.add(pair)
        edges.append({"source": source, "target": target, "label": str(raw.get("label", ""))})
    maximum_pairs = len(nodes) * (len(nodes) - 1) / 2
    density = len(pairs) / maximum_pairs if maximum_pairs else 0
    dense = len(nodes) >= 6 and (density > 0.35 or len(edges) > 18)
    directed = bool(data.get("directed", False))
    two_column_width = (1056 // 2) - 58
    two_columns = all(
        V.font(
            f"{index + 1:02d}  {node['label']}",
            V.MIN_METADATA_FONT,
            True,
        ).getlength(f"{index + 1:02d}  {node['label']}")
        <= two_column_width
        for index, node in enumerate(nodes)
    )
    legend_columns = 2 if two_columns else 1
    legend_rows = int(math.ceil(len(nodes) / legend_columns))
    base_height = 1150 if dense else 980
    image, draw, content, pal = V.canvas(spec, base_height + legend_rows * 72)
    left, top, right, bottom = content
    for node in nodes:
        node["color"] = V.visible_mark_color(node["color"], pal.card, pal.accent)
    encoding = "adjacency-matrix" if dense else "circular-node-link"
    encoding_label = "DENSE · ADJACENCY MATRIX" if dense else "SPARSE · NODE-LINK"
    draw.text(
        (left, top),
        encoding_label,
        font=V.font(encoding_label, V.MIN_METADATA_FONT, True),
        fill=pal.muted,
    )
    id_to_index = {node["id"]: index for index, node in enumerate(nodes)}
    graph_bottom = top + 560
    if dense:
        matrix_top = top + 110
        matrix_left = left + 180
        matrix_size = min(620, right - matrix_left - 20)
        cell = max(34, matrix_size // len(nodes))
        present = set((edge["source"], edge["target"]) for edge in edges)
        for row, row_node in enumerate(nodes):
            draw.text(
                (matrix_left - 25, matrix_top + row * cell + cell // 2),
                str(row + 1),
                font=V.font("0", V.MIN_METADATA_FONT, True),
                fill=pal.text,
                anchor="rm",
            )
            draw.text(
                (matrix_left + row * cell + cell // 2, matrix_top - 25),
                str(row + 1),
                font=V.font("0", V.MIN_METADATA_FONT, True),
                fill=pal.text,
                anchor="mb",
            )
            for column, column_node in enumerate(nodes):
                x1 = matrix_left + column * cell
                y1 = matrix_top + row * cell
                connected = (row_node["id"], column_node["id"]) in present
                if not directed:
                    connected = connected or (column_node["id"], row_node["id"]) in present
                fill = pal.accent if connected else pal.panel
                draw.rectangle((x1, y1, x1 + cell - 3, y1 + cell - 3),
                               fill=fill, outline=pal.line, width=1)
        graph_bottom = matrix_top + len(nodes) * cell
    else:
        cx = (left + right) // 2
        cy = top + 310
        radius = min(245, (right - left) // 2 - 120)
        positions = {}
        for index, node in enumerate(nodes):
            angle = -math.pi / 2 + index * 2 * math.pi / len(nodes)
            positions[node["id"]] = (
                int(cx + math.cos(angle) * radius),
                int(cy + math.sin(angle) * radius),
            )
        for edge in edges:
            start, end = positions[edge["source"]], positions[edge["target"]]
            draw.line((start, end), fill=pal.line, width=6)
            if directed:
                angle = math.atan2(end[1] - start[1], end[0] - start[0])
                tip = (
                    end[0] - math.cos(angle) * 36,
                    end[1] - math.sin(angle) * 36,
                )
                base = (
                    tip[0] - math.cos(angle) * 18,
                    tip[1] - math.sin(angle) * 18,
                )
                normal = (-math.sin(angle) * 10, math.cos(angle) * 10)
                draw.polygon(
                    [
                        tip,
                        (base[0] + normal[0], base[1] + normal[1]),
                        (base[0] - normal[0], base[1] - normal[1]),
                    ],
                    fill=pal.muted,
                )
            if edge["label"] and len(edges) <= 6:
                mx, my = (start[0] + end[0]) // 2, (start[1] + end[1]) // 2
                label = edge["label"]
                draw.text(
                    (mx, my),
                    label,
                    font=V.font(label, V.MIN_METADATA_FONT, True),
                    fill=pal.muted,
                    anchor="mm",
                    stroke_width=5,
                    stroke_fill=pal.card,
                )
        for index, node in enumerate(nodes):
            x, y = positions[node["id"]]
            draw.ellipse(
                (x - 32, y - 32, x + 32, y + 32),
                fill=node["color"],
                outline=pal.card,
                width=5,
            )
            draw.text((x, y), str(index + 1), font=V.font("0", V.MIN_BODY_FONT, True),
                      fill=V.accessible_foreground(node["color"]), anchor="mm")
    legend_top = max(top + 625, graph_bottom + 48)
    column_w = (right - left) // legend_columns
    for index, node in enumerate(nodes):
        row, column = divmod(index, legend_columns)
        x = left + column * column_w
        y = legend_top + row * 62
        draw.ellipse((x, y + 6, x + 30, y + 36), fill=node["color"])
        legend = f"{index + 1:02d}  {node['label']}"
        V.fit_text(
            draw,
            (x + 44, y + 1),
            legend,
            max_width=column_w - 58,
            size=V.MIN_METADATA_FONT,
            min_size=V.MIN_METADATA_FONT,
            color=pal.text,
            bold=True,
        )
    return V.save_png(
        image,
        output,
        spec,
        content,
        pal,
        extra_metadata={
            "item_count": len(nodes),
            "edge_count": len(edges),
            "network_encoding": encoding,
            "network_density": f"{density:.4f}",
            "network_directed": "true" if directed else "false",
        },
    )


def render_chart(spec_source: Any, output: Any) -> Path:
    spec = V.load_render_spec(spec_source)
    dispatch = {
        "hero": _render_hero,
        "anchor": _render_anchor,
        "threshold": _render_threshold,
        "comparison": _render_comparison,
        "ranking": _render_comparison,
        "trend": _render_trend,
        "timeline": _render_timeline,
        "composition": _render_composition,
        "uncertainty": _render_uncertainty,
        "network": _render_network,
    }
    renderer = dispatch.get(spec["kind"])
    if renderer is None:
        raise V.RenderSpecError(f"{spec['kind']} is not a static chart kind")
    return renderer(spec, output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a chart RenderSpec or bundle.")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(render_chart(args.spec, args.out))


if __name__ == "__main__":
    main()
