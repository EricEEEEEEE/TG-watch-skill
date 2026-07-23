#!/usr/bin/env python3
"""Offline schematic route and radius maps for RenderSpec.

No map tiles or network access are used. Geographic inputs are projected with a
local equirectangular approximation and the output is explicitly labelled as a
schematic, so the renderer never fabricates cartographic evidence.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from PIL import ImageDraw

try:
    import render_visual as V
except ImportError:  # pragma: no cover
    from . import render_visual as V

Point = Dict[str, Any]


def _parse_point(raw: Any, field: str, index: int = 0) -> Point:
    if not isinstance(raw, Mapping):
        raise V.RenderSpecError(f"{field} must be an object")
    label = str(raw.get("label", raw.get("name", f"Point {index + 1}")))
    if "lat" in raw and ("lon" in raw or "lng" in raw):
        lat = V.number(raw.get("lat"), f"{field}.lat")
        lon = V.number(raw.get("lon", raw.get("lng")), f"{field}.lon")
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise V.RenderSpecError(f"{field} contains invalid latitude/longitude")
        return {"label": label, "x": lon, "y": lat, "lat": lat, "lon": lon, "geo": True}
    if "x" in raw and "y" in raw:
        return {
            "label": label,
            "x": V.number(raw.get("x"), f"{field}.x"),
            "y": V.number(raw.get("y"), f"{field}.y"),
            "geo": False,
        }
    raise V.RenderSpecError(f"{field} needs lat/lon or x/y")


def _haversine(a: Point, b: Point) -> float:
    radius = 6371.0088
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat = lat2 - lat1
    dlon = math.radians(b["lon"] - a["lon"])
    inner = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(inner))


def _prepare_coordinates(points: Sequence[Point], *, sequential: bool) -> List[Point]:
    """Unwrap longitude and scale x for a local, north-up metric approximation."""
    prepared = [dict(point) for point in points]
    if not prepared or not prepared[0]["geo"]:
        return prepared
    mean_lat = sum(point["lat"] for point in prepared) / len(prepared)
    x_scale = max(0.01, abs(math.cos(math.radians(mean_lat))))
    reference = prepared[0]["lon"]
    previous = reference
    for index, point in enumerate(prepared):
        longitude = point["lon"]
        comparison = previous if sequential else reference
        while longitude - comparison > 180:
            longitude -= 360
        while longitude - comparison < -180:
            longitude += 360
        point["x"] = longitude * x_scale
        point["y"] = point["lat"]
        point["unwrapped_lon"] = longitude
        if sequential or index == 0:
            previous = longitude
    return prepared


def _bounds(points: Sequence[Point], radius_km: float = 0.0, center: Point = None) -> Tuple[float, float, float, float]:
    xs = [point["x"] for point in points]
    ys = [point["y"] for point in points]
    if center is not None and radius_km > 0:
        if center["geo"]:
            lat_delta = radius_km / 111.32
            lon_delta = radius_km / 111.32
        else:
            lat_delta = lon_delta = radius_km
        xs.extend([center["x"] - lon_delta, center["x"] + lon_delta])
        ys.extend([center["y"] - lat_delta, center["y"] + lat_delta])
    low_x, high_x = min(xs), max(xs)
    low_y, high_y = min(ys), max(ys)
    spread_x = high_x - low_x
    spread_y = high_y - low_y
    geo = bool(points and points[0]["geo"])
    pad_x = spread_x * 0.18 if spread_x else (0.02 if geo else max(abs(high_x) * 0.03, 0.02))
    pad_y = spread_y * 0.18 if spread_y else (0.02 if geo else max(abs(high_y) * 0.03, 0.02))
    return low_x - pad_x, low_y - pad_y, high_x + pad_x, high_y + pad_y


def _fit_bounds(
    bounds: Tuple[float, float, float, float],
    box: Tuple[int, int, int, int],
) -> Tuple[float, float, float, float]:
    """Expand one axis so x/y use the same source-unit-to-pixel scale."""
    low_x, low_y, high_x, high_y = bounds
    x1, y1, x2, y2 = box
    width, height = max(1, x2 - x1), max(1, y2 - y1)
    target_aspect = width / height
    range_x, range_y = high_x - low_x, high_y - low_y
    if range_x / range_y < target_aspect:
        desired_x = range_y * target_aspect
        delta = (desired_x - range_x) / 2
        low_x, high_x = low_x - delta, high_x + delta
    else:
        desired_y = range_x / target_aspect
        delta = (desired_y - range_y) / 2
        low_y, high_y = low_y - delta, high_y + delta
    return low_x, low_y, high_x, high_y


def _project(point: Point, bounds: Tuple[float, float, float, float], box: Tuple[int, int, int, int]) -> Tuple[int, int]:
    low_x, low_y, high_x, high_y = bounds
    x1, y1, x2, y2 = box
    x = x1 + (point["x"] - low_x) / (high_x - low_x) * (x2 - x1)
    y = y2 - (point["y"] - low_y) / (high_y - low_y) * (y2 - y1)
    return int(x), int(y)


def _draw_grid(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], pal: Any) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=22, fill=pal.panel, outline=pal.line, width=2)
    for index in range(1, 8):
        x = int(x1 + index * (x2 - x1) / 8)
        draw.line((x, y1 + 2, x, y2 - 2), fill=pal.line, width=1)
    for index in range(1, 6):
        y = int(y1 + index * (y2 - y1) / 6)
        draw.line((x1 + 2, y, x2 - 2, y), fill=pal.line, width=1)
    label = "SCHEMATIC · NORTH UP · NO BASEMAP"
    draw.rounded_rectangle((x1 + 16, y1 + 16, x1 + 570, y1 + 68), radius=22, fill=pal.card)
    draw.text(
        (x1 + 29, y1 + 25),
        label,
        font=V.font(label, V.MIN_METADATA_FONT, True),
        fill=pal.muted,
    )


def _draw_marker(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    label: str,
    index: int,
    *,
    color: Tuple[int, int, int],
    pal: Any,
) -> None:
    x, y = xy
    radius = 23
    draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                 fill=color, outline=pal.card, width=5)
    if index >= 0:
        draw.text((x, y - 1), str(index + 1),
                  font=V.font("0", V.MIN_METADATA_FONT, True),
                  fill=V.accessible_foreground(color), anchor="mm")
    label_font = V.font(label, V.MIN_METADATA_FONT, True)
    label_w = min(380, int(draw.textlength(label, font=label_font)) + 54)
    label_x = x + 30
    if label_x + label_w > draw._image.width - 54:
        label_x = x - label_w - 30
    draw.rounded_rectangle((label_x, y - 28, label_x + label_w, y + 28),
                           radius=16, fill=pal.card, outline=pal.line)
    V.fit_text(
        draw,
        (label_x + 17, y - 19),
        label,
        max_width=label_w - 34,
        size=V.MIN_METADATA_FONT,
        min_size=V.MIN_METADATA_FONT,
        color=pal.text,
        bold=True,
    )


def _route(spec: Mapping[str, Any], output: Any) -> Path:
    data = spec["data"]
    raw_points = data.get("points", [])
    if not isinstance(raw_points, list) or len(raw_points) < 2:
        raise V.RenderSpecError("route map requires at least two data.points")
    points = [_parse_point(raw, f"data.points[{index}]", index) for index, raw in enumerate(raw_points)]
    if any(point["geo"] != points[0]["geo"] for point in points):
        raise V.RenderSpecError("route points must all use the same coordinate system")
    points = _prepare_coordinates(points, sequential=True)
    image, draw, content, pal = V.canvas(spec, 1000)
    left, top, right, bottom = content
    map_box = (left, top + 96, right, bottom)
    bounds = _fit_bounds(_bounds(points), map_box)
    _draw_grid(draw, map_box, pal)
    coords = [_project(point, bounds, map_box) for point in points]
    route_color = V.visible_mark_color(
        V.parse_color(data.get("route_color"), pal.accent),
        pal.panel,
        pal.accent,
    )
    draw.line(coords, fill=(255, 255, 255), width=14, joint="curve")
    draw.line(coords, fill=route_color, width=8, joint="curve")
    # Direction chevrons on every segment.
    for start, end in zip(coords, coords[1:]):
        mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        length = 13
        wing = 7
        tip = (mx + math.cos(angle) * length, my + math.sin(angle) * length)
        left_wing = (
            mx - math.cos(angle) * wing + math.cos(angle + math.pi / 2) * wing,
            my - math.sin(angle) * wing + math.sin(angle + math.pi / 2) * wing,
        )
        right_wing = (
            mx - math.cos(angle) * wing - math.cos(angle + math.pi / 2) * wing,
            my - math.sin(angle) * wing - math.sin(angle + math.pi / 2) * wing,
        )
        draw.polygon([tip, left_wing, right_wing], fill=route_color)
    for index, (point, coord) in enumerate(zip(points, coords)):
        _draw_marker(draw, coord, point["label"], index, color=route_color, pal=pal)
    if "distance_label" in data:
        distance_semantics = "supplied-label"
        distance_label = str(data["distance_label"])
    elif "distance" in data:
        supplied_distance = V.number(data["distance"], "data.distance")
        distance_unit = str(data.get("distance_unit", data.get("unit", ""))).strip()
        distance_label = "Supplied distance · " + V.format_value(
            supplied_distance,
            {"unit": distance_unit, "decimals": data.get("decimals", 1)},
        )
        distance_semantics = "supplied-distance"
    elif points[0]["geo"]:
        distance = sum(_haversine(a, b) for a, b in zip(points, points[1:]))
        distance_semantics = "geodesic-straight-line-segments"
        distance_label = f"Geodesic straight-line segments · {distance:,.1f} km"
    else:
        distance_semantics = "relative-unspecified"
        distance_label = "relative route"
    V.fit_text(
        draw,
        (left, top + 5),
        distance_label,
        max_width=right - left - 260,
        size=40,
        min_size=V.MIN_BODY_FONT,
        color=pal.text,
        bold=True,
    )
    stops = f"{len(points)} stops"
    draw.text((right, top + 14), stops,
              font=V.font(stops, V.MIN_METADATA_FONT, True),
              fill=pal.muted, anchor="ra")
    return V.save_png(
        image,
        output,
        spec,
        content,
        pal,
        extra_metadata={
            "item_count": len(points),
            "projection": "schematic-equirectangular",
            "distance_semantics": distance_semantics,
        },
    )


def _radius(spec: Mapping[str, Any], output: Any) -> Path:
    data = spec["data"]
    center = _parse_point(data.get("center"), "data.center")
    radius_km = V.number(data.get("radius_km", data.get("radius")), "data.radius_km")
    if radius_km <= 0:
        raise V.RenderSpecError("data.radius_km must be greater than zero")
    raw_points = data.get("points", [])
    if not isinstance(raw_points, list):
        raise V.RenderSpecError("data.points must be an array")
    points = [_parse_point(raw, f"data.points[{index}]", index) for index, raw in enumerate(raw_points)]
    if any(point["geo"] != center["geo"] for point in points):
        raise V.RenderSpecError("radius map points and center must use the same coordinate system")
    all_points = _prepare_coordinates([center] + points, sequential=False)
    center, points = all_points[0], all_points[1:]
    image, draw, content, pal = V.canvas(spec, 1000)
    left, top, right, bottom = content
    map_box = (left, top + 96, right, bottom)
    bounds = _fit_bounds(_bounds(all_points, radius_km, center), map_box)
    _draw_grid(draw, map_box, pal)
    center_xy = _project(center, bounds, map_box)
    if center["geo"]:
        east = dict(center)
        east["x"] = center["x"] + radius_km / 111.32
    else:
        east = dict(center)
        east["x"] = center["x"] + radius_km
    east_xy = _project(east, bounds, map_box)
    radius_px = max(10, abs(east_xy[0] - center_xy[0]))
    radius_color = V.visible_mark_color(
        V.parse_color(data.get("radius_color"), pal.accent),
        pal.panel,
        pal.accent,
    )
    fill = tuple(int((channel + 255 * 4) / 5) for channel in radius_color)
    draw.ellipse(
        (
            center_xy[0] - radius_px,
            center_xy[1] - radius_px,
            center_xy[0] + radius_px,
            center_xy[1] + radius_px,
        ),
        fill=fill,
        outline=radius_color,
        width=6,
    )
    draw.line(
        (center_xy[0], center_xy[1], center_xy[0] + radius_px, center_xy[1]),
        fill=radius_color,
        width=3,
    )
    radius_label = str(data.get("radius_label", f"{radius_km:g} km"))
    radius_text_color = V.readable_color(radius_color, pal.panel, pal.text)
    draw.text(
        (center_xy[0] + radius_px // 2, center_xy[1] - 43),
        radius_label,
        font=V.font(radius_label, V.MIN_METADATA_FONT, True),
        fill=radius_text_color,
        anchor="ma",
    )
    _draw_marker(draw, center_xy, center["label"], -1, color=radius_color, pal=pal)
    for index, point in enumerate(points):
        coord = _project(point, bounds, map_box)
        point_color = V.visible_mark_color(
            V.parse_color(
                raw_points[index].get("color") if isinstance(raw_points[index], Mapping) else None,
                pal.good,
            ),
            pal.panel,
            pal.good,
        )
        _draw_marker(draw, coord, point["label"], index, color=point_color, pal=pal)
    heading = f"{radius_label} radius"
    draw.text((left, top + 7), heading, font=V.font(heading, 40, True), fill=pal.text)
    reference = f"{len(points)} reference points"
    draw.text((right, top + 14), reference,
              font=V.font(reference, V.MIN_METADATA_FONT, True),
              fill=pal.muted, anchor="ra")
    return V.save_png(
        image,
        output,
        spec,
        content,
        pal,
        extra_metadata={"item_count": len(points) + 1, "projection": "schematic-equirectangular"},
    )


def _point_map(spec: Mapping[str, Any], output: Any) -> Path:
    data = spec["data"]
    raw_points = data.get("points")
    if raw_points is None and data.get("point") is not None:
        raw_points = [data["point"]]
    if not isinstance(raw_points, list) or not 1 <= len(raw_points) <= 7:
        raise V.RenderSpecError("point map requires 1–7 data.points")
    points = [
        _parse_point(raw, f"data.points[{index}]", index)
        for index, raw in enumerate(raw_points)
    ]
    if any(point["geo"] != points[0]["geo"] for point in points):
        raise V.RenderSpecError("point map points must use the same coordinate system")
    points = _prepare_coordinates(points, sequential=False)
    image, draw, content, pal = V.canvas(spec, 1000)
    left, top, right, bottom = content
    heading = str(
        data.get(
            "location_label",
            "Location" if len(points) == 1 else f"{len(points)} supplied locations",
        )
    )
    V.fit_text(
        draw,
        (left, top + 5),
        heading,
        max_width=right - left,
        size=40,
        min_size=V.MIN_BODY_FONT,
        color=pal.text,
        bold=True,
    )
    map_box = (left, top + 96, right, bottom)
    bounds = _fit_bounds(_bounds(points), map_box)
    _draw_grid(draw, map_box, pal)
    for index, point in enumerate(points):
        coord = _project(point, bounds, map_box)
        raw = raw_points[index]
        point_color = V.visible_mark_color(
            V.parse_color(
                raw.get("color") if isinstance(raw, Mapping) else None,
                pal.accent,
            ),
            pal.panel,
            pal.accent,
        )
        _draw_marker(draw, coord, point["label"], index, color=point_color, pal=pal)
    return V.save_png(
        image,
        output,
        spec,
        content,
        pal,
        extra_metadata={
            "item_count": len(points),
            "projection": "schematic-equirectangular",
            "map_encoding": "point-map",
        },
    )


def render_map(spec_source: Any, output: Any) -> Path:
    spec = V.load_render_spec(spec_source)
    if spec["kind"] == "point":
        return _point_map(spec, output)
    if spec["kind"] == "route":
        return _route(spec, output)
    if spec["kind"] == "radius":
        return _radius(spec, output)
    raise V.RenderSpecError(f"{spec['kind']} is not a map kind")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render an offline schematic map RenderSpec or bundle.")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(render_map(args.spec, args.out))


if __name__ == "__main__":
    main()
