# Visual decision engine

Use this decision engine to turn an arbitrary script and representative output into a
`VisualSpec`. Decide how to show information; do not change how the script obtains,
classifies, schedules, routes, retries, deduplicates, or acts on that information.

## Contents

- Required inputs and output contract
- Medium compilation: text adapter versus VisualSpec-to-RenderSpec
- Decision sequence and candidate scoring
- Information hierarchy and fallbacks
- Stop conditions and scope boundary

## Required inputs

Inspect all available evidence before choosing a medium:

- the script and its existing output path
- one normal sample and, when available, an empty, extreme, and long-text sample
- the fields, units, timestamps, sources, uncertainty, and relationships already present
- the target language and Telegram client assumptions
- existing fonts, renderers, and visual conventions in the repository

Do not infer missing thresholds, anchors, severity, causality, recommendations, or facts.

## Output contract

Produce one semantic and medium-decision `VisualSpec` before rendering:

```json
{
  "schema_version": "1.0",
  "primary_question": "How far is current value from its stated anchor?",
  "headline": "Current versus stated anchor",
  "answer": "Current is below anchor",
  "semantic_roles": ["scalar", "anchor", "unit", "time", "source"],
  "intents": ["value_anchor"],
  "evidence": [
    {
      "label": "Current",
      "value": "3210",
      "unit": "USD",
      "role": "scalar",
      "source_path": "$.current_price"
    },
    {
      "label": "Anchor",
      "value": "3261",
      "unit": "USD",
      "role": "anchor",
      "source_path": "$.fair_anchor_price"
    },
    {
      "label": "Unit",
      "value": "USD",
      "role": "unit",
      "source_path": "$.currency"
    },
    {
      "label": "Observed",
      "value": "2026-07-23T15:41:00+08:00",
      "role": "time",
      "source_path": "$.timestamp"
    },
    {
      "label": "Source",
      "value": "caller-supplied source",
      "role": "source",
      "source_path": "$.source"
    }
  ],
  "scores": {
    "text": 62,
    "image": 91,
    "video": 28
  },
  "selected_modality": "image",
  "fallback_chain": ["image", "text"],
  "selection_reason": "The answer depends on a shared quantitative scale.",
  "grammar": "value-band",
  "feature_gate": {
    "rich_messages": false,
    "images": true,
    "videos": true
  },
  "warnings": []
}
```

Keep `primary_question` singular. If the output asks several independent questions, create
an overview plus detail frames rather than one overloaded card.

Every evidence item must have a non-empty `source_path` pointing to the original payload.
Field names and numerical resemblance are not provenance.

## Compile by medium

Treat compilation as an explicit AI/agent step:

```text
source payload → VisualSpec (semantics, modality, grammar, evidence provenance)
  ├─ text → text compiler/adapter → Rich Message + HTML fallback
  └─ image/video → RenderSpec → deterministic renderer → artifact
```

The text compiler/adapter consumes `VisualSpec` directly and preserves each evidence
`source_path`; text does not use `RenderSpec`.

For image/video, never pass `VisualSpec` directly to a pixel/frame renderer and never let a
renderer infer missing numbers or choose a visual grammar. The following is an abridged
binding diagram; a real bundle must include the full validated `VisualSpec`. Compile:

```json
{
  "visual_spec": {"schema_version": "1.0"},
  "render_spec": {
    "version": "1.0",
    "kind": "anchor",
    "title": "Current versus stated anchor",
    "subtitle": "",
    "theme": "light",
    "width": 1200,
    "data": {
      "current": 3210,
      "anchors": [
        {"label": "Stated anchor", "value": 3261, "primary": true}
      ],
      "unit": "USD",
      "delta_pct": "-1.563937442502299908003679853"
    },
    "meta": {
      "timestamp": "2026-07-23T15:41:00+08:00",
      "source": "caller-supplied source"
    },
    "source_bindings": {
      "title": {
        "inputs": ["$.label"],
        "operation": "copy",
        "verified_result": "Current versus stated anchor"
      },
      "data.current": {"jsonpath": "$.current_price"},
      "data.anchors[0].value": {"jsonpath": "$.fair_anchor_price"},
      "data.unit": {"jsonpath": "$.currency"},
      "meta.timestamp": {"jsonpath": "$.timestamp"},
      "meta.source": {"jsonpath": "$.source"},
      "data.delta_pct": {
        "inputs": ["$.current_price", "$.fair_anchor_price"],
        "operation": "percent_delta",
        "verified_result": "-1.563937442502299908003679853"
      }
    }
  }
}
```

Bind every dynamic displayed title, value, label, unit, timestamp, source, series,
coordinate, and state through `source_bindings`. Bind `title` and `subtitle` to original
evidence through the registered `copy` operation; a `VisualSpec.headline` or
`VisualSpec.answer` string is not independently source-traceable. For a direct field, use
`{"jsonpath": "<original evidence source_path>"}` or
`{"source_path": "<original evidence source_path>"}`. Static renderer vocabulary such as
`Current` or `Source` may be a tested locale token. A derived field must declare all input
paths, a registered executable `operation`, and its exact `verified_result`; validation
recomputes it. Free-form formulas are rejected. Compilation may format or deterministically
derive display values; it may not guess, interpolate, select, or synthesize factual numbers.

