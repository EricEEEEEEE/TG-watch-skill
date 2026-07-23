#!/usr/bin/env python3
"""Validated intermediate representation for TG Watch visual decisions.

The module is deliberately renderer-neutral and standard-library only.  It
turns semantic roles and media scores into a deterministic delivery decision
that every renderer can consume.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple


class SemanticRole(str, Enum):
    """Domain-independent roles that values play in a visual explanation."""

    SCALAR = "scalar"
    DELTA = "delta"
    ANCHOR = "anchor"
    THRESHOLD = "threshold"
    INTERVAL = "interval"
    SERIES = "series"
    CATEGORY = "category"
    GEO_POINT = "geo_point"
    GEO_PATH = "geo_path"
    GEO_REGION = "geo_region"
    NETWORK = "network"
    SEQUENCE = "sequence"
    UNCERTAINTY = "uncertainty"
    STATUS = "status"
    SOURCE = "source"
    TIME = "time"
    UNIT = "unit"


class VisualIntent(str, Enum):
    """Questions a visual can answer, independent of business domain."""

    STATE = "state"
    STATE_CHANGE = "state_change"
    COMPARISON = "comparison"
    RANKING = "ranking"
    TREND = "trend"
    COMPOSITION = "composition"
    THRESHOLD_DISTANCE = "threshold_distance"
    VALUE_ANCHOR = "value_anchor"
    DISCOUNT_PREMIUM = "discount_premium"
    SPREAD = "spread"
    TIMELINE = "timeline"
    GEO_LOCATION = "geo_location"
    DISTANCE_ROUTE = "distance_route"
    NETWORK = "network"
    BEFORE_AFTER = "before_after"
    UNCERTAINTY = "uncertainty"
    DIGEST = "digest"


class Modality(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"


@dataclass(frozen=True)
class FeatureGate:
    """Telegram/client capabilities available to the adapter."""

    # Rich Messages are new enough that framework/client support must be
    # verified explicitly. Basic image/video carriers are long-established.
    rich_messages: bool = False
    images: bool = True
    videos: bool = True
    max_rich_text_chars: int = 32768
    max_html_chars: int = 4096

    def __post_init__(self) -> None:
        for name, value, ceiling in (
            ("max_rich_text_chars", self.max_rich_text_chars, 32768),
            ("max_html_chars", self.max_html_chars, 4096),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError("%s must be an integer" % name)
            if value <= 0:
                raise ValueError("%s must be positive" % name)
            if value > ceiling:
                raise ValueError("%s exceeds Telegram's supported ceiling" % name)

    def supports(self, modality: Modality) -> bool:
        if modality is Modality.IMAGE:
            return self.images
        if modality is Modality.VIDEO:
            return self.videos
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rich_messages": self.rich_messages,
            "images": self.images,
            "videos": self.videos,
            "max_rich_text_chars": self.max_rich_text_chars,
            "max_html_chars": self.max_html_chars,
        }

    @classmethod
    def from_dict(cls, raw: Optional[Mapping[str, Any]]) -> "FeatureGate":
        if raw is None:
            return cls()
        for key in ("rich_messages", "images", "videos"):
            if key in raw and not isinstance(raw[key], bool):
                raise TypeError("%s feature gate must be a boolean" % key)
        return cls(
            rich_messages=raw.get("rich_messages", False),
            images=raw.get("images", True),
            videos=raw.get("videos", True),
            max_rich_text_chars=raw.get("max_rich_text_chars", 32768),
            max_html_chars=raw.get("max_html_chars", 4096),
        )


@dataclass(frozen=True)
class ModalityScores:
    """Comparable 0–100 usefulness scores for each delivery medium."""

    text: int
    image: int
    video: int

    def __post_init__(self) -> None:
        for name, value in self.to_dict().items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError("%s score must be an integer" % name)
            if not 0 <= value <= 100:
                raise ValueError("%s score must be between 0 and 100" % name)

    def for_modality(self, modality: Modality) -> int:
        return int(getattr(self, modality.value))

    def to_dict(self) -> Dict[str, int]:
        return {"text": self.text, "image": self.image, "video": self.video}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ModalityScores":
        return cls(
            text=raw["text"],
            image=raw["image"],
            video=raw["video"],
        )


@dataclass(frozen=True)
class VisualDatum:
    """One traceable item that may be shown as visual evidence."""

    label: str
    value: str
    role: SemanticRole
    source_path: str
    unit: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("datum label must not be empty")
        if not self.source_path.strip():
            raise ValueError("datum source_path must not be empty")
        if self.source_path != "$" and not self.source_path.startswith("$."):
            raise ValueError("datum source_path must be an original-payload JSONPath")

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "label": self.label,
            "value": self.value,
            "role": self.role.value,
            "source_path": self.source_path,
        }
        if self.unit:
            result["unit"] = self.unit
        return result

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "VisualDatum":
        return cls(
            label=str(raw["label"]),
            value=str(raw.get("value", "")),
            role=SemanticRole(str(raw["role"])),
            source_path=str(raw["source_path"]),
            unit=str(raw["unit"]) if raw.get("unit") is not None else None,
        )


def _unique(values: Iterable[Any]) -> Tuple[Any, ...]:
    result = []
    seen = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return tuple(result)


def select_modality(
    scores: ModalityScores, feature_gate: Optional[FeatureGate] = None
) -> Tuple[Modality, Tuple[Modality, ...], str]:
    """Select a medium and deterministic fallback chain.

    Video has an intentionally high burden of proof: it is selected only when
    available and at least 15 points more useful than the best static
    alternative (text or image). This prevents decorative motion.
    """

    gate = feature_gate or FeatureGate()
    best_supported_static = scores.text
    if gate.images:
        best_supported_static = max(best_supported_static, scores.image)
    video_eligible = (
        gate.videos
        and scores.video >= best_supported_static + 15
    )
    if video_eligible:
        selected = Modality.VIDEO
        reason = (
            "video adds temporal meaning and beats the best static medium "
            "by at least 15 points"
        )
    elif gate.images and scores.image > scores.text:
        selected = Modality.IMAGE
        reason = "image communicates the relationships more efficiently than text"
    else:
        selected = Modality.TEXT
        reason = "text is the clearest supported medium for this payload"

    if selected is Modality.VIDEO:
        fallback = [Modality.VIDEO]
        if gate.images:
            fallback.append(Modality.IMAGE)
        fallback.append(Modality.TEXT)
    elif selected is Modality.IMAGE:
        fallback = [Modality.IMAGE, Modality.TEXT]
    else:
        fallback = [Modality.TEXT]
    return selected, tuple(fallback), reason


def grammar_for(
    selected: Modality, intents: Sequence[VisualIntent], rich_messages: bool = True
) -> str:
    """Choose the first applicable visual grammar in priority order."""

    primary = intents[0] if intents else VisualIntent.STATE
    if selected is Modality.TEXT:
        if primary is VisualIntent.GEO_LOCATION:
            return "native-location"
        if primary is VisualIntent.DIGEST:
            return "rich-digest" if rich_messages else "html-digest"
        return "verdict-key-values"
    if selected is Modality.VIDEO:
        return "sequence-replay"

    image_grammars = {
        VisualIntent.VALUE_ANCHOR: "value-band",
        VisualIntent.DISCOUNT_PREMIUM: "value-band",
        VisualIntent.SPREAD: "value-band",
        VisualIntent.THRESHOLD_DISTANCE: "threshold-bullet",
        VisualIntent.DISTANCE_ROUTE: "route-map",
        VisualIntent.GEO_LOCATION: "point-map",
        VisualIntent.NETWORK: "node-link",
        VisualIntent.STATE_CHANGE: "annotated-line",
        VisualIntent.TREND: "annotated-line",
        VisualIntent.RANKING: "ranked-bars",
        VisualIntent.COMPOSITION: "stacked-composition",
        VisualIntent.UNCERTAINTY: "range-band",
        VisualIntent.BEFORE_AFTER: "aligned-bars",
        VisualIntent.TIMELINE: "event-timeline",
        VisualIntent.COMPARISON: "aligned-bars",
        VisualIntent.STATE: "hero-card",
    }
    if primary in image_grammars:
        return image_grammars[primary]
    for intent in intents[1:]:
        if intent in image_grammars:
            return image_grammars[intent]
    return "hero-evidence-source"


@dataclass(frozen=True)
class VisualSpec:
    """Stable, validated contract between semantic inspection and rendering."""

    primary_question: str
    headline: str
    answer: str
    semantic_roles: Tuple[SemanticRole, ...]
    intents: Tuple[VisualIntent, ...]
    evidence: Tuple[VisualDatum, ...]
    scores: ModalityScores
    selected_modality: Modality
    fallback_chain: Tuple[Modality, ...]
    selection_reason: str
    grammar: str
    feature_gate: FeatureGate
    warnings: Tuple[str, ...] = ()
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        self.validate()

    @property
    def delivery_format(self) -> str:
        if self.selected_modality is Modality.IMAGE:
            return "photo"
        if self.selected_modality is Modality.VIDEO:
            return "video"
        return "rich_message" if self.feature_gate.rich_messages else "html"

    def validate(self) -> None:
        if self.schema_version != "1.0":
            raise ValueError("unsupported VisualSpec schema_version")
        if not self.primary_question.strip():
            raise ValueError("primary_question must not be empty")
        if not self.headline.strip():
            raise ValueError("headline must not be empty")
        if not self.semantic_roles:
            raise ValueError("at least one semantic role is required")
        if not self.intents:
            raise ValueError("at least one visual intent is required")
        if len(self.intents) > 3:
            raise ValueError(
                "VisualSpec supports one primary and at most two secondary intents"
            )
        if len(set(self.semantic_roles)) != len(self.semantic_roles):
            raise ValueError("semantic_roles must be unique")
        if len(set(self.intents)) != len(self.intents):
            raise ValueError("intents must be unique")
        evidence_paths = [datum.source_path for datum in self.evidence]
        if len(set(evidence_paths)) != len(evidence_paths):
            raise ValueError("evidence source_path values must be unique")
        undeclared_roles = {
            datum.role for datum in self.evidence
        } - set(self.semantic_roles)
        if undeclared_roles:
            raise ValueError(
                "evidence roles must be declared in semantic_roles: "
                + ", ".join(sorted(role.value for role in undeclared_roles))
            )
        expected, expected_fallback, _ = select_modality(
            self.scores, self.feature_gate
        )
        if self.selected_modality is not expected:
            raise ValueError("selected_modality does not match scores and feature gates")
        if self.fallback_chain != expected_fallback:
            raise ValueError("fallback_chain does not match selected modality")
        if not self.feature_gate.supports(self.selected_modality):
            raise ValueError("selected modality is not supported by feature gate")
        if self.selected_modality is Modality.VIDEO:
            best_supported_static = self.scores.text
            if self.feature_gate.images:
                best_supported_static = max(
                    best_supported_static, self.scores.image
                )
            if self.scores.video < best_supported_static + 15:
                raise ValueError(
                    "video must beat the best supported static medium "
                    "by at least 15 points"
                )
        expected_grammar = grammar_for(
            self.selected_modality, self.intents, self.feature_gate.rich_messages
        )
        if self.grammar != expected_grammar:
            raise ValueError(
                "grammar does not match selected modality and primary intent"
            )
        if not self.selection_reason.strip():
            raise ValueError("selection_reason must not be empty")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "primary_question": self.primary_question,
            "headline": self.headline,
            "answer": self.answer,
            "semantic_roles": [role.value for role in self.semantic_roles],
            "intents": [intent.value for intent in self.intents],
            "evidence": [datum.to_dict() for datum in self.evidence],
            "scores": self.scores.to_dict(),
            "selected_modality": self.selected_modality.value,
            "delivery_format": self.delivery_format,
            "fallback_chain": [item.value for item in self.fallback_chain],
            "selection_reason": self.selection_reason,
            "grammar": self.grammar,
            "feature_gate": self.feature_gate.to_dict(),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "VisualSpec":
        gate = FeatureGate.from_dict(raw.get("feature_gate"))
        scores = ModalityScores.from_dict(raw["scores"])
        selected = Modality(str(raw["selected_modality"]))
        fallback_raw = raw.get("fallback_chain")
        if fallback_raw is None:
            _, fallback, _ = select_modality(scores, gate)
        else:
            fallback = tuple(Modality(str(value)) for value in fallback_raw)
        return cls(
            schema_version=str(raw.get("schema_version", "1.0")),
            primary_question=str(raw["primary_question"]),
            headline=str(raw["headline"]),
            answer=str(raw.get("answer", "")),
            semantic_roles=tuple(
                SemanticRole(str(value)) for value in raw["semantic_roles"]
            ),
            intents=tuple(VisualIntent(str(value)) for value in raw["intents"]),
            evidence=tuple(
                VisualDatum.from_dict(value) for value in raw.get("evidence", ())
            ),
            scores=scores,
            selected_modality=selected,
            fallback_chain=fallback,
            selection_reason=str(raw.get("selection_reason", "")),
            grammar=str(raw["grammar"]),
            feature_gate=gate,
            warnings=tuple(str(value) for value in raw.get("warnings", ())),
        )


def make_visual_spec(
    *,
    primary_question: str,
    headline: str,
    answer: str,
    semantic_roles: Sequence[SemanticRole],
    intents: Sequence[VisualIntent],
    evidence: Sequence[VisualDatum],
    scores: ModalityScores,
    feature_gate: Optional[FeatureGate] = None,
    warnings: Sequence[str] = (),
) -> VisualSpec:
    """Construct a VisualSpec without allowing inconsistent decision fields."""

    gate = feature_gate or FeatureGate()
    unique_roles = _unique(semantic_roles)
    unique_intents = _unique(intents)
    selected, fallback, reason = select_modality(scores, gate)
    grammar = grammar_for(selected, unique_intents, gate.rich_messages)
    normalized_warnings = list(warnings)
    if not gate.rich_messages:
        normalized_warnings.append(
            "Rich Messages unavailable; use escaped Telegram HTML fallback."
        )
    if not gate.images:
        normalized_warnings.append("Image delivery unavailable.")
    if not gate.videos:
        normalized_warnings.append("Video delivery unavailable.")
    return VisualSpec(
        primary_question=primary_question,
        headline=headline,
        answer=answer,
        semantic_roles=unique_roles,
        intents=unique_intents,
        evidence=tuple(evidence),
        scores=scores,
        selected_modality=selected,
        fallback_chain=fallback,
        selection_reason=reason,
        grammar=grammar,
        feature_gate=gate,
        warnings=_unique(normalized_warnings),
    )
