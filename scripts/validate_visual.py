#!/usr/bin/env python3
"""Validate TG Watch PNG/GIF artifacts and embedded RenderSpec metadata."""
from __future__ import annotations

import argparse
import json
import hashlib
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from PIL import (
    Image,
    ImageChops,
    ImageDraw,
    ImageFont,
    ImageSequence,
    ImageStat,
    PngImagePlugin,
)

try:
    import render_visual as V
except ImportError:  # pragma: no cover
    from . import render_visual as V


REQUIRED_METADATA = {
    "render_spec_version",
    "render_kind",
    "title",
    "render_spec_sha256",
    "content_bbox",
    "card_bbox",
    "canvas_background_color",
    "background_color",
    "foreground_color",
    "cjk_required",
    "cjk_sample",
    "font_path",
    "source_binding_status",
    "traceability_status",
    "min_title_font_px",
    "min_body_font_px",
    "min_metadata_font_px",
    "text_truncated",
}

MOBILE_WIDTHS = (320, 375, 390, 430)
MOBILE_FONT_FLOORS = {
    320: {"title": 12.5, "body": 9.0, "metadata": 9.5},
    375: {"title": 14.5, "body": 10.5, "metadata": 9.5},
    390: {"title": 15.0, "body": 11.0, "metadata": 9.5},
    430: {"title": 15.0, "body": 11.0, "metadata": 9.5},
}


def _metadata(image: Image.Image) -> Dict[str, str]:
    if image.format == "PNG":
        return {str(key): str(value) for key, value in image.info.items() if isinstance(value, (str, int, float))}
    comment = image.info.get("comment", b"")
    if isinstance(comment, bytes):
        comment = comment.decode("utf-8", errors="replace")
    if isinstance(comment, str) and comment.startswith("tg-watch:"):
        try:
            payload = json.loads(comment[len("tg-watch:") :])
            if isinstance(payload, Mapping):
                return {str(key): str(value) for key, value in payload.items()}
        except json.JSONDecodeError:
            return {}
    return {}


def _mobile_preview_metadata(image: Image.Image) -> Dict[str, str]:
    if image.format == "PNG":
        return {
            str(key): str(value)
            for key, value in image.info.items()
            if isinstance(value, (str, int, float))
        }
    comment = image.info.get("comment", b"")
    if isinstance(comment, bytes):
        comment = comment.decode("utf-8", errors="replace")
    if isinstance(comment, str) and comment.startswith("tg-watch-mobile:"):
        try:
            payload = json.loads(comment[len("tg-watch-mobile:") :])
            if isinstance(payload, Mapping):
                return {str(key): str(value) for key, value in payload.items()}
        except json.JSONDecodeError:
            return {}
    return {}


