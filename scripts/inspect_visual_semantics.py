#!/usr/bin/env python3
"""Infer a validated VisualSpec from representative JSON output.

This is a deterministic baseline for agents: it detects domain-independent
semantic roles, scores text/image/video, then delegates media selection to the
VisualSpec contract.  It never invents values or business conclusions.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    from .visual_spec import (
        FeatureGate,
        ModalityScores,
        SemanticRole,
        VisualDatum,
        VisualIntent,
        VisualSpec,
        make_visual_spec,
    )
except ImportError:
    from visual_spec import (  # type: ignore
        FeatureGate,
        ModalityScores,
        SemanticRole,
        VisualDatum,
        VisualIntent,
        VisualSpec,
        make_visual_spec,
    )


DEMO_PAYLOAD: Dict[str, Any] = {
    "title": "rswETH / ETH",
    "summary": "Market price is 1.56% below the 7D p95 anchor.",
    "current_price": 3210,
    "fair_anchor_price": 3261,
    "discount_percent": 1.56,
    "source": "Curve / oracle",
    "timestamp": "2026-07-23T10:30:00+08:00",
    "unit": "USD",
}

_ROLE_KEYWORDS: Tuple[Tuple[SemanticRole, Tuple[str, ...]], ...] = (
    (SemanticRole.ANCHOR, ("anchor", "fair_value", "reference", "benchmark", "nav", "peg", "锚", "公允")),
    (SemanticRole.THRESHOLD, ("threshold", "limit", "trigger", "target", "buffer", "ceiling", "floor", "阈值", "上限", "下限")),
    (SemanticRole.DELTA, ("delta", "change", "discount", "premium", "spread", "gap", "difference", "pct", "percent", "变化", "折价", "溢价", "价差")),
    (SemanticRole.INTERVAL, ("interval", "window", "duration", "range", "period", "区间", "窗口")),
    (SemanticRole.SERIES, ("series", "history", "trend", "timeseries", "candles", "points", "sparkline", "历史", "趋势")),
    (SemanticRole.GEO_POINT, ("latitude", "longitude", "lat", "lon", "lng", "location", "coordinate", "地点", "坐标", "位置")),
    (SemanticRole.GEO_PATH, ("route", "path", "trajectory", "origin", "destination", "distance", "路线", "路径", "轨迹", "距离")),
    (SemanticRole.GEO_REGION, ("region", "polygon", "radius", "geofence", "boundary", "区域", "半径", "边界")),
    (SemanticRole.NETWORK, ("network", "topology", "nodes", "edges", "dependency", "graph", "拓扑", "依赖")),
    (SemanticRole.SEQUENCE, ("timeline", "events", "steps", "sequence", "phases", "时间线", "步骤", "阶段")),
    (SemanticRole.UNCERTAINTY, ("confidence", "uncertainty", "probability", "lower", "upper", "p10", "p90", "置信", "概率", "不确定")),
    (SemanticRole.STATUS, ("status", "state", "severity", "health", "result", "状态", "等级")),
    (SemanticRole.SOURCE, ("source", "venue", "provider", "出处", "来源")),
    (SemanticRole.TIME, ("time", "timestamp", "date", "updated", "created", "时间", "日期")),
    (SemanticRole.UNIT, ("unit", "currency", "denomination", "单位", "币种")),
    (SemanticRole.CATEGORY, ("category", "group", "segment", "type", "label", "分类", "分组")),
)

_INTERNAL_KEYS = {
    "visual_hints",
    "primary_question",
    "question",
}


def _normalize_key(value: str) -> str:
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return re.sub(r"[^a-zA-Z0-9\u3400-\u9fff]+", "_", snake).strip("_").lower()


def _flatten(
    value: Any, path: str = "$", key: str = ""
) -> Iterable[Tuple[str, str, Any]]:
    if isinstance(value, Mapping):
        for child_key, child_value in value.items():
            child = str(child_key)
            child_path = "%s.%s" % (path, child) if path != "$" else "$.%s" % child
            yield from _flatten(child_value, child_path, child)
        return
    yield path, _normalize_key(key), value


def _matches(key: str, words: Sequence[str]) -> bool:
    tokens = set(key.split("_"))
    for word in words:
        normalized = _normalize_key(word)
        if normalized in tokens or (
            len(normalized) >= 5 and normalized in key
        ):
            return True
    return False


def _detect_roles(payload: Mapping[str, Any]) -> Tuple[SemanticRole, ...]:
    roles: List[SemanticRole] = []
    numeric_count = 0
    for _, key, value in _flatten(payload):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            numeric_count += 1
            roles.append(SemanticRole.SCALAR)
        for role, words in _ROLE_KEYWORDS:
            if _matches(key, words):
                roles.append(role)
        if isinstance(value, list):
            if value and all(
                isinstance(item, (int, float)) and not isinstance(item, bool)
                for item in value
            ):
                roles.append(SemanticRole.SCALAR)
                if _matches(
                    key,
                    (
                        "series",
                        "history",
                        "trend",
                        "timeseries",
                        "candles",
                        "points",
                        "历史",
                        "趋势",
                    ),
                ):
                    roles.append(SemanticRole.SERIES)
                else:
                    roles.append(SemanticRole.CATEGORY)
            elif len(value) > 1:
                roles.append(SemanticRole.CATEGORY)
    if numeric_count == 0 and not roles:
        roles.append(SemanticRole.STATUS)
    return tuple(dict.fromkeys(roles))


def _detect_intents(
    payload: Mapping[str, Any],
    roles: Sequence[SemanticRole],
    primary_question: str = "",
) -> Tuple[VisualIntent, ...]:
    role_set = set(roles)
    normalized_keys = [key for _, key, _ in _flatten(payload)]
    keys = " ".join(normalized_keys)
    descriptive_values = [
        str(payload.get(key, ""))
        for key in ("label", "title", "name", "headline")
        if isinstance(payload.get(key), str)
    ]
    context = " ".join([primary_question, keys] + descriptive_values).lower()
    intents: List[VisualIntent] = []
    state_count = _meaningful_state_count(payload)

    def has_any(*phrases: str) -> bool:
        return any(phrase.lower() in context for phrase in phrases)

    before_tokens = ("before", "previous", "prior", "old", "之前", "变化前")
    after_tokens = ("after", "current", "new", "现在", "变化后")
    has_before = any(
        any(_matches(key, (token,)) for token in before_tokens)
        for key in normalized_keys
    )
    has_after = any(
        any(_matches(key, (token,)) for token in after_tokens)
        for key in normalized_keys
    )
    explicit_before_after = (has_before and has_after) or any(
        "before_after" in key or "前后" in key for key in normalized_keys
    )

    # The user's visual question owns primary-intent priority. These checks
    # describe relationships and never rely on evaluation-case identifiers.
    if has_any(
        "state evolve",
        "state evolved",
        "状态如何变化",
        "状态演变",
        "threshold crossing",
        "transition",
    ) and state_count >= 3:
        intents.append(VisualIntent.STATE_CHANGE)
    elif SemanticRole.GEO_PATH in role_set or has_any(
        "origin", "destination", "route", "affected area", "路线", "路径"
    ):
        intents.append(VisualIntent.DISTANCE_ROUTE)
    elif SemanticRole.GEO_POINT in role_set and has_any(
        "where", "location", "event point", "位置", "哪里"
    ):
        intents.append(VisualIntent.GEO_LOCATION)
    elif has_any("top items", "top movers", "ranking", "ranked", "排行", "排名"):
        intents.append(VisualIntent.RANKING)
    elif has_any(
        "makes up",
        "portfolio mix",
        "composition",
        "allocation",
        "占比",
        "构成",
    ):
        intents.append(VisualIntent.COMPOSITION)
    elif SemanticRole.SEQUENCE in role_set or has_any(
        "what happened", "in what order", "timeline", "先后", "时间线"
    ):
        intents.append(VisualIntent.TIMELINE)
    elif (
        SemanticRole.ANCHOR in role_set
        and SemanticRole.DELTA in role_set
        and has_any("discount or premium", "discount", "premium", "折价", "溢价")
    ):
        intents.append(VisualIntent.DISCOUNT_PREMIUM)
    elif has_any("spread between", "spread", "价差"):
        intents.append(VisualIntent.SPREAD)
    elif SemanticRole.ANCHOR in role_set or has_any(
        "defensible anchor", "relative to", "fair value", "锚定", "公允价值"
    ):
        intents.append(VisualIntent.VALUE_ANCHOR)
    elif SemanticRole.THRESHOLD in role_set or has_any(
        "from the threshold", "threshold distance", "距离阈值"
    ):
        intents.append(VisualIntent.THRESHOLD_DISTANCE)
    elif SemanticRole.NETWORK in role_set or has_any(
        "components connected", "topology", "network", "如何连接", "拓扑"
    ):
        intents.append(VisualIntent.NETWORK)
    elif has_any(
        "range of outcomes", "supplied interval", "uncertainty", "不确定", "区间"
    ):
        intents.append(VisualIntent.UNCERTAINTY)
    elif has_any(
        "which option",
        "larger and by how much",
        "comparison",
        "compare",
        "哪个更大",
        "比较",
    ) or ("categories" in normalized_keys and "values" in normalized_keys):
        intents.append(VisualIntent.COMPARISON)
    elif SemanticRole.SERIES in role_set or has_any(
        "over time", "trend", "趋势", "随时间"
    ):
        intents.append(VisualIntent.TREND)
    elif has_any(
        "facts that matter", "daily brief", "digest", "摘要", "简报", "汇总"
    ) or any(word in keys for word in ("digest", "items", "stories")):
        intents.append(VisualIntent.DIGEST)
    elif explicit_before_after:
        intents.append(VisualIntent.BEFORE_AFTER)
    elif has_any("current state", "right now", "当前状态", "现在状态"):
        intents.append(VisualIntent.STATE)

    # Preserve useful secondary relationships after the primary decision.
    if SemanticRole.ANCHOR in role_set:
        intents.append(VisualIntent.VALUE_ANCHOR)
    if SemanticRole.ANCHOR in role_set and SemanticRole.DELTA in role_set:
        intents.extend((VisualIntent.DISCOUNT_PREMIUM, VisualIntent.COMPARISON))
    if SemanticRole.THRESHOLD in role_set:
        intents.append(VisualIntent.THRESHOLD_DISTANCE)
    if SemanticRole.SERIES in role_set:
        intents.append(VisualIntent.TREND)
    if SemanticRole.GEO_PATH in role_set:
        intents.append(VisualIntent.DISTANCE_ROUTE)
    elif SemanticRole.GEO_POINT in role_set:
        intents.append(VisualIntent.GEO_LOCATION)
    if SemanticRole.NETWORK in role_set:
        intents.append(VisualIntent.NETWORK)
    if SemanticRole.SEQUENCE in role_set:
        intents.append(VisualIntent.TIMELINE)
    if SemanticRole.UNCERTAINTY in role_set:
        intents.append(VisualIntent.UNCERTAINTY)
    if explicit_before_after:
        intents.extend((VisualIntent.BEFORE_AFTER, VisualIntent.STATE_CHANGE))
    if any(word in keys for word in ("spread", "价差")):
        intents.append(VisualIntent.SPREAD)
    if not intents:
        intents.append(VisualIntent.STATE)
    # One visual cannot give ten relationships equal weight. Preserve the
    # primary decision and at most two useful secondary intents, matching the
    # VisualSpec contract and preventing overloaded render plans.
    return tuple(dict.fromkeys(intents))[:3]


def _meaningful_state_count(payload: Mapping[str, Any]) -> int:
    """Return the largest explicit ordered-state collection in the payload."""

    count = 0
    sequence_keys = {
        "series",
        "history",
        "frames",
        "steps",
        "events",
        "sequence",
        "trajectory",
        "path",
        "points",
    }
    for _, key, value in _flatten(payload):
        if key in sequence_keys and isinstance(value, list):
            count = max(count, len(value))
    return count


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _humanize(key: str) -> str:
    if not key:
        return "Value"
    return key.replace("_", " ").strip().title()


def _role_for_key(key: str, value: Any) -> SemanticRole:
    # Provenance/trust roles must survive overlapping names such as
    # ``confidence_interval``. Their evidence paths drive hard bundle
    # coverage checks, so a generic interval classification cannot take
    # precedence over uncertainty/source/time/unit.
    for preferred in (
        SemanticRole.SOURCE,
        SemanticRole.TIME,
        SemanticRole.UNIT,
        SemanticRole.UNCERTAINTY,
    ):
        words = next(words for role, words in _ROLE_KEYWORDS if role is preferred)
        if _matches(key, words):
            return preferred
    for role, words in _ROLE_KEYWORDS:
        if _matches(key, words):
            return role
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return SemanticRole.SCALAR
    if isinstance(value, list) and value:
        if all(
            isinstance(item, (int, float)) and not isinstance(item, bool)
            for item in value
        ) and _matches(key, ("series", "history", "trend", "points")):
            return SemanticRole.SERIES
        return SemanticRole.CATEGORY
    return SemanticRole.STATUS


def _extract_evidence(payload: Mapping[str, Any]) -> Tuple[VisualDatum, ...]:
    evidence: List[VisualDatum] = []
    global_unit = payload.get("unit")
    for path, key, value in _flatten(payload):
        if (
            key in _INTERNAL_KEYS
            or key.startswith("visual_hints")
            or path.startswith("$.visual_hints.")
        ):
            continue
        # VisualSpec is the traceability contract, not display copy. Keep the
        # complete canonical value here; text/raster adapters own any visible
        # truncation. Truncating evidence would make strict source-binding
        # verification impossible for dense arrays and networks.
        rendered = _format_value(value)
        evidence.append(
            VisualDatum(
                label=_humanize(key),
                value=rendered,
                role=_role_for_key(key, value),
                source_path=path,
                unit=_unit_for(key, value, global_unit),
            )
        )
    return tuple(evidence)


def _unit_for(key: str, value: Any, global_unit: Any) -> Optional[str]:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    tokens = set(key.split("_"))
    if {"percent", "pct", "percentage"} & tokens:
        return "%"
    known_suffixes = {
        "km": "km",
        "meter": "m",
        "meters": "m",
        "ms": "ms",
        "seconds": "s",
        "minutes": "min",
        "hours": "h",
    }
    for token, unit in known_suffixes.items():
        if token in tokens:
            return unit
    if global_unit is not None and {
        "price",
        "value",
        "amount",
        "anchor",
        "current",
        "fair",
        "bid",
        "ask",
        "spread",
        "estimate",
        "previous",
    } & tokens:
        return str(global_unit)
    return None


def _score_modalities(
    roles: Sequence[SemanticRole],
    intents: Sequence[VisualIntent],
    evidence_count: int,
    hints: Mapping[str, Any],
    state_count: int,
) -> ModalityScores:
    role_set = set(roles)
    intent_set = set(intents)
    primary_intent = intents[0]
    text, image, video = 78, 18, 0

    if evidence_count > 5:
        text -= 15
        image += 15
    if SemanticRole.ANCHOR in role_set:
        text -= 8
        image += 30
    if SemanticRole.THRESHOLD in role_set:
        text -= 8
        image += 30
    if SemanticRole.SERIES in role_set:
        text -= 15
        image += 30
        video += 20
    if SemanticRole.GEO_POINT in role_set:
        text -= 5
        image += 20
    if SemanticRole.GEO_PATH in role_set:
        text -= 20
        image += 45
        video += 35
    if SemanticRole.GEO_REGION in role_set:
        text -= 12
        image += 30
    if SemanticRole.NETWORK in role_set:
        text -= 20
        image += 50
    if SemanticRole.SEQUENCE in role_set:
        text -= 10
        image += 25
        video += 45
    if SemanticRole.UNCERTAINTY in role_set:
        text -= 8
        image += 25

    if VisualIntent.VALUE_ANCHOR in intent_set:
        image += 25
    if primary_intent is VisualIntent.THRESHOLD_DISTANCE:
        image += 30
    if primary_intent is VisualIntent.COMPARISON:
        text -= 10
        image += 55
    if primary_intent is VisualIntent.TREND:
        image += 25
    if VisualIntent.DISCOUNT_PREMIUM in intent_set:
        image += 12
    if primary_intent in (VisualIntent.DISCOUNT_PREMIUM, VisualIntent.SPREAD):
        text -= 10
        image += 55
    if primary_intent is VisualIntent.RANKING:
        text -= 10
        image += 55
    if primary_intent is VisualIntent.COMPOSITION:
        text -= 10
        image += 55
    if VisualIntent.BEFORE_AFTER in intent_set:
        image += 20
        video += 30
    if primary_intent is VisualIntent.BEFORE_AFTER:
        text -= 10
        image += 40
    if primary_intent is VisualIntent.TIMELINE:
        image += 35
    if primary_intent is VisualIntent.STATE_CHANGE:
        image += 5
        video += 80
    if primary_intent is VisualIntent.DIGEST:
        text += 10
    if primary_intent is VisualIntent.UNCERTAINTY:
        image += 35

    if bool(hints.get("motion_is_meaningful", False)) and state_count >= 3:
        video += 70
    preferred = str(hints.get("preferred_modality", "")).lower()
    if preferred in ("text", "image", "video"):
        if preferred == "text":
            text += 10
        elif preferred == "image":
            image += 10
        else:
            video += 10

    if primary_intent is VisualIntent.STATE_CHANGE:
        # Even with a secondary uncertainty/threshold role, a meaningful
        # multi-state transition must preserve the 15-point motion gate.
        image = min(image, 85)
        video = max(video, image + 15)

    clamp = lambda value: max(0, min(100, int(value)))
    return ModalityScores(clamp(text), clamp(image), clamp(video))


def _first_string(payload: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _default_question(intents: Sequence[VisualIntent]) -> str:
    intent_set = set(intents)
    choices = (
        (VisualIntent.VALUE_ANCHOR, "How far is the current value from its anchor?"),
        (VisualIntent.THRESHOLD_DISTANCE, "How close is the current value to its threshold?"),
        (VisualIntent.DISTANCE_ROUTE, "Where is the route and how does distance change?"),
        (VisualIntent.GEO_LOCATION, "Where is the reported item?"),
        (VisualIntent.TREND, "How is the value changing over time?"),
        (VisualIntent.NETWORK, "How are the reported components connected?"),
        (VisualIntent.TIMELINE, "What happened, and in what order?"),
        (VisualIntent.RANKING, "Which items lead or lag?"),
        (VisualIntent.COMPOSITION, "What makes up the reported total?"),
        (VisualIntent.UNCERTAINTY, "What range of outcomes is supported?"),
    )
    for intent, question in choices:
        if intent in intent_set:
            return question
    return "What does this output say right now?"


def inspect_payload(
    payload: Mapping[str, Any],
    *,
    primary_question: str = "",
    feature_gate: Optional[FeatureGate] = None,
) -> VisualSpec:
    """Inspect representative output and return a fully validated VisualSpec."""

    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a JSON object")
    question = (
        primary_question.strip()
        or _first_string(payload, ("primary_question", "question"))
    )
    roles = _detect_roles(payload)
    intents = _detect_intents(payload, roles, question)
    evidence = _extract_evidence(payload)
    roles = tuple(
        dict.fromkeys(
            tuple(roles) + tuple(datum.role for datum in evidence)
        )
    )
    hints_raw = payload.get("visual_hints", {})
    hints = hints_raw if isinstance(hints_raw, Mapping) else {}
    state_count = _meaningful_state_count(payload)
    scores = _score_modalities(roles, intents, len(evidence), hints, state_count)
    question = question or _default_question(intents)
    headline = _first_string(
        payload, ("headline", "title", "name", "pair", "label")
    )
    if not headline:
        headline = question.rstrip("?")
    answer = _first_string(
        payload, ("summary", "conclusion", "answer", "message", "status")
    )
    if (
        not answer
        and intents[0] is VisualIntent.STATE
        and "value" in payload
        and not isinstance(payload["value"], (Mapping, list, tuple))
    ):
        # A caller-supplied label/value state is already a factual answer. The
        # neutral template exposes it; it does not classify or reinterpret it.
        answer = _format_value(payload["value"])
    warnings: List[str] = []
    if not answer:
        warnings.append(
            "No explicit conclusion found; renderer must not infer one from raw values."
        )
    if bool(hints.get("motion_is_meaningful", False)) and state_count < 3:
        warnings.append(
            "Motion hint ignored because fewer than three meaningful states were supplied."
        )
    return make_visual_spec(
        primary_question=question,
        headline=headline,
        answer=answer,
        semantic_roles=roles,
        intents=intents,
        evidence=evidence,
        scores=scores,
        feature_gate=feature_gate,
        warnings=warnings,
    )


def _read_payload(path: str) -> Mapping[str, Any]:
    if path == "-":
        raw = json.load(sys.stdin)
    else:
        with Path(path).open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    if not isinstance(raw, Mapping):
        raise ValueError("input JSON must be an object")
    return raw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Infer a TG Watch VisualSpec from JSON output."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("input", nargs="?", help="JSON file path, or - for stdin")
    source.add_argument("--demo", action="store_true", help="inspect built-in demo")
    parser.add_argument("--question", default="", help="override primary question")
    rich = parser.add_mutually_exclusive_group()
    rich.add_argument(
        "--rich-messages",
        action="store_true",
        help="enable only after Bot API, library, and target-client verification",
    )
    rich.add_argument(
        "--no-rich-messages",
        action="store_false",
        dest="rich_messages",
        help=argparse.SUPPRESS,
    )
    parser.set_defaults(rich_messages=False)
    parser.add_argument("--no-images", action="store_true")
    parser.add_argument("--no-videos", action="store_true")
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo or args.input is None:
        payload = DEMO_PAYLOAD
    else:
        try:
            payload = _read_payload(args.input)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            parser.error(str(exc))
    gate = FeatureGate(
        rich_messages=args.rich_messages,
        images=not args.no_images,
        videos=not args.no_videos,
    )
    spec = inspect_payload(
        payload, primary_question=args.question, feature_gate=gate
    )
    json.dump(
        spec.to_dict(),
        sys.stdout,
        ensure_ascii=False,
        indent=None if args.compact else 2,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
