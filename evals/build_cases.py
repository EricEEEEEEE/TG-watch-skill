#!/usr/bin/env python3
"""Build the deterministic 85-case TG visual compiler evaluation corpus."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


FAMILIES = [
    {
        "intent": "state",
        "primary_question": "What is the current state?",
        "roles": ["category", "status", "time"],
        "expected_medium": "text",
        "expected_grammar": "verdict-key-values",
        "sample": {"label": "API availability", "value": "healthy", "time": "09:30", "source": "probe"},
    },
    {
        "intent": "digest",
        "primary_question": "What are the few facts that matter?",
        "roles": ["category"],
        "expected_medium": "text",
        "expected_grammar": "html-digest",
        "sample": {"title": "Daily brief", "items": ["Fact A", "Fact B", "Fact C"], "source": "three feeds"},
    },
    {
        "intent": "threshold_distance",
        "primary_question": "How far is the current value from the threshold?",
        "roles": ["category", "scalar", "threshold", "unit"],
        "expected_medium": "image",
        "expected_grammar": "threshold-bullet",
        "sample": {"label": "Utilization", "value": 73, "threshold": 85, "unit": "%", "source": "metrics API"},
    },
    {
        "intent": "value_anchor",
        "primary_question": "Where is the current value relative to its defensible anchor?",
        "roles": ["anchor", "category", "interval", "scalar", "unit"],
        "expected_medium": "image",
        "expected_grammar": "value-band",
        "sample": {
            "label": "Asset / anchor",
            "value": 96.4,
            "anchor": 100,
            "interval": [98, 102],
            "unit": "USD",
            "source": "anchor fixture",
        },
    },
    {
        "intent": "discount_premium",
        "primary_question": "What is the discount or premium to the stated anchor?",
        "roles": ["anchor", "category", "delta", "scalar", "unit"],
        "expected_medium": "image",
        "expected_grammar": "value-band",
        "sample": {
            "label": "Asset discount",
            "current_price": 96.4,
            "fair_anchor_price": 100,
            "discount_percent": 3.6,
            "unit": "USD",
            "source": "example feed",
        },
    },
    {
        "intent": "spread",
        "primary_question": "How large is the spread between the two supplied values?",
        "roles": ["category", "delta", "scalar", "unit"],
        "expected_medium": "image",
        "expected_grammar": "value-band",
        "sample": {
            "label": "Bid / ask spread",
            "bid": 99.2,
            "ask": 100.1,
            "spread": 0.9,
            "unit": "USD",
            "source": "example venue",
        },
    },
    {
        "intent": "comparison",
        "primary_question": "Which option is larger and by how much?",
        "roles": ["category", "scalar", "unit"],
        "expected_medium": "image",
        "expected_grammar": "aligned-bars",
        "sample": {
            "label": "Latency",
            "categories": ["A", "B", "C"],
            "values": [120, 84, 166],
            "unit": "ms",
            "source": "comparison fixture",
        },
    },
    {
        "intent": "ranking",
        "primary_question": "What are the top items?",
        "roles": ["category", "scalar", "unit"],
        "expected_medium": "image",
        "expected_grammar": "ranked-bars",
        "sample": {
            "label": "Top movers",
            "categories": ["A", "B", "C", "D", "E"],
            "values": [9, 7, 5, 3, 1],
            "unit": "%",
            "source": "ranking fixture",
        },
    },
    {
        "intent": "trend",
        "primary_question": "How has the value changed over time?",
        "roles": ["category", "scalar", "series", "unit"],
        "expected_medium": "image",
        "expected_grammar": "annotated-line",
        "sample": {
            "label": "Requests",
            "series": [12, 18, 15, 29, 31, 27, 34],
            "unit": "k",
            "source": "timeseries fixture",
        },
    },
    {
        "intent": "composition",
        "primary_question": "What makes up the total?",
        "roles": ["category", "scalar", "unit"],
        "expected_medium": "image",
        "expected_grammar": "stacked-composition",
        "sample": {
            "label": "Portfolio mix",
            "categories": ["Core", "Cash", "Other"],
            "values": [62, 23, 15],
            "unit": "%",
            "source": "composition fixture",
        },
    },
    {
        "intent": "network",
        "primary_question": "How are the supplied components connected?",
        "roles": ["category", "network"],
        "expected_medium": "image",
        "expected_grammar": "node-link",
        "sample": {
            "label": "Pipeline topology",
            "nodes": ["Collector", "Processor", "Telegram", "Archive"],
            "edges": [
                ["Collector", "Processor"],
                ["Processor", "Telegram"],
                ["Processor", "Archive"],
            ],
            "source": "runtime graph",
        },
    },
    {
        "intent": "before_after",
        "primary_question": "What changed between the supplied before and after states?",
        "roles": ["category", "scalar", "unit"],
        "expected_medium": "image",
        "expected_grammar": "aligned-bars",
        "sample": {
            "label": "Before / after",
            "categories": ["Latency", "Errors", "Throughput"],
            "previous_values": [120, 18, 80],
            "current_values": [84, 9, 116],
            "unit": "index",
            "source": "comparison fixture",
        },
    },
    {
        "intent": "uncertainty",
        "primary_question": "What range of outcomes is supported by the supplied interval?",
        "roles": ["category", "interval", "scalar", "uncertainty", "unit"],
        "expected_medium": "image",
        "expected_grammar": "range-band",
        "sample": {
            "label": "Latency estimate",
            "estimate": 50,
            "confidence_interval": [44, 58],
            "unit": "ms",
            "source": "model output",
        },
    },
    {
        "intent": "geo_location",
        "primary_question": "Where is the event?",
        "roles": ["category", "geo_point", "scalar"],
        "expected_medium": "text",
        "expected_grammar": "native-location",
        "sample": {"label": "Event point", "latitude": 1.3521, "longitude": 103.8198, "source": "sensor"},
    },
    {
        "intent": "distance_route",
        "primary_question": "How are the origin, destination, and affected area related?",
        "roles": ["category", "geo_path", "scalar", "unit"],
        "expected_medium": "image",
        "expected_grammar": "route-map",
        "sample": {
            "label": "Route",
            "origin": [1.29, 103.85],
            "destination": [1.36, 103.99],
            "distance": 18.4,
            "unit": "km",
            "source": "route fixture",
        },
    },
    {
        "intent": "timeline",
        "primary_question": "What happened, and in what order?",
        "roles": ["category", "sequence"],
        "expected_medium": "image",
        "expected_grammar": "event-timeline",
        "sample": {
            "label": "Incident timeline",
            "events": [
                ["09:10", "Detected"],
                ["09:18", "Confirmed"],
                ["09:31", "Recovered"],
            ],
            "source": "incident fixture",
        },
    },
    {
        "intent": "state_change",
        "primary_question": "How did the state evolve?",
        "roles": ["category", "scalar", "series", "threshold", "unit"],
        "expected_medium": "video",
        "expected_grammar": "sequence-replay",
        "sample": {
            "label": "Threshold crossing",
            "series": [40, 48, 61, 79, 91],
            "threshold": 80,
            "unit": "%",
            "source": "state fixture",
        },
    },
]

VARIANTS = [
    ("basic", {}),
    (
        "cjk_long",
        {
            "locale": "zh-CN",
            "title_suffix": "——这是一个用于验证中文长标题自动换行、数字宽度和移动端可读性的案例",
        },
    ),
    ("missing_optional", {"drop_optional": True}),
    ("extreme", {"extreme_values": True}),
    ("composite", {"secondary_intent": "uncertainty", "uncertainty": "interval"}),
]


def apply_extreme_values(intent: str, sample: dict) -> None:
    """Stress fields that actually carry the family's visual relationship."""

    if intent == "state":
        sample["value"] = "unknown / degraded / recovering / awaiting confirmation"
    elif intent == "digest":
        sample["items"] = [
            f"Fact {index}: representative long evidence item {index * 999_999:,}"
            for index in range(1, 13)
        ]
    elif intent == "threshold_distance":
        sample["value"] = 9_999_999_999.999
        sample["threshold"] = 0.000001
    elif intent == "value_anchor":
        sample["value"] = -12_345.67
        sample["anchor"] = 0.000001
        sample["interval"] = [-999_999.5, 9_999_999_999.999]
    elif intent == "discount_premium":
        sample["current_price"] = -12_345.67
        sample["fair_anchor_price"] = 0.000001
        sample["discount_percent"] = 9_999_999_999.999
    elif intent == "spread":
        sample["bid"] = -12_345.67
        sample["ask"] = 9_999_999_999.999
        sample["spread"] = 10_000_012_345.669
    elif intent in ("comparison", "ranking"):
        sample["values"] = [9_999_999_999.999, 0.000001, -12_345.67]
        sample["categories"] = ["Very large", "Very small", "Negative"]
    elif intent == "trend":
        sample["series"] = [0.000001, 999_999.0, -12_345.67, 9_999_999_999.999]
    elif intent == "composition":
        sample["values"] = [0.000001, 9_999_999_999.999, 1]
    elif intent == "network":
        sample["nodes"] = [f"Node {index} with a long label" for index in range(12)]
        sample["edges"] = [
            [sample["nodes"][left], sample["nodes"][right]]
            for left in range(12)
            for right in range(left + 1, min(12, left + 4))
        ]
    elif intent == "before_after":
        sample["previous_values"] = [-12_345.67, 0.000001, 9_999_999_999.999]
        sample["current_values"] = [9_999_999_999.999, -12_345.67, 0.000001]
    elif intent == "uncertainty":
        sample["estimate"] = -12_345.67
        sample["confidence_interval"] = [-999_999.5, 9_999_999_999.999]
    elif intent == "geo_location":
        sample["latitude"] = 89.9999
        sample["longitude"] = -179.9999
    elif intent == "distance_route":
        sample["origin"] = [89.9, 179.9]
        sample["destination"] = [-89.9, -179.9]
        sample["distance"] = 20_003.93
    elif intent == "timeline":
        sample["events"] = [
            [f"{index:02d}:59:59.999", f"Stage {index} with long evidence"]
            for index in range(12)
        ]
    elif intent == "state_change":
        sample["series"] = [-12_345.67, 0.000001, 79.999, 9_999_999_999.999]
        sample["threshold"] = 80