A standalone image/video `RenderSpec` may omit bindings only for a local fixture or legacy
exploration. Treat it as untraceable and block it from high-risk or production acceptance
until bundled bindings are complete.

## Decision sequence

### 1. State the user's visual question

Rewrite the output as one question that can be answered in three seconds:

- What is the current state?
- What changed, and by how much?
- Which item is highest or lowest?
- How far is a value from a target, anchor, or boundary?
- Where is it, how far away, or along which route?
- What happened first, next, and last?
- How uncertain is the estimate?

If no single question survives, separate the content.

### 2. Extract semantic roles

Map fields to the vocabulary in `semantic-roles.md`. Use field names only as evidence;
confirm roles from values, labels, and surrounding code. For example, `target` may mean a
display target, a geographic destination, or a business target.

### 3. Identify the dominant relationship

Choose one primary `VisualIntent`:

| Relationship | VisualIntent | Default encoding |
| --- | --- | --- |
| one value or state | `state` | hero value or concise text |
| old versus new | `state_change` | delta pair or slope |
| items on one scale | `comparison` | dot plot or aligned bars |
| ordered items | `ranking` | sorted bars |
| values over time | `trend` | line plus event markers |
| parts of a whole | `composition` | stacked bar |
| value versus boundary | `threshold_distance` | bullet chart |
| value versus fair/reference value | `value_anchor` | shared-axis ruler |
| price/value gap | `discount_premium` | ruler plus signed delta |
| distance between two supplied values | `spread` | common-axis difference |
| uncertain estimate | `uncertainty` | interval or fan band |
| time-ordered events | `timeline` | horizontal/vertical timeline |
| point or supplied region | `geo_location` | native map or point/region map |
| path, route, or geographic distance | `distance_route` | route map |
| entities and links | `network` | topology or adjacency matrix |
| supplied initial and final states | `before_after` | aligned comparison or motion |
| many independent summaries | `digest` | grouped text or small multiples |

Add at most two secondary intents. The primary intent owns the largest visual area.

### 4. Choose the lightest sufficient medium

Use the following gates in order.

#### Use regular text when all are true

- the answer is expressible in one sentence
- there are at most five important facts
- no spatial geometry, time series, topology, or quantitative scale is required
- there are no more than two items to compare
- precise placement does not improve comprehension

#### Use rich text when

- the content is a structured report, table, formula, nested explanation, or evidence list
- native headings, tables, details, quotes, maps, collage, or slideshow can express it
- the Telegram Bot API and deployed library support the required Rich Message features

Do not burn a long report into a PNG merely to make it look designed.

#### Use an image when any are true

- values must share an axis, baseline, threshold, or anchor
- three or more items must be compared
- trend, distribution, composition, uncertainty, geography, topology, or a timeline matters
- a stable screenshot-like visual must be readable without opening another interface
- exact hierarchy and annotation matter more than native reflow

#### Use motion only when all are true

- change, order, movement, accumulation, or transition is itself the evidence
- there are at least three meaningful states
- a static overview plus small multiples would materially hide the pattern
- the first frame, silent playback, final frame, and static fallback all remain meaningful

Require the motion candidate to beat the best static candidate by at least 15 points. Never
use animation merely to attract attention.

#### Use a hybrid when

An image or video needs a short native-text conclusion, context, source, or accessible
summary. The caption must complement the media, not transcribe every visible label.

### 5. Score candidates

Score each candidate from 0–100:

| Dimension | Weight | Question |
| --- | ---: | --- |
| semantic fit | 30 | Does the encoding directly express the dominant relationship? |
| three-second comprehension | 20 | Is the primary answer obvious on a phone? |
| evidence capacity | 15 | Can it show the necessary evidence without crowding? |
| data integrity | 15 | Does it preserve scale, units, uncertainty, and provenance? |
| accessibility | 10 | Does it work with CJK, color-vision differences, and silent use? |
| production reliability | 10 | Can it render deterministically and degrade safely? |

Choose the highest score after applying the medium gates. Record the score and reason so a
reviewer can challenge the decision.

## Information hierarchy

Use the same hierarchy for every medium:

1. **Answer** — subject, state, primary value, or conclusion already present in input.
2. **Evidence** — the comparison, series, range, route, or event that supports the answer.
3. **Provenance** — timestamp, units, source, method, uncertainty, and missing-data notes.

Use one hero metric. Use no more than two supporting modules in one static card. Split the
rest into a detail frame or native details block.

## Fallback order

Define fallbacks before rendering:

```text
Rich Message → regular HTML text
motion/video → poster image → regular text
rendered map → native location/map block → coordinates in text
chart/card → structured text table → explicit missing-visual note
```

Never replace unavailable evidence with invented content.

## Stop conditions

Stop and request/emit a text-safe fallback when:

- the primary question cannot be identified
- a necessary relationship is ambiguous
- required values have incompatible or unlabeled units
- the only available data is stale or missing and the script does not label that state
- the proposed visualization would imply a judgment not made by the script

## Out of scope

Do not design cron schedules, alert rules, routing, topics, recipients, acknowledgements,
cooldowns, retries, deduplication, data acquisition, trading actions, or business decisions.
Existing labels such as severity or action may be displayed, but this skill never creates or
changes them.
