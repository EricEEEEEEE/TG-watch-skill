#!/usr/bin/env python3
"""Render VisualSpec copy as portable rich blocks plus safe HTML fallback.

The rich JSON is an internal adapter contract, not a network request and not a
claim that its shape is Telegram's wire schema.  A delivery adapter can map the
blocks to current Telegram Rich Message primitives when available.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

try:
    from .visual_spec import VisualDatum, VisualSpec
except ImportError:
    from visual_spec import VisualDatum, VisualSpec  # type: ignore


def _datum_value(datum: VisualDatum) -> str:
    return "%s %s" % (datum.value, datum.unit) if datum.unit else datum.value


def _truncate_plain(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 0:
        return ""
    if limit == 1:
        return "…"
    return value[: limit - 1].rstrip() + "…"


def _plain_chunks(value: str, limit: int) -> List[str]:
    """Split text without losing characters or creating an empty chunk."""

    if limit <= 0:
        raise ValueError("message text budget must be positive")
    if not value:
        return [""]
    return [value[index : index + limit] for index in range(0, len(value), limit)]


def _rich_payload(
    spec: VisualSpec,
    blocks: List[Dict[str, Any]],
    *,
    part_index: int,
    part_count: int,
) -> Dict[str, Any]:
    return {
        "schema": "tg-watch.rich-message.v1",
        "blocks": blocks,
        "metadata": {
            "primary_question": spec.primary_question,
            "selected_modality": spec.selected_modality.value,
            "visual_grammar": spec.grammar,
            "intents": [intent.value for intent in spec.intents],
            "omitted_evidence": 0,
            "content_complete": True,
            "part_index": part_index,
            "part_count": part_count,
        },
    }


def build_rich_messages(spec: VisualSpec) -> List[Dict[str, Any]]:
    """Return one or more lossless renderer-neutral rich payloads."""

    limit = spec.feature_gate.max_rich_text_chars
    atoms: List[tuple[Dict[str, Any], int]] = []
    for text in _plain_chunks(spec.headline, limit):
        atoms.append(({"type": "heading", "level": 1, "text": text}, len(text)))
    if spec.answer:
        for text in _plain_chunks(spec.answer, limit):
            atoms.append(({"type": "quote", "text": text}, len(text)))
    for datum in spec.evidence:
        label = datum.label
        value = _datum_value(datum)
        if len(label) + len(value) <= limit:
            rows = [(label, value)]
        else:
            # Preserve every character. A very large datum becomes continued
            # evidence rows rather than being silently dropped.
            combined = "%s: %s" % (label, value)
            rows = [("Evidence", part) for part in _plain_chunks(combined, max(1, limit - 8))]
        for row_label, row_value in rows:
            row = {
                "cells": [row_label, row_value],
                "role": datum.role.value,
                "source_path": datum.source_path,
            }
            cost = len(row_label) + len(row_value)
            atoms.append(
                (
                    {
                        "type": "table",
                        "columns": ["Item", "Value"],
                        "rows": [row],
                    },
                    cost,
                )
            )

    block_groups: List[List[Dict[str, Any]]] = [[]]
    used = 0
    for block, cost in atoms:
        if block_groups[-1] and used + cost > limit:
            block_groups.append([])
            used = 0
        block_groups[-1].append(block)
        used += cost
    part_count = len(block_groups)
    return [
        _rich_payload(
            spec,
            blocks,
            part_index=index + 1,
            part_count=part_count,
        )
        for index, blocks in enumerate(block_groups)
    ]


def build_rich_message(spec: VisualSpec) -> Dict[str, Any]:
    """Return a complete rich envelope, with continuations when required."""

    messages = build_rich_messages(spec)
    first = dict(messages[0])
    if len(messages) > 1:
        first["continuations"] = messages[1:]
    return first


def _bounded_bold(value: str, limit: int) -> str:
    """Return balanced HTML without truncating inside an escaped entity."""

    escaped = html.escape(value, quote=True)
    wrapped = "<b>%s</b>" % escaped
    if len(wrapped) <= limit:
        return wrapped
    if limit < len("<b>…</b>"):
        return "…"[:limit]
    low, high = 0, len(value)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = "<b>%s…</b>" % html.escape(value[:middle].rstrip(), quote=True)
        if len(candidate) <= limit:
            low = middle
        else:
            high = middle - 1
    return "<b>%s…</b>" % html.escape(value[:low].rstrip(), quote=True)


def _escaped_plain_chunks(value: str, limit: int) -> List[str]:
    """Split untrusted text into escaped chunks without cutting entities."""

    if limit <= 0:
        raise ValueError("HTML text budget must be positive")
    remaining = value
    chunks: List[str] = []
    while remaining:
        low, high = 1, len(remaining)
        best = 0
        while low <= high:
            middle = (low + high) // 2
            escaped = html.escape(remaining[:middle], quote=True)
            if len(escaped) <= limit:
                best = middle
                low = middle + 1
            else:
                high = middle - 1
        if best == 0:
            raise ValueError("HTML text budget is too small for escaped content")
        chunks.append(html.escape(remaining[:best], quote=True))
        remaining = remaining[best:]
    return chunks or [""]


def _tagged_html_chunks(value: str, tag: str, limit: int) -> List[str]:
    opening, closing = "<%s>" % tag, "</%s>" % tag
    content_limit = limit - len(opening) - len(closing)
    if content_limit <= 0:
        raise ValueError("HTML text budget is too small for balanced markup")
    return [
        opening + chunk + closing
        for chunk in _escaped_plain_chunks(value, content_limit)
    ]


def render_html_fallback_parts(spec: VisualSpec) -> List[str]:
    """Render lossless, balanced Telegram-safe HTML message parts."""

    limit = spec.feature_gate.max_html_chars
    fragments: List[str] = []
    fragments.extend(_tagged_html_chunks(spec.headline, "b", limit))
    if spec.answer:
        fragments.extend(_tagged_html_chunks(spec.answer, "blockquote", limit))
    for datum in spec.evidence:
        line = "<b>%s</b>: %s" % (
            html.escape(datum.label, quote=True),
            html.escape(_datum_value(datum), quote=True),
        )
        if len(line) <= limit:
            fragments.append(line)
        else:
            plain = "%s: %s" % (datum.label, _datum_value(datum))
            fragments.extend(_escaped_plain_chunks(plain, limit))

    messages: List[str] = []
    current: List[str] = []
    for fragment in fragments:
        candidate = "\n".join(current + [fragment])
        if current and len(candidate) > limit:
            messages.append("\n".join(current))
            current = []
        current.append(fragment)
    if current:
        messages.append("\n".join(current))
    return messages or [""]


def render_html_fallback(spec: VisualSpec) -> str:
    """Render a single fallback, refusing silent loss when continuation is needed."""

    parts = render_html_fallback_parts(spec)
    if len(parts) != 1:
        raise ValueError(
            "HTML fallback requires %d parts; use render_message() or "
            "render_html_fallback_parts()" % len(parts)
        )
    return parts[0]


def _native_location_payload(spec: VisualSpec) -> Optional[Dict[str, Any]]:
    """Compile source-traceable point evidence into an internal native carrier."""

    latitude = None
    longitude = None
    latitude_path = ""
    longitude_path = ""
    for datum in spec.evidence:
        leaf = datum.source_path.rsplit(".", 1)[-1].lower()
        try:
            numeric = float(datum.value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric):
            continue
        if leaf in {"latitude", "lat"}:
            latitude, latitude_path = numeric, datum.source_path
        elif leaf in {"longitude", "lon", "lng"}:
            longitude, longitude_path = numeric, datum.source_path
    if (
        latitude is None
        or longitude is None
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        return None
    return {
        "schema": "tg-watch.native-location.v1",
        "latitude": latitude,
        "longitude": longitude,
        "label": spec.headline,
        "source_paths": {
            "latitude": latitude_path,
            "longitude": longitude_path,
        },
    }


def render_message(spec: VisualSpec) -> Dict[str, Any]:
    """Return selected text representation and an always-available HTML form."""

    html_parts = render_html_fallback_parts(spec)
    html_fallback = html_parts[0]
    html_continuations = html_parts[1:]
    native_location = (
        _native_location_payload(spec)
        if spec.grammar == "native-location"
        else None
    )
    if native_location is not None:
        selected_format = "native_location"
        payload = native_location
        fallback = {
            "format": "html",
            "parse_mode": "HTML",
            "payload": html_fallback,
            "continuations": html_continuations,
            "part_count": len(html_parts),
        }
    elif spec.feature_gate.rich_messages:
        selected_format = "rich_message"
        payload: Any = build_rich_message(spec)
        fallback: Optional[Dict[str, Any]] = {
            "format": "html",
            "parse_mode": "HTML",
            "payload": html_fallback,
            "continuations": html_continuations,
            "part_count": len(html_parts),
        }
    else:
        selected_format = "html"
        payload = html_fallback
        fallback = None
    result: Dict[str, Any] = {
        "selected_format": selected_format,
        "visual_modality": spec.selected_modality.value,
        "payload": payload,
    }
    if selected_format == "html":
        result["parse_mode"] = "HTML"
        result["continuations"] = html_continuations
        result["part_count"] = len(html_parts)
    if fallback is not None:
        result["fallback"] = fallback
    return result


def _read_spec(path: str) -> VisualSpec:
    if path == "-":
        raw = json.load(sys.stdin)
    else:
        with Path(path).open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    if not isinstance(raw, Mapping):
        raise ValueError("VisualSpec JSON must be an object")
    return VisualSpec.from_dict(raw)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render VisualSpec text as rich JSON and HTML fallback."
    )
    parser.add_argument("input", help="VisualSpec JSON path, or - for stdin")
    parser.add_argument(
        "--format",
        choices=("auto", "rich", "html"),
        default="auto",
        help="output selected envelope, rich blocks, or HTML only",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        spec = _read_spec(args.input)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    if args.format == "rich":
        output: Any = build_rich_message(spec)
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif args.format == "html":
        sys.stdout.write(render_html_fallback(spec) + "\n")
    else:
        json.dump(
            render_message(spec),
            sys.stdout,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