def add_uncertainty(sample: dict) -> None:
    """Add uncertainty to an existing measurement, not as an unrelated fixture."""

    numeric = [
        value
        for value in sample.values()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    if numeric:
        center = numeric[0]
        spread = max(abs(center) * 0.05, 0.000001)
        sample["confidence_interval"] = [center - spread, center + spread]
    else:
        sample["confidence"] = "medium"


def build_cases() -> list[dict]:
    cases: list[dict] = []
    for family in FAMILIES:
        for variant_name, mutation in VARIANTS:
            case = deepcopy(family)
            case_id = f"{family['intent']}-{variant_name}"
            case["id"] = case_id
            case["variant"] = variant_name
            case["locale"] = mutation.get("locale", "en")
            case["uncertainty"] = mutation.get("uncertainty", "none")
            if suffix := mutation.get("title_suffix"):
                case["sample"]["label"] = f"{case['sample'].get('label', family['intent'])}{suffix}"
            if mutation.get("drop_optional"):
                case["sample"].pop("source", None)
            if mutation.get("extreme_values"):
                apply_extreme_values(family["intent"], case["sample"])
            if secondary := mutation.get("secondary_intent"):
                case["secondary_intents"] = [secondary]
                add_uncertainty(case["sample"])
            cases.append(case)
    return cases


def main() -> None:
    out = Path(__file__).with_name("cases.json")
    payload = {
        "version": 1,
        "description": "17 visual intents × 5 robustness variants",
        "case_count": 85,
        "cases": build_cases(),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