def _rgb(hex_color: str) -> Tuple[int, int, int]:
    raw = str(hex_color).strip().lstrip("#")
    if len(raw) != 6:
        raise ValueError("expected #RRGGBB")
    return tuple(int(raw[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _relative_luminance(color: Tuple[int, int, int]) -> float:
    channels = []
    for raw in color:
        channel = raw / 255.0
        channels.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> float:
    high, low = sorted((_relative_luminance(a), _relative_luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _nonblank(frame: Image.Image) -> bool:
    stat = ImageStat.Stat(frame.convert("L"))
    return bool(stat.var and stat.var[0] > 1.0)


def _outside_card_is_clear(
    frame: Image.Image,
    card_bbox: Tuple[int, int, int, int],
    canvas_background: Tuple[int, int, int],
) -> bool:
    """Inspect actual pixels outside the declared card, not renderer assertions."""
    rgb = frame.convert("RGB")
    width, height = rgb.size
    x1, y1, x2, y2 = card_bbox
    expected = Image.new("RGB", rgb.size, canvas_background)
    difference = ImageChops.difference(rgb, expected)
    mask = Image.new("L", rgb.size, 0)
    draw = ImageDraw.Draw(mask)
    if x1 > 0:
        draw.rectangle((0, 0, x1 - 1, height - 1), fill=255)
    if x2 < width:
        draw.rectangle((x2 + 1, 0, width - 1, height - 1), fill=255)
    if y1 > 0:
        draw.rectangle((x1, 0, x2, y1 - 1), fill=255)
    if y2 < height:
        draw.rectangle((x1, y2 + 1, x2, height - 1), fill=255)
    return ImageChops.multiply(difference.convert("L"), mask).getbbox() is None


def _boxes_overlap(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> bool:
    return not (
        a[2] <= b[0]
        or b[2] <= a[0]
        or a[3] <= b[1]
        or b[3] <= a[1]
    )


def _scaled_bbox(
    bbox: Tuple[int, int, int, int],
    scale: float,
) -> Tuple[int, int, int, int]:
    return (
        int(round(bbox[0] * scale)),
        int(round(bbox[1] * scale)),
        int(round(bbox[2] * scale)),
        int(round(bbox[3] * scale)),
    )


def _pixel_extent(
    frame: Image.Image,
    background: Tuple[int, int, int],
    *,
    tolerance: int = 3,
) -> Optional[Tuple[int, int, int, int]]:
    """Return the bbox of pixels visibly different from the canvas background."""

    expected = Image.new("RGB", frame.size, background)
    difference = ImageChops.difference(frame.convert("RGB"), expected).convert("L")
    mask = difference.point(lambda value: 255 if value > tolerance else 0)
    return mask.getbbox()


def _visible_pixel_count(
    frame: Image.Image,
    background: Tuple[int, int, int],
    *,
    tolerance: int = 20,
) -> int:
    expected = Image.new("RGB", frame.size, background)
    difference = ImageChops.difference(frame.convert("RGB"), expected).convert("L")
    histogram = difference.histogram()
    return int(sum(histogram[tolerance + 1 :]))


def _save_mobile_preview(
    source: Image.Image,
    output: Path,
    *,
    target_width: int,
    source_digest: str,
) -> None:
    source_width, source_height = source.size
    target_height = max(1, int(round(source_height * target_width / source_width)))
    preview_payload = {
        "schema": "tg-watch.mobile-preview.v1",
        "source_name": Path(getattr(source, "filename", "") or "artifact").name,
        "source_sha256": source_digest,
        "source_width": source_width,
        "source_height": source_height,
        "viewport_width": target_width,
        "viewport_height": target_height,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    if str(source.format or "").upper() == "GIF":
        frames: List[Image.Image] = []
        durations: List[int] = []
        for frame in ImageSequence.Iterator(source):
            frames.append(
                frame.convert("RGB").resize(
                    (target_width, target_height),
                    Image.Resampling.LANCZOS,
                )
            )
            durations.append(int(frame.info.get("duration", 0)))
        comment = (
            "tg-watch-mobile:"
            + json.dumps(preview_payload, ensure_ascii=False, separators=(",", ":"))
        ).encode("utf-8")
        frames[0].save(
            output,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=int(source.info.get("loop", 0)),
            disposal=2,
            optimize=False,
            comment=comment,
        )
        return
    info = PngImagePlugin.PngInfo()
    for key, value in preview_payload.items():
        info.add_text(str(key), str(value))
    source.convert("RGB").resize(
        (target_width, target_height),
        Image.Resampling.LANCZOS,
    ).save(output, format="PNG", pnginfo=info)


def validate_mobile_previews(
    path: Any,
    preview_dir: Any,
    *,
    widths: Sequence[int] = MOBILE_WIDTHS,
) -> Dict[str, Any]:
    """Materialize and inspect real phone-width previews for a PNG or GIF.

    This gate combines source render metadata with the pixels in each saved
    preview. It intentionally does not treat a single 390px font calculation
    as evidence that the other phone widths work.
    """

    artifact = Path(path)
    output_dir = Path(preview_dir)
    requested = tuple(int(width) for width in widths)
    report: Dict[str, Any] = {
        "ok": False,
        "source": str(artifact),
        "required_widths": list(requested),
        "preview_count": 0,
        "results": {},
        "errors": [],
    }
    if requested != MOBILE_WIDTHS:
        report["errors"].append(
            "mobile release gate requires exactly 320, 375, 390, and 430 px"
        )
        return report
    if not artifact.is_file():
        report["errors"].append("source artifact does not exist")
        return report
    source_digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    try:
        with Image.open(artifact) as source:
            source_format = str(source.format or "").upper()
            source_width, source_height = source.size
            source_frames = int(getattr(source, "n_frames", 1))
            source_metadata = _metadata(source)
            source_durations = (
                [
                    int(frame.info.get("duration", 0))
                    for frame in ImageSequence.Iterator(source)
                ]
                if source_format == "GIF"
                else []
            )
            if source_format not in {"PNG", "GIF"}:
                report["errors"].append(f"unsupported source format: {source_format}")
                return report
            if source_width < max(requested):
                report["errors"].append(
                    f"source width {source_width}px cannot cover the 430px gate without upscaling"
                )
                return report
            missing = sorted(REQUIRED_METADATA - set(source_metadata))
            if missing:
                report["errors"].append(
                    "source is missing render metadata: " + ", ".join(missing)
                )
                return report
            try:
                canvas_background = _rgb(source_metadata["canvas_background_color"])
                content_background = _rgb(source_metadata["background_color"])
                card_bbox = tuple(
                    int(value)
                    for value in json.loads(source_metadata["card_bbox"])
                )
                if len(card_bbox) != 4:
                    raise ValueError
                content_bbox = tuple(
                    int(value)
                    for value in json.loads(source_metadata["content_bbox"])
                )
                if len(content_bbox) != 4:
                    raise ValueError
                source_fonts = {
                    "title": int(source_metadata["min_title_font_px"]),
                    "body": int(source_metadata["min_body_font_px"]),
                    "metadata": int(source_metadata["min_metadata_font_px"]),
                }
                source.seek(0)
                source_extent = _pixel_extent(
                    source.convert("RGB"),
                    canvas_background,
                )
                if source_extent is None:
                    raise ValueError
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                report["errors"].append(
                    "source card/color/typography metadata is invalid"
                )
                return report

            for width in requested:
                suffix = ".gif" if source_format == "GIF" else ".png"
                preview_path = output_dir / f"{artifact.stem}-{width}px{suffix}"
                source.seek(0)
                _save_mobile_preview(
                    source,
                    preview_path,
                    target_width=width,
                    source_digest=source_digest,
                )
                expected_height = max(
                    1, int(round(source_height * width / source_width))
                )
                scale = width / source_width
                floors = MOBILE_FONT_FLOORS[width]
                display_fonts = {
                    role: round(value * scale, 3)
                    for role, value in source_fonts.items()
                }
                errors: List[str] = []
                checks: Dict[str, bool] = {}
                with Image.open(preview_path) as preview:
                    preview_format = str(preview.format or "").upper()
                    preview_frames = int(getattr(preview, "n_frames", 1))
                    preview_metadata = _mobile_preview_metadata(preview)
                    first = preview.convert("RGB")
                    actual_extent = _pixel_extent(first, canvas_background)
                    scaled_card = _scaled_bbox(source_extent, scale)
                    scaled_content = _scaled_bbox(content_bbox, scale)
                    content_pixels = first.crop(scaled_content)
                    checks["actual_dimensions"] = preview.size == (
                        width,
                        expected_height,
                    )
                    checks["format_preserved"] = preview_format == source_format
                    checks["preview_metadata"] = (
                        preview_metadata.get("schema")
                        == "tg-watch.mobile-preview.v1"
                        and preview_metadata.get("source_sha256") == source_digest
                        and preview_metadata.get("viewport_width") == str(width)
                        and preview_metadata.get("viewport_height")
                        == str(expected_height)
                    )
                    checks["metadata_readability"] = all(
                        display_fonts[role] >= floors[role]
                        for role in ("title", "body", "metadata")
                    )
                    checks["metadata_not_truncated"] = (
                        source_metadata.get("text_truncated") == "false"
                    )
                    checks["actual_pixel_content"] = (
                        _nonblank(content_pixels)
                        and _visible_pixel_count(
                            content_pixels,
                            content_background,
                        )
                        >= max(64, width // 2)
                    )
                    checks["actual_safe_margin"] = (
                        actual_extent is not None
                        and min(
                            actual_extent[0],
                            actual_extent[1],
                            width - actual_extent[2],
                            expected_height - actual_extent[3],
                        )
                        >= 2
                    )
                    checks["actual_card_geometry"] = (
                        actual_extent is not None
                        and all(
                            abs(actual_extent[index] - scaled_card[index])
                            <= 2
                            for index in range(4)
                        )
                    )
                    if source_format == "GIF":
                        preview_durations = [
                            int(frame.info.get("duration", 0))
                            for frame in ImageSequence.Iterator(preview)
                        ]
                        preview.seek(0)
                        first_frame = preview.convert("RGB")
                        preview.seek(preview_frames - 1)
                        last_frame = preview.convert("RGB")
                        checks["animation_preserved"] = (
                            preview_frames == source_frames
                            and preview_durations == source_durations
                            and ImageChops.difference(
                                first_frame, last_frame
                            ).getbbox()
                            is not None
                        )
                    else:
                        checks["animation_preserved"] = True
                for check, passed in checks.items():
                    if not passed:
                        errors.append(f"{width}px {check} failed")
                report["results"][str(width)] = {
                    "ok": not errors,
                    "path": str(preview_path),
                    "format": preview_format,
                    "size": [width, expected_height],
                    "frames": preview_frames,
                    "display_font_px": display_fonts,
                    "font_floor_px": floors,
                    "actual_content_bbox": (
                        list(actual_extent) if actual_extent is not None else None
                    ),
                    "checks": checks,
                    "errors": errors,
                }
    except (OSError, ValueError) as exc:
        report["errors"].append(f"cannot build mobile previews: {exc}")
        return report
    report["preview_count"] = len(report["results"])
    report["ok"] = (
        report["preview_count"] == len(MOBILE_WIDTHS)
        and all(item["ok"] for item in report["results"].values())
    )
    if not report["ok"] and not report["errors"]:
        report["errors"].extend(
            error
            for item in report["results"].values()
            for error in item["errors"]
        )
    return report


def validate_visual(
    path: Any,
    spec_source: Any = None,
    *,
    allow_unverified: bool = False,
) -> Dict[str, Any]:
    artifact = Path(path)
    errors = []
    warnings = []
    checks: Dict[str, bool] = {}
    metadata: Dict[str, str] = {}
    if not artifact.exists():
        return {
            "ok": False,
            "path": str(artifact),
            "format": "",
            "size": None,
            "frames": 0,
            "checks": {"exists": False},
            "errors": ["artifact does not exist"],
            "warnings": [],
            "metadata": {},
        }
    checks["exists"] = True
    try:
        with Image.open(artifact) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
            frame_count = int(getattr(image, "n_frames", 1))
            metadata = _metadata(image)
            checks["supported_format"] = image_format in {"PNG", "GIF"}
            if not checks["supported_format"]:
                errors.append(f"unsupported format: {image_format}")
            expected_suffix = ".png" if image_format == "PNG" else ".gif"
            checks["extension_matches_format"] = artifact.suffix.lower() == expected_suffix
            if not checks["extension_matches_format"]:
                errors.append("file extension does not match image format")
            checks["dimensions"] = 320 <= width <= 4096 and 320 <= height <= 4096
            if not checks["dimensions"]:
                errors.append(f"dimensions out of bounds: {width}x{height}")
            checks["nonblank_first_frame"] = _nonblank(image.copy())
            if not checks["nonblank_first_frame"]:
                errors.append("first frame is blank or visually uniform")

            missing = sorted(REQUIRED_METADATA - set(metadata))
            checks["metadata"] = not missing
            if missing:
                errors.append("missing metadata: " + ", ".join(missing))

            bbox = None
            if metadata.get("content_bbox"):
                try:
                    parsed = json.loads(metadata["content_bbox"])
                    if not isinstance(parsed, list) or len(parsed) != 4:
                        raise ValueError
                    bbox = tuple(int(value) for value in parsed)
                    x1, y1, x2, y2 = bbox
                    checks["content_boundary"] = (
                        0 <= x1 < x2 <= width
                        and 0 <= y1 < y2 <= height
                        and min(x1, y1, width - x2, height - y2) >= 8
                    )
                except (ValueError, TypeError, json.JSONDecodeError):
                    checks["content_boundary"] = False
            else:
                checks["content_boundary"] = False
            if not checks["content_boundary"]:
                errors.append("content_bbox is invalid or violates the 8px safe boundary")

            try:
                parsed_card = json.loads(metadata["card_bbox"])
                if not isinstance(parsed_card, list) or len(parsed_card) != 4:
                    raise ValueError
                card_bbox = tuple(int(value) for value in parsed_card)
                cx1, cy1, cx2, cy2 = card_bbox
                card_valid = (
                    0 <= cx1 < cx2 < width
                    and 0 <= cy1 < cy2 < height
                )
                checks["actual_card_boundary"] = card_valid and _outside_card_is_clear(
                    image.copy(),
                    card_bbox,
                    _rgb(metadata["canvas_background_color"]),
                )
            except (KeyError, ValueError, TypeError, json.JSONDecodeError):
                checks["actual_card_boundary"] = False
            if not checks["actual_card_boundary"]:
                errors.append("actual pixels escape the declared card boundary")

            try:
                ratio = contrast_ratio(
                    _rgb(metadata.get("background_color", "")),
                    _rgb(metadata.get("foreground_color", "")),
                )
                checks["base_contrast"] = ratio >= 4.5
                if not checks["base_contrast"]:
                    errors.append(f"base text contrast is {ratio:.2f}:1; expected at least 4.5:1")
            except (ValueError, TypeError):
                ratio = None
                checks["base_contrast"] = False
                errors.append("cannot validate base contrast metadata")

            cjk_required = metadata.get("cjk_required", "false").lower() == "true"
            if cjk_required:
                font_path = Path(metadata.get("font_path", ""))
                try:
                    font_ok = font_path.is_file()
                    if font_ok:
                        loaded_font = ImageFont.truetype(str(font_path), size=20)
                        sample = metadata.get("cjk_sample", "")
                        sample_glyphs = [
                            bytes(loaded_font.getmask(char))
                            for char in sample
                            if char.strip()
                        ]
                        missing_glyphs = {
                            bytes(loaded_font.getmask("\ufffd")),
                            bytes(loaded_font.getmask(chr(0x10FFFF))),
                        }
                        if (
                            sample
                            and (
                                len(set(sample_glyphs)) < min(2, len(set(sample)))
                                or any(glyph in missing_glyphs for glyph in sample_glyphs)
                            )
                        ):
                            font_ok = False
                except OSError:
                    font_ok = False
                checks["cjk_font"] = font_ok
                if not font_ok:
                    errors.append("CJK content requires a loadable CJK font")
            else:
                checks["cjk_font"] = True
            try:
                scale = min(1.0, 390.0 / width)
                typography_ok = (
                    int(metadata["min_title_font_px"]) >= V.MIN_TITLE_FONT
                    and int(metadata["min_body_font_px"]) >= V.MIN_BODY_FONT
                    and int(metadata["min_metadata_font_px"]) >= V.MIN_METADATA_FONT
                    and int(metadata["min_title_font_px"]) * scale >= 15.0
                    and int(metadata["min_body_font_px"]) * scale >= 11.0
                    and int(metadata["min_metadata_font_px"]) * scale >= 9.5
                )
            except (KeyError, TypeError, ValueError):
                typography_ok = False
            checks["mobile_typography"] = typography_ok
            if not typography_ok:
                errors.append("source typography metadata is below the mobile readability gate")
            checks["no_text_truncation"] = metadata.get("text_truncated") == "false"
            if not checks["no_text_truncation"]:
                errors.append("renderer truncated text; split, wrap, or enlarge the artifact")

            if metadata.get("render_kind") == "uncertainty":
                try:
                    raw_boxes = json.loads(metadata["interval_label_boxes"])
                    label_boxes = [
                        (
                            tuple(int(value) for value in pair[0]),
                            tuple(int(value) for value in pair[1]),
                        )
                        for pair in raw_boxes
                    ]
                    boxes_valid = bool(label_boxes) and all(
                        len(low_box) == 4
                        and len(high_box) == 4
                        and 0 <= low_box[0] < low_box[2] <= width
                        and 0 <= low_box[1] < low_box[3] <= height
                        and 0 <= high_box[0] < high_box[2] <= width
                        and 0 <= high_box[1] < high_box[3] <= height
                        and not _boxes_overlap(low_box, high_box)
                        for low_box, high_box in label_boxes
                    )
                    separation_ok = (
                        boxes_valid
                        and metadata.get("interval_label_layout")
                        in {"inline", "staggered"}
                        and int(metadata["interval_label_min_gap_px"]) >= 12
                    )
                except (
                    KeyError,
                    TypeError,
                    ValueError,
                    json.JSONDecodeError,
                ):
                    separation_ok = False
                checks["interval_label_separation"] = separation_ok
                if not separation_ok:
                    errors.append(
                        "uncertainty endpoint labels overlap or lack a 12px separation"
                    )
            else:
                checks["interval_label_separation"] = True

            if metadata.get("motion_threshold_visible") == "true":
                try:
                    marker = tuple(
                        int(value)
                        for value in json.loads(metadata["threshold_marker_bbox"])
                    )
                    scale_box = tuple(
                        int(value)
                        for value in json.loads(metadata["motion_scale_bbox"])
                    )
                    marker_valid = (
                        len(marker) == 4
                        and len(scale_box) == 4
                        and 0 <= marker[0] < marker[2] <= width
                        and 0 <= marker[1] < marker[3] <= height
                        and 0 <= scale_box[0] < scale_box[2] <= width
                        and 0 <= scale_box[1] < scale_box[3] <= height
                        and _nonblank(image.convert("RGB").crop(marker))
                    )
                except (
                    KeyError,
                    TypeError,
                    ValueError,
                    json.JSONDecodeError,
                ):
                    marker_valid = False
                checks["motion_threshold_marker"] = marker_valid
                if not marker_valid:
                    errors.append("motion threshold marker is missing, blank, or out of bounds")
            else:
                checks["motion_threshold_marker"] = True

            if image_format == "GIF":
                checks["animated"] = frame_count >= 3
                if not checks["animated"]:
                    errors.append("sequence GIF needs at least three frames")
                durations = [
                    int(frame.info.get("duration", 0))
                    for frame in ImageSequence.Iterator(image)
                ]
                total_duration = sum(durations)
                checks["motion_duration"] = (
                    6000 <= total_duration <= 12000
                    and metadata.get("total_duration_ms") == str(total_duration)
                )
                if not checks["motion_duration"]:
                    errors.append(
                        "sequence duration must be 6000–12000ms and match metadata"
                    )
                fallback_ok = True
                for metadata_key, role in (
                    ("poster_artifact", "poster"),
                    ("final_artifact", "final"),
                ):
                    filename = metadata.get(metadata_key, "")
                    if not filename or Path(filename).name != filename:
                        fallback_ok = False
                        continue
                    fallback_path = artifact.parent / filename
                    try:
                        with Image.open(fallback_path) as fallback:
                            fallback_ok = (
                                fallback_ok
                                and fallback.format == "PNG"
                                and fallback.size == (width, height)
                                and _metadata(fallback).get("motion_role") == role
                            )
                    except OSError:
                        fallback_ok = False
                checks["static_fallbacks"] = fallback_ok
                if not fallback_ok:
                    errors.append("sequence poster/final static fallback artifacts are missing or invalid")
                image.seek(0)
                first = image.convert("RGB")
                image.seek(frame_count - 1)
                last = image.convert("RGB")
                checks["nonblank_last_frame"] = _nonblank(last)
                if not checks["nonblank_last_frame"]:
                    errors.append("last frame is blank or visually uniform")
                difference = ImageChops.difference(first, last)
                checks["first_last_distinct"] = difference.getbbox() is not None
                if not checks["first_last_distinct"]:
                    errors.append("first and last frames are identical")
                declared_frames = metadata.get("frame_count")
                checks["frame_metadata"] = declared_frames == str(frame_count)
                if not checks["frame_metadata"]:
                    errors.append("frame_count metadata does not match GIF frames")
            else:
                checks["animated"] = True
                checks["nonblank_last_frame"] = True
                checks["first_last_distinct"] = True
                checks["frame_metadata"] = True
    except (OSError, ValueError) as exc:
        return {
            "ok": False,
            "path": str(artifact),
            "format": "",
            "size": None,
            "frames": 0,
            "checks": checks,
            "errors": [f"cannot inspect image: {exc}"],
            "warnings": warnings,
            "metadata": metadata,
        }

    if spec_source is not None:
        try:
            spec = V.load_render_spec(spec_source)
            checks["render_spec_digest"] = (
                metadata.get("render_spec_sha256") == V.render_spec_digest(spec)
            )
            if not checks["render_spec_digest"]:
                errors.append("artifact render_spec_sha256 does not match the supplied RenderSpec")
            checks["kind_matches_spec"] = metadata.get("render_kind") == spec["kind"]
            if not checks["kind_matches_spec"]:
                errors.append("artifact render_kind does not match the supplied RenderSpec")
            checks["title_matches_spec"] = metadata.get("title") == spec["title"]
            if not checks["title_matches_spec"]:
                errors.append("artifact title does not match the supplied RenderSpec")
            if (
                V.contains_cjk(V._public_render_spec(spec))
                and metadata.get("cjk_required", "false").lower() != "true"
            ):
                checks["cjk_declaration"] = False
                errors.append("CJK RenderSpec is not declared in artifact metadata")
            else:
                checks["cjk_declaration"] = True
            decision = spec.get("_visual_spec")
            if isinstance(decision, Mapping):
                checks["visual_spec_digest"] = (
                    metadata.get("visual_spec_sha256") == V.decision_spec_digest(decision)
                )
                if not checks["visual_spec_digest"]:
                    errors.append("artifact visual_spec_sha256 does not match the bundle VisualSpec")
                checks["source_binding_status"] = (
                    metadata.get("source_binding_status")
                    == str(spec.get("_source_binding_status", ""))
                )
                if not checks["source_binding_status"]:
                    errors.append("artifact source_binding_status differs from bundle validation")
            if spec["kind"] == "sequence" and "threshold" in spec["data"]:
                try:
                    threshold = V.number(
                        spec["data"]["threshold"],
                        "data.threshold",
                    )
                    domain = [
                        V.number(value, "motion_scale_domain")
                        for value in json.loads(metadata["motion_scale_domain"])
                    ]
                    expected_threshold = V.format_value(threshold, spec["data"])
                    threshold_encoding_ok = (
                        len(domain) == 2
                        and domain[0] <= threshold <= domain[1]
                        and metadata.get("motion_threshold_visible") == "true"
                        and metadata.get("motion_threshold_value") == expected_threshold
                        and checks.get("motion_threshold_marker", False)
                    )
                except (
                    KeyError,
                    TypeError,
                    ValueError,
                    json.JSONDecodeError,
                    V.RenderSpecError,
                ):
                    threshold_encoding_ok = False
                checks["motion_threshold_encoding"] = threshold_encoding_ok
                if not threshold_encoding_ok:
                    errors.append(
                        "numeric sequence threshold is not visibly encoded on a shared scale"
                    )
            else:
                checks["motion_threshold_encoding"] = True
        except V.RenderSpecError as exc:
            checks["render_spec_digest"] = False
            errors.append(f"supplied RenderSpec/bundle is invalid: {exc}")
    binding_status = metadata.get("source_binding_status", "")
    traceability_status = metadata.get("traceability_status", "")
    checks["traceability"] = traceability_status == "verified"
    if not checks["traceability"]:
        message = (
            metadata.get("source_binding_warning")
            or f"source bindings are {binding_status or 'unverified'}"
        )
        if allow_unverified:
            warnings.append(message)
        else:
            errors.append(message + "; use --allow-unverified only for prototypes")
    if not metadata.get("source"):
        warnings.append("source metadata is empty")
    if not metadata.get("timestamp"):
        warnings.append("timestamp metadata is empty")

    return {
        "ok": not errors,
        "path": str(artifact),
        "format": image_format,
        "size": [width, height],
        "frames": frame_count,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "metadata": metadata,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a TG Watch PNG/GIF artifact.")
    parser.add_argument("artifact")
    parser.add_argument("--spec", help="Optional source RenderSpec or bundle for digest verification")
    parser.add_argument(
        "--mobile-preview-dir",
        help="Materialize and validate the required 320/375/390/430px previews",
    )
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Allow standalone/untraceable prototype artifacts as warnings",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = validate_visual(
        args.artifact,
        args.spec,
        allow_unverified=args.allow_unverified,
    )
    if args.mobile_preview_dir:
        mobile = validate_mobile_previews(
            args.artifact,
            args.mobile_preview_dir,
        )
        result["mobile_gate"] = mobile
        result["checks"]["mobile_previews"] = bool(mobile["ok"])
        if not mobile["ok"]:
            result["ok"] = False
            result["errors"].extend(
                "mobile gate: %s" % error
                for error in mobile.get("errors", [])
            )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
