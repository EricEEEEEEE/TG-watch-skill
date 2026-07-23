#!/usr/bin/env python3
"""Render a RenderSpec JSON document to a Telegram-ready PNG or GIF.

RenderSpec is intentionally small and domain-neutral::

    {
      "version": "1.0",
      "kind": "anchor",
      "title": "Asset value",
      "subtitle": "Current price against two anchors",
      "theme": "light",
      "data": {...},
      "meta": {"source": "Example API", "timestamp": "2026-07-23 10:00 SGT"}
    }

The renderer also accepts a decision/render bundle shaped as
``{"visual_spec": <decision IR>, "render_spec": <RenderSpec>}``. In bundle
mode, the selected modality, known grammar mapping, and evidence bindings are
checked before pixels are generated.

Supported kinds are implemented by sibling modules:
anchor/value-band, threshold/bullet, comparison/ranking, trend, timeline,
route/radius, and sequence (animated GIF).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

try:
    import layout as L
except ImportError:  # pragma: no cover - package-style import
    from . import layout as L

RGB = Tuple[int, int, int]
BBox = Tuple[int, int, int, int]

KIND_ALIASES = {
    "value-band": "anchor",
    "value_band": "anchor",
    "bullet": "threshold",
    "static-route": "route",
    "static_route": "route",
    "radius-map": "radius",
    "radius_map": "radius",
    "animation": "sequence",
}
CHART_KINDS = {
    "hero",
    "anchor",
    "threshold",
    "comparison",
    "ranking",
    "trend",
    "timeline",
    "composition",
    "uncertainty",
    "network",
}
MAP_KINDS = {"route", "radius", "point"}
MOTION_KINDS = {"sequence"}
SUPPORTED_KINDS = CHART_KINDS | MAP_KINDS | MOTION_KINDS

# Source-space typography gates for 1200px Telegram assets. At the common
# 390px mobile display width these remain legible instead of collapsing into
# 4–7px text. Renderers may go larger, never smaller for user-facing content.
MIN_TITLE_FONT = 48
MIN_BODY_FONT = 34
MIN_METADATA_FONT = 36


class RenderSpecError(ValueError):
    """Raised when a RenderSpec cannot be rendered faithfully."""


def _public_render_spec(spec: Mapping[str, Any]) -> Dict[str, Any]:
    return {str(key): value for key, value in spec.items() if not str(key).startswith("_")}


def canonical_render_spec(spec: Mapping[str, Any]) -> str:
    return json.dumps(_public_render_spec(spec), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def render_spec_digest(spec: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_render_spec(spec).encode("utf-8")).hexdigest()


def decision_spec_digest(spec: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _wide_script_character(char: str) -> bool:
    code = ord(char)
    return (
        0x1100 <= code <= 0x11FF  # Hangul Jamo
        or 0x3130 <= code <= 0x318F  # Hangul compatibility Jamo
        or 0xAC00 <= code <= 0xD7AF  # Hangul syllables
        or 0x3000 <= code <= 0x30FF  # CJK punctuation, Hiragana, Katakana
        or 0x3400 <= code <= 0x4DBF  # CJK Extension A
        or 0x4E00 <= code <= 0x9FFF  # CJK Unified Ideographs
        or 0x20000 <= code <= 0x2EBEF  # CJK Extensions B–F
        or 0x30000 <= code <= 0x323AF  # CJK Extensions G–H
        or 0xFF00 <= code <= 0xFFEF  # Full-width forms
    )


def _contains_hangul(text: str) -> bool:
    return any(
        0x1100 <= ord(char) <= 0x11FF
        or 0x3130 <= ord(char) <= 0x318F
        or 0xAC00 <= ord(char) <= 0xD7AF
        for char in text
    )


def contains_cjk(value: Any) -> bool:
    if isinstance(value, str):
        return any(_wide_script_character(ch) for ch in value)
    if isinstance(value, Mapping):
        return any(contains_cjk(k) or contains_cjk(v) for k, v in value.items())
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return any(contains_cjk(item) for item in value)
    return False


def cjk_sample(value: Any, limit: int = 16) -> str:
    characters = []

    def visit(item: Any) -> None:
        if len(characters) >= limit:
            return
        if isinstance(item, str):
            for char in item:
                code = ord(char)
                if _wide_script_character(char) and char not in characters:
                    characters.append(char)
                    if len(characters) >= limit:
                        return
        elif isinstance(item, Mapping):
            for key, child in item.items():
                visit(key)
                visit(child)
        elif isinstance(item, Sequence) and not isinstance(item, (bytes, bytearray)):
            for child in item:
                visit(child)

    visit(value)
    return "".join(characters)


def resolve_font_path(text: str, bold: bool = False) -> str:
    """Return the concrete font used for metadata and CJK validation."""
    is_cjk = contains_cjk(text)
    if _contains_hangul(text):
        candidates = L._HANGUL_BOLD if bold else L._HANGUL_REGULAR
    elif is_cjk:
        candidates = L._CJK_BOLD if bold else L._CJK_REGULAR
    else:
        candidates = L._LATIN_BOLD if bold else L._LATIN_REGULAR
    for candidate in candidates:
        if Path(candidate).exists():
            try:
                ImageFont.truetype(candidate, size=20)
                return str(candidate)
            except OSError:
                continue
    return ""


def font(text: str, size: int, bold: bool = False) -> ImageFont.ImageFont:
    return L.pick_font(str(text), int(size), bool(bold))


def palette_for(spec: Mapping[str, Any]) -> L.Palette:
    theme = str(spec.get("theme", "light")).lower()
    accent = spec.get("accent")
    parsed_accent = parse_color(accent) if accent else None
    if theme == "dark":
        return L.dark_palette(parsed_accent or (96, 165, 250))
    if theme != "light":
        raise RenderSpecError("theme must be 'light' or 'dark'")
    return L.light_palette(parsed_accent or (37, 99, 235))


def parse_color(value: Any, fallback: RGB = (37, 99, 235)) -> RGB:
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            return tuple(max(0, min(255, int(v))) for v in value)  # type: ignore[return-value]
        except (TypeError, ValueError):
            return fallback
    if isinstance(value, str):
        raw = value.strip().lstrip("#")
        if len(raw) == 6:
            try:
                return tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
            except ValueError:
                return fallback
    return fallback


def color_hex(color: RGB) -> str:
    return "#" + "".join(f"{max(0, min(255, int(channel))):02x}" for channel in color)


def _relative_luminance(color: RGB) -> float:
    channels = []
    for value in color:
        channel = value / 255.0
        channels.append(
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def color_contrast(a: RGB, b: RGB) -> float:
    high, low = sorted((_relative_luminance(a), _relative_luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def accessible_foreground(background: RGB) -> RGB:
    dark = (9, 13, 20)
    light = (255, 255, 255)
    return max((dark, light), key=lambda candidate: color_contrast(background, candidate))


def readable_color(candidate: RGB, background: RGB, fallback: RGB, minimum: float = 4.5) -> RGB:
    """Keep custom text colors only when they remain readable on the supplied background."""
    if color_contrast(candidate, background) >= minimum:
        return candidate
    if color_contrast(fallback, background) >= minimum:
        return fallback
    return accessible_foreground(background)


def visible_mark_color(candidate: RGB, background: RGB, fallback: RGB) -> RGB:
    """Keep custom non-text marks only when they are distinguishable from the background."""
    if color_contrast(candidate, background) >= 3.0:
        return candidate
    if color_contrast(fallback, background) >= 3.0:
        return fallback
    return accessible_foreground(background)


def number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise RenderSpecError(f"{field} must be numeric, not boolean")
    if isinstance(value, int):
        return value
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise RenderSpecError(f"{field} must be numeric") from exc
    if not math.isfinite(result):
        raise RenderSpecError(f"{field} must be finite")
    return result


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def format_value(value: float, data: Mapping[str, Any], compact: bool = False) -> str:
    prefix = str(data.get("prefix", ""))
    suffix = str(data.get("suffix", data.get("unit", "")))
    compact = compact and bool(data.get("compact", False))
    if compact and abs(value) >= 1_000_000:
        body = f"{value / 1_000_000:.1f}M"
    elif compact and abs(value) >= 1_000:
        body = f"{value / 1_000:.1f}K"
    elif "decimals" in data:
        raw_decimals = data["decimals"]
        if isinstance(raw_decimals, bool):
            raise RenderSpecError("data.decimals must be an integer from 0 to 8")
        try:
            decimals = max(0, min(8, int(raw_decimals)))
        except (TypeError, ValueError) as exc:
            raise RenderSpecError("data.decimals must be an integer from 0 to 8") from exc
        body = f"{value:,.{decimals}f}"
    else:
        try:
            body = f"{Decimal(str(value)):,f}"
        except InvalidOperation as exc:
            raise RenderSpecError("display value must be finite numeric data") from exc
    spacer = " " if suffix and not suffix.startswith(("%", "x", "°")) else ""
    return f"{prefix}{body}{spacer}{suffix}".strip()


def normalize_kind(spec: Mapping[str, Any]) -> str:
    raw = str(spec.get("kind", spec.get("intent", ""))).strip().lower()
    kind = KIND_ALIASES.get(raw, raw)
    if kind not in SUPPORTED_KINDS:
        supported = ", ".join(sorted(SUPPORTED_KINDS))
        raise RenderSpecError(f"unsupported render kind {raw!r}; expected one of: {supported}")
    return kind


def normalize_render_spec(spec: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(spec, Mapping):
        raise RenderSpecError("RenderSpec must be a JSON object")
    normalized = dict(spec)
    normalized["version"] = str(spec.get("version", "1.0"))
    if normalized["version"] != "1.0":
        raise RenderSpecError("unsupported RenderSpec version; expected '1.0'")
    normalized["kind"] = normalize_kind(spec)
    normalized["title"] = str(spec.get("title", "")).strip()
    normalized["subtitle"] = str(spec.get("subtitle", "")).strip()
    normalized["theme"] = str(spec.get("theme", "light")).lower()
    if not normalized["title"]:
        raise RenderSpecError("RenderSpec.title is required")
    data = spec.get("data", {})
    meta = spec.get("meta", {})
    if not isinstance(data, Mapping):
        raise RenderSpecError("RenderSpec.data must be an object")
    if not isinstance(meta, Mapping):
        raise RenderSpecError("RenderSpec.meta must be an object")
    normalized["data"] = dict(data)
    normalized["meta"] = dict(meta)
    bindings = spec.get("source_bindings")
    if bindings is not None and not isinstance(bindings, (list, Mapping)):
        raise RenderSpecError("RenderSpec.source_bindings must be an array or object")
    if bindings is not None:
        normalized["source_bindings"] = bindings
    return normalized


def _selected_modality(decision: Mapping[str, Any]) -> str:
    selected = decision.get("selected_modality")
    modality = decision.get("modality")
    if selected is None and isinstance(modality, Mapping):
        selected = modality.get("selected", modality.get("chosen"))
    elif selected is None:
        selected = modality
    return str(selected or "").strip().lower().replace("_", "-")


def _decision_grammar(decision: Mapping[str, Any]) -> str:
    grammar = decision.get("selected_grammar", decision.get("visual_grammar", decision.get("grammar")))
    if isinstance(grammar, Mapping):
        grammar = grammar.get("kind", grammar.get("pattern", grammar.get("name")))
    return str(grammar or "").strip().lower().replace("_", "-")


GRAMMAR_TO_KIND = {
    "verdict-key-values": "__text__",
    "rich-verdict-evidence-source": "__text__",
    "html-verdict-evidence-source": "__text__",
    "rich-digest": "__text__",
    "html-digest": "__text__",
    "native-location": "__text__",
    "hero-evidence-source": "__unsupported__",
    "hero-card": "hero",
    "anchor": "anchor",
    "value-anchor": "anchor",
    "value-band": "anchor",
    "anchor-ruler": "anchor",
    "discount-premium": "anchor",
    "threshold": "threshold",
    "bullet": "threshold",
    "threshold-bullet": "threshold",
    "bullet-threshold": "threshold",
    "threshold-distance": "threshold",
    "comparison": "comparison",
    "aligned-bars": "comparison",
    "dot-plot": "comparison",
    "ranking": "ranking",
    "ranked-bars": "ranking",
    "trend": "trend",
    "line": "trend",
    "annotated-line": "trend",
    "line-event": "trend",
    "stacked-composition": "composition",
    "range-band": "uncertainty",
    "node-link": "network",
    "timeline": "timeline",
    "event-timeline": "timeline",
    "point-map": "point",
    "route": "route",
    "route-map": "route",
    "distance-route": "route",
    "radius": "radius",
    "radius-map": "radius",
    "sequence": "sequence",
    "motion-sequence": "sequence",
    "sequence-replay": "sequence",
}


def _evidence_paths(decision: Mapping[str, Any]) -> set:
    evidence = decision.get("evidence")
    paths = set()

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            source_path = value.get("source_path")
            if isinstance(source_path, str) and source_path.strip():
                paths.add(source_path.strip())
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(evidence)
    return paths


def _evidence_values(decision: Mapping[str, Any]) -> Dict[str, Any]:
    values = {}
    evidence = decision.get("evidence")
    if not isinstance(evidence, list):
        return values
    for item in evidence:
        if not isinstance(item, Mapping):
            continue
        path = item.get("source_path")
        if isinstance(path, str) and path.strip() and "value" in item:
            values[path.strip()] = item["value"]
    return values


def _resolve_render_path(render_spec: Mapping[str, Any], path: str) -> Any:
    matches = list(re.finditer(r"([^\.\[\]]+)|\[(\d+)\]", path))
    if not matches or "".join(match.group(0) for match in matches).replace(".", "") != path.replace(".", ""):
        raise RenderSpecError(f"invalid source_bindings target path: {path!r}")
    current: Any = render_spec
    for match in matches:
        key, index = match.group(1), match.group(2)
        if key is not None:
            if not isinstance(current, Mapping) or key not in current:
                raise RenderSpecError(f"source_bindings target does not exist: {path!r}")
            current = current[key]
        else:
            if not isinstance(current, list) or int(index) >= len(current):
                raise RenderSpecError(f"source_bindings target does not exist: {path!r}")
            current = current[int(index)]
    return current


def _numeric_decimal(value: Any) -> Optional[Decimal]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            result = Decimal(str(value))
            return result if result.is_finite() else None
        except InvalidOperation:
            return None
    if isinstance(value, str):
        try:
            result = Decimal(value.strip())
            return result if result.is_finite() else None
        except (InvalidOperation, ValueError):
            return None
    return None


def _values_equal(rendered: Any, evidence: Any) -> bool:
    if isinstance(rendered, (int, float, Decimal)) and not isinstance(rendered, bool):
        rendered_number = _numeric_decimal(rendered)
        evidence_number = _numeric_decimal(evidence)
        return (
            rendered_number is not None
            and evidence_number is not None
            and rendered_number == evidence_number
        )
    if isinstance(rendered, Mapping):
        candidate = evidence
        if isinstance(evidence, str):
            try:
                candidate = json.loads(evidence)
            except json.JSONDecodeError:
                return False
        if not isinstance(candidate, Mapping) or set(rendered) != set(candidate):
            return False
        return all(
            _values_equal(rendered[key], candidate[key])
            for key in rendered
        )
    if isinstance(rendered, (list, tuple)):
        candidate = evidence
        if isinstance(evidence, str):
            try:
                candidate = json.loads(evidence)
            except json.JSONDecodeError:
                return False
        if not isinstance(candidate, (list, tuple)) or len(rendered) != len(candidate):
            return False
        return all(
            _values_equal(rendered_item, evidence_item)
            for rendered_item, evidence_item in zip(rendered, candidate)
        )
    return type(rendered) is type(evidence) and rendered == evidence


def _structured_input(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("[", "{")):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value
    return value


def _operation_number(value: Any, operation: str) -> Decimal:
    candidate = _numeric_decimal(value)
    if candidate is None:
        raise RenderSpecError(f"derived operation {operation!r} requires numeric inputs")
    return candidate


def execute_binding_operation(operation: str, inputs: Sequence[Any]) -> Any:
    """Execute the audited, deterministic derived-binding operation registry."""
    values = [_structured_input(value) for value in inputs]
    if operation == "copy":
        if len(values) != 1:
            raise RenderSpecError("copy operation requires exactly one input")
        return values[0]
    if operation == "delta":
        if len(values) != 2:
            raise RenderSpecError("delta operation requires exactly two inputs")
        return _operation_number(values[0], operation) - _operation_number(values[1], operation)
    if operation == "ratio":
        if len(values) != 2:
            raise RenderSpecError("ratio operation requires exactly two inputs")
        denominator = _operation_number(values[1], operation)
        if denominator == 0:
            raise RenderSpecError("ratio operation denominator must not be zero")
        return _operation_number(values[0], operation) / denominator
    if operation == "percent_delta":
        if len(values) != 2:
            raise RenderSpecError("percent_delta operation requires exactly two inputs")
        denominator = _operation_number(values[1], operation)
        if denominator == 0:
            raise RenderSpecError("percent_delta denominator must not be zero")
        return (
            (_operation_number(values[0], operation) - denominator)
            / denominator
            * Decimal("100")
        )
    if operation == "sum":
        sequence = values[0] if len(values) == 1 and isinstance(values[0], list) else values
        return sum((_operation_number(value, operation) for value in sequence), Decimal("0"))
    if operation == "zip_items":
        if (
            len(values) != 2
            or not isinstance(values[0], list)
            or not isinstance(values[1], list)
            or len(values[0]) != len(values[1])
        ):
            raise RenderSpecError("zip_items requires two equal-length arrays")
        return [
            {"label": str(label), "value": value}
            for label, value in zip(values[0], values[1])
        ]
    if operation == "indexed_points":
        if len(values) != 1 or not isinstance(values[0], list):
            raise RenderSpecError("indexed_points requires one array")
        result = []
        for index, value in enumerate(values[0]):
            if isinstance(value, Mapping):
                point = dict(value)
                point.setdefault("label", str(index + 1))
            else:
                point = {"label": str(index + 1), "value": value}
            result.append(point)
        return result
    if operation == "sequence_frames":
        if len(values) != 1 or not isinstance(values[0], list):
            raise RenderSpecError("sequence_frames requires one array")
        result = []
        for index, value in enumerate(values[0]):
            if isinstance(value, Mapping):
                frame = dict(value)
                frame.setdefault("label", f"Step {index + 1}")
            else:
                frame = {"label": f"Step {index + 1}", "value": value}
            result.append(frame)
        return result
    if operation == "endpoint_points":
        if len(values) != 2:
            raise RenderSpecError("endpoint_points requires two endpoints")
        result = []
        for index, value in enumerate(values):
            if isinstance(value, Mapping):
                point = dict(value)
            elif (
                isinstance(value, (list, tuple))
                and len(value) == 2
                and all(_numeric_decimal(coordinate) is not None for coordinate in value)
            ):
                point = {"lat": value[0], "lon": value[1]}
            else:
                raise RenderSpecError(
                    "endpoint_points entries must be point objects or [lat, lon] pairs"
                )
            point.setdefault("label", "Origin" if index == 0 else "Destination")
            result.append(point)
        return result
    if operation == "node_objects":
        if len(values) != 1 or not isinstance(values[0], list):
            raise RenderSpecError("node_objects requires one array")
        result = []
        for index, value in enumerate(values[0]):
            if isinstance(value, Mapping):
                node = dict(value)
                node.setdefault("id", f"n{index + 1}")
                node.setdefault("label", str(node["id"]))
            else:
                node = {"id": str(value), "label": str(value)}
            result.append(node)
        return result
    if operation == "edge_objects":
        if len(values) != 1 or not isinstance(values[0], list):
            raise RenderSpecError("edge_objects requires one array")
        result = []
        for value in values[0]:
            if isinstance(value, Mapping) and "source" in value and "target" in value:
                result.append(dict(value))
            elif isinstance(value, (list, tuple)) and len(value) >= 2:
                result.append({"source": str(value[0]), "target": str(value[1])})
            else:
                raise RenderSpecError("edge_objects entries need source/target pairs")
        return result
    if operation == "timeline_events":
        if len(values) != 1 or not isinstance(values[0], list):
            raise RenderSpecError("timeline_events requires one array")
        result = []
        for value in values[0]:
            if isinstance(value, Mapping) and "time" in value and "label" in value:
                result.append({"time": value["time"], "label": value["label"]})
            elif isinstance(value, (list, tuple)) and len(value) >= 2:
                result.append({"time": value[0], "label": value[1]})
            else:
                raise RenderSpecError("timeline_events entries need time/label pairs")
        return result
    if operation == "interval_band":
        if (
            len(values) != 1
            or not isinstance(values[0], (list, tuple))
            or len(values[0]) != 2
        ):
            raise RenderSpecError("interval_band requires one [low, high] pair")
        return [
            {
                "label": "Confidence interval",
                "low": values[0][0],
                "high": values[0][1],
            }
        ]
    if operation == "before_after_items":
        if (
            len(values) != 3
            or not all(isinstance(value, list) for value in values)
            or not (len(values[0]) == len(values[1]) == len(values[2]))
        ):
            raise RenderSpecError(
                "before_after_items requires categories, previous, and current arrays"
            )
        result = []
        for label, previous, current in zip(values[0], values[1], values[2]):
            result.append({"label": f"{label} · before", "value": previous})
            result.append({"label": f"{label} · after", "value": current})
        return result
    if operation == "format_value_unit":
        if len(values) != 2:
            raise RenderSpecError("format_value_unit requires value and unit")
        return f"{values[0]} {values[1]}".strip()
    raise RenderSpecError(f"unknown derived binding operation: {operation!r}")


def _binding_values(bindings: Any) -> list:
    if isinstance(bindings, Mapping):
        return list(bindings.values())
    return list(bindings)


_STYLE_DATA_KEYS = {
    "domain",
    "decimals",
    "max_items",
    "max_frames",
    "duration_ms",
    "preserve_order",
    "directed",
    "primary",
    "prefix",
    "suffix",
    "current_label",
    "anchor_label",
    "axis_label",
    "value_label",
    "estimate_label",
    "interval_label",
    "composition_label",
    "total_label",
    "start_label",
    "end_label",
    "location_label",
}


def _required_binding_paths(render_spec: Mapping[str, Any]) -> set:
    """Collect displayed factual leaves; visual/style controls are exempt."""
    required = set()

    def visit(value: Any, path: str, key: str = "") -> None:
        if key in _STYLE_DATA_KEYS or key == "color" or key.endswith("_color"):
            return
        if isinstance(value, Mapping):
            for child_key, child in value.items():
                visit(child, f"{path}.{child_key}", str(child_key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]", key)
        elif value is not None and value != "":
            required.add(path)

    visit(render_spec.get("data", {}), "data")
    visit(render_spec.get("meta", {}), "meta")
    if render_spec.get("title"):
        required.add("title")
    if render_spec.get("subtitle"):
        required.add("subtitle")
    return required


def _validate_source_bindings(render_spec: Mapping[str, Any], decision: Mapping[str, Any]) -> Tuple[str, str]:
    bindings = render_spec.get("source_bindings")
    if bindings is None:
        raise RenderSpecError("bundle RenderSpec.source_bindings is required")
    if not isinstance(bindings, Mapping) or not bindings:
        raise RenderSpecError(
            "bundle RenderSpec.source_bindings must be an object keyed by RenderSpec path"
        )
    evidence_paths = _evidence_paths(decision)
    evidence_values = _evidence_values(decision)
    if not evidence_paths:
        raise RenderSpecError("bundle VisualSpec has no evidence.source_path values")
    consumed_evidence_paths = set()
    for target, binding in bindings.items():
        if not isinstance(binding, Mapping):
            raise RenderSpecError(f"source_bindings[{target!r}] must be an object")
        direct_path = binding.get("jsonpath", binding.get("source_path"))
        derived_inputs = binding.get("inputs")
        spec_field = binding.get("spec_field")
        if spec_field is not None:
            raise RenderSpecError(
                f"source_bindings[{target!r}] spec_field is not source-traceable; "
                "bind a copy operation to VisualSpec evidence"
            )
        selected_kinds = sum(
            item is not None for item in (direct_path, derived_inputs)
        )
        if selected_kinds > 1:
            raise RenderSpecError(
                f"source_bindings[{target!r}] must use exactly one binding mode"
            )
        if str(target) in {"title", "subtitle"} and direct_path is not None:
            raise RenderSpecError(
                f"source_bindings[{target!r}] must use the evidence-backed copy operation"
            )
        if direct_path is not None:
            if not isinstance(direct_path, str) or direct_path not in evidence_paths:
                raise RenderSpecError(
                    f"source_bindings[{target!r}] path {direct_path!r} "
                    "is absent from VisualSpec evidence"
                )
            if direct_path not in evidence_values:
                raise RenderSpecError(
                    f"VisualSpec evidence {direct_path!r} has no value for direct binding"
                )
            target_value = _resolve_render_path(render_spec, str(target))
            if not _values_equal(target_value, evidence_values[direct_path]):
                raise RenderSpecError(
                    f"direct binding value mismatch for {target!r} "
                    f"against VisualSpec evidence {direct_path!r}"
                )
            consumed_evidence_paths.add(direct_path)
        elif derived_inputs is not None:
            operation = str(binding.get("operation", "")).strip()
            verified_result_present = "verified_result" in binding
            if (
                not isinstance(derived_inputs, list)
                or not derived_inputs
                or not all(isinstance(item, str) and item in evidence_paths for item in derived_inputs)
                or not operation
                or not verified_result_present
                or any(source_path not in evidence_values for source_path in derived_inputs)
            ):
                raise RenderSpecError(
                    f"source_bindings[{target!r}] derived binding needs "
                    "evidence-backed inputs, operation, and verified_result"
                )
            computed = execute_binding_operation(
                operation,
                [evidence_values[source_path] for source_path in derived_inputs],
            )
            if not _values_equal(computed, binding["verified_result"]):
                raise RenderSpecError(
                    f"derived binding verified_result mismatch for {target!r}"
                )
            target_value = _resolve_render_path(render_spec, str(target))
            if not _values_equal(target_value, computed):
                raise RenderSpecError(
                    f"derived binding target mismatch for {target!r}"
                )
            if str(target) in {"title", "subtitle"} and operation != "copy":
                raise RenderSpecError(
                    f"source_bindings[{target!r}] permits only the copy operation"
                )
            consumed_evidence_paths.update(derived_inputs)
        else:
            raise RenderSpecError(
                f"source_bindings[{target!r}] needs jsonpath/source_path or "
                "inputs+operation+verified_result"
            )
    trust_roles = {
        "unit",
        "source",
        "time",
        "anchor",
        "threshold",
        "series",
        "geo_point",
        "geo_path",
        "geo_region",
        "network",
        "sequence",
        "uncertainty",
    }
    required_trust_paths = {
        str(item["source_path"]).strip()
        for item in decision.get("evidence", [])
        if isinstance(item, Mapping)
        and str(item.get("role", "")).strip().lower() in trust_roles
        and isinstance(item.get("source_path"), str)
        and str(item["source_path"]).strip()
    }
    unconsumed_trust = sorted(required_trust_paths - consumed_evidence_paths)
    if unconsumed_trust:
        raise RenderSpecError(
            "VisualSpec trust evidence is not consumed by RenderSpec bindings: "
            + ", ".join(unconsumed_trust)
        )
    required = _required_binding_paths(render_spec)
    targets = {str(target) for target in bindings}

    def covered(path: str) -> bool:
        return any(
            path == target
            or path.startswith(target + ".")
            or path.startswith(target + "[")
            for target in targets
        )

    missing = sorted(path for path in required if not covered(path))
    if missing:
        raise RenderSpecError(
            "RenderSpec factual leaves missing source_bindings: "
            + ", ".join(missing[:12])
        )
    return "verified", ""


def _validate_bundle(decision: Mapping[str, Any], render_spec: Dict[str, Any]) -> Dict[str, Any]:
    try:
        try:
            import visual_spec as visual_spec_module
        except ImportError:  # pragma: no cover
            from . import visual_spec as visual_spec_module
        visual_spec_module.VisualSpec.from_dict(decision)
    except (KeyError, TypeError, ValueError) as exc:
        raise RenderSpecError(f"invalid VisualSpec: {exc}") from exc
    selected = _selected_modality(decision)
    if not selected:
        raise RenderSpecError("VisualSpec.selected_modality is required in bundle mode")
    modality_aliases = {
        "static": "image",
        "static-image": "image",
        "chart": "image",
        "map": "image",
        "gif": "video",
        "motion": "video",
        "animation": "video",
    }
    selected = modality_aliases.get(selected, selected)
    expected = "video" if render_spec["kind"] == "sequence" else "image"
    if selected != expected:
        raise RenderSpecError(
            f"VisualSpec selected_modality={selected!r} conflicts with "
            f"RenderSpec kind={render_spec['kind']!r} ({expected})"
        )
    grammar = _decision_grammar(decision)
    mapped_kind = GRAMMAR_TO_KIND.get(grammar)
    if mapped_kind is None:
        raise RenderSpecError(
            f"VisualSpec grammar={grammar!r} has no audited RenderSpec renderer mapping"
        )
    if mapped_kind == "__text__":
        raise RenderSpecError(
            f"VisualSpec grammar={grammar!r} is a text grammar and must not enter raster rendering"
        )
    if mapped_kind == "__unsupported__":
        raise RenderSpecError(
            f"VisualSpec grammar={grammar!r} has no implemented renderer; refusing silent substitution"
        )
    if mapped_kind != render_spec["kind"]:
        raise RenderSpecError(
            f"VisualSpec grammar={grammar!r} maps to {mapped_kind!r}, "
            f"not RenderSpec kind={render_spec['kind']!r}"
        )
    binding_status, binding_warning = _validate_source_bindings(render_spec, decision)
    render_spec["_visual_spec"] = dict(decision)
    render_spec["_decision_grammar"] = grammar
    render_spec["_source_binding_status"] = binding_status
    render_spec["_source_binding_warning"] = binding_warning
    return render_spec


def load_render_spec(source: Any) -> Dict[str, Any]:
    if isinstance(source, Mapping):
        payload = source
    else:
        path = Path(source)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RenderSpecError(f"cannot read RenderSpec {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise RenderSpecError("RenderSpec input must be a JSON object")
    if "render_spec" in payload or "visual_spec" in payload:
        decision = payload.get("visual_spec")
        render_payload = payload.get("render_spec")
        if not isinstance(decision, Mapping) or not isinstance(render_payload, Mapping):
            raise RenderSpecError("bundle requires object-valued visual_spec and render_spec")
        return _validate_bundle(decision, normalize_render_spec(render_payload))
    return normalize_render_spec(payload)


def canvas(
    spec: Mapping[str, Any],
    height: int,
    *,
    default_width: int = 1200,
) -> Tuple[Image.Image, ImageDraw.ImageDraw, BBox, L.Palette]:
    """Create the shared card shell and return the drawable content rectangle."""
    pal = palette_for(spec)
    width = int(spec.get("width", default_width))
    width = max(640, min(1600, width))
    margin = max(22, int(width * 0.023))
    left = margin + max(38, int(width * 0.04))
    right = width - margin - max(34, int(width * 0.035))
    title = str(spec["title"])
    subtitle = str(spec.get("subtitle", ""))
    title_lines = L.wrap_text(title, MIN_TITLE_FONT, True, right - left, 4)
    subtitle_lines = (
        L.wrap_text(subtitle, MIN_BODY_FONT, False, right - left, 3)
        if subtitle
        else []
    )
    height += (len(title_lines) - 1) * 62 + max(0, len(subtitle_lines) - 1) * 45
    height = max(480, min(2600, int(height)))
    image = Image.new("RGB", (width, height), pal.bg)
    image.info["text_truncated"] = (
        "true"
        if any(line.endswith("…") for line in title_lines + subtitle_lines)
        else "false"
    )
    draw = ImageDraw.Draw(image)
    card = (margin, margin, width - margin, height - margin)
    image.info["card_bbox"] = json.dumps(list(card), separators=(",", ":"))
    radius = max(24, int(width * 0.026))
    draw.rounded_rectangle(card, radius=radius, fill=pal.card, outline=pal.line, width=2)
    rail_w = max(9, int(width * 0.009))
    draw.rounded_rectangle(
        (margin, margin, margin + rail_w, height - margin),
        radius=radius,
        fill=pal.accent,
    )
    draw.rectangle(
        (margin + rail_w // 2, margin + radius // 2, margin + rail_w, height - margin - radius // 2),
        fill=pal.accent,
    )

    y = margin + 31
    for line in title_lines:
        draw.text(
            (left, y),
            line,
            font=font(line, MIN_TITLE_FONT, True),
            fill=pal.text,
        )
        y += 62
    header_bottom = y + 15
    if subtitle_lines:
        y += 2
        for line in subtitle_lines:
            draw.text((left, y), line, font=font(line, MIN_BODY_FONT), fill=pal.muted)
            y += 45
        header_bottom = y + 14
    draw.line((left, header_bottom, right, header_bottom), fill=pal.line, width=2)

    meta = spec.get("meta", {})
    footer_parts = [
        str(meta.get("source", "")).strip(),
        str(meta.get("timestamp", "")).strip(),
    ]
    footer = "  ·  ".join(part for part in footer_parts if part) or "TG Watch visual"
    footer_y = height - margin - 64
    draw.line((left, footer_y - 20, right, footer_y - 20), fill=pal.line, width=1)
    fit_text(
        draw,
        (left, footer_y),
        footer,
        max_width=right - left,
        size=MIN_METADATA_FONT,
        min_size=MIN_METADATA_FONT,
        color=pal.muted,
    )
    content = (left, header_bottom + 30, right, footer_y - 48)
    return image, draw, content, pal


def fit_text(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    text: str,
    *,
    max_width: int,
    size: int,
    color: RGB,
    bold: bool = False,
    min_size: int = 14,
    anchor: Optional[str] = None,
) -> int:
    """Draw one line, shrinking only when necessary; return the chosen size."""
    chosen = int(size)
    while chosen > min_size:
        chosen_font = font(text, chosen, bold)
        if draw.textlength(str(text), font=chosen_font) <= max_width:
            break
        chosen -= 1
    rendered = str(text)
    chosen_font = font(rendered, chosen, bold)
    if draw.textlength(rendered, font=chosen_font) > max_width:
        tail = rendered.rstrip()
        while tail and draw.textlength(tail + "…", font=chosen_font) > max_width:
            tail = tail[:-1]
        rendered = tail + "…"
        draw._image.info["text_truncated"] = "true"
    draw.text(xy, rendered, font=chosen_font, fill=color, anchor=anchor)
    return chosen


def metadata_for(spec: Mapping[str, Any], content_bbox: BBox, pal: L.Palette) -> Dict[str, str]:
    text_probe = canonical_render_spec(spec)
    font_path = resolve_font_path(text_probe, False)
    meta = spec.get("meta", {})
    decision = spec.get("_visual_spec")
    bindings = spec.get("source_bindings")
    if "_source_binding_status" in spec:
        binding_status = str(spec["_source_binding_status"])
        binding_warning = str(spec.get("_source_binding_warning", ""))
    elif bindings is None:
        binding_status = "standalone-unbound"
        binding_warning = "standalone RenderSpec has no evidence-verified source_bindings"
    else:
        binding_status = "standalone-unverified"
        binding_warning = "standalone RenderSpec source_bindings cannot be verified without VisualSpec evidence"
    metadata = {
        "render_spec_version": str(spec.get("version", "1.0")),
        "render_kind": str(spec["kind"]),
        "title": str(spec["title"]),
        "source": str(meta.get("source", "")),
        "timestamp": str(meta.get("timestamp", "")),
        "render_spec_sha256": render_spec_digest(spec),
        "content_bbox": json.dumps(list(content_bbox), separators=(",", ":")),
        "canvas_background_color": color_hex(pal.bg),
        "background_color": color_hex(pal.card),
        "foreground_color": color_hex(pal.text),
        "cjk_required": "true" if contains_cjk(_public_render_spec(spec)) else "false",
        "cjk_sample": cjk_sample(_public_render_spec(spec)),
        "font_path": font_path,
        "source_binding_status": binding_status,
        "source_binding_warning": binding_warning,
        "traceability_status": "verified" if binding_status == "verified" else "unverified",
        "min_title_font_px": str(MIN_TITLE_FONT),
        "min_body_font_px": str(MIN_BODY_FONT),
        "min_metadata_font_px": str(MIN_METADATA_FONT),
    }
    if isinstance(decision, Mapping):
        metadata["visual_spec_sha256"] = decision_spec_digest(decision)
        metadata["selected_modality"] = _selected_modality(decision)
        metadata["decision_grammar"] = str(spec.get("_decision_grammar", ""))
    if bindings is not None:
        metadata["source_bindings_sha256"] = hashlib.sha256(
            json.dumps(bindings, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    return metadata


def save_png(
    image: Image.Image,
    output: Any,
    spec: Mapping[str, Any],
    content_bbox: BBox,
    pal: L.Palette,
    *,
    extra_metadata: Optional[Mapping[str, Any]] = None,
) -> Path:
    out = Path(output)
    if out.suffix.lower() != ".png":
        raise RenderSpecError("static visuals must use a .png output path")
    out.parent.mkdir(parents=True, exist_ok=True)
    metadata = metadata_for(spec, content_bbox, pal)
    metadata["card_bbox"] = str(image.info.get("card_bbox", ""))
    metadata["text_truncated"] = str(image.info.get("text_truncated", "false"))
    if extra_metadata:
        metadata.update({str(k): str(v) for k, v in extra_metadata.items()})
    pnginfo = PngImagePlugin.PngInfo()
    for key, value in metadata.items():
        pnginfo.add_text(key, value)
    image.save(out, format="PNG", optimize=True, pnginfo=pnginfo)
    return out


def render(spec_source: Any, output: Any) -> Path:
    spec = load_render_spec(spec_source)
    kind = spec["kind"]
    if kind in CHART_KINDS:
        try:
            import render_chart
        except ImportError:  # pragma: no cover
            from . import render_chart
        return render_chart.render_chart(spec, output)
    if kind in MAP_KINDS:
        try:
            import render_map
        except ImportError:  # pragma: no cover
            from . import render_map
        return render_map.render_map(spec, output)
    try:
        import render_motion
    except ImportError:  # pragma: no cover
        from . import render_motion
    return render_motion.render_motion(spec, output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a TG Watch RenderSpec or visual/render bundle.")
    parser.add_argument("--spec", required=True, help="Path to RenderSpec or bundle JSON")
    parser.add_argument("--out", required=True, help="Output .png or .gif path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        result = render(args.spec, args.out)
    except RenderSpecError as exc:
        raise SystemExit(f"RenderSpec error: {exc}") from exc
    print(result)


if __name__ == "__main__":
    main()
