# Semantic roles and VisualIntent

Normalize arbitrary script output into visual roles before selecting a chart or layout.
Roles describe how a value participates in a visual relationship, not its business domain.

## Contents

- Atomic roles and relationship signatures
- Allowed presentation transforms
- Missingness, VisualSpec evidence, and role-resolution checks

## Atomic roles

Use only these canonical values in `VisualSpec.semantic_roles` and
`VisualSpec.evidence[].role`:

| Role | Meaning | Examples |
| --- | --- | --- |
| `scalar` | one observed/current/previous numeric value | 98.2%, `$3,210` |
| `delta` | signed absolute or percentage difference | `-51 USD`, `-1.56%` |
| `anchor` | supplied reference or fair value | NAV, oracle, target |
| `threshold` | supplied decision boundary | limit, SLO, trigger line |
| `interval` | range endpoints or bounded window | confidence/expected range |
| `series` | ordered comparable observations | hourly latency samples |
| `category` | discrete grouping or item identity | region, class, ranked item |
| `geo_point` | latitude/longitude or known place | station, incident |
| `geo_path` | ordered coordinates or supplied route | vehicle track |
| `geo_region` | polygon, radius, bounding box | affected area |
| `network` | nodes and edges as one relationship set | dependency graph |
| `sequence` | ordered events, steps, or frames | timeline, process |
| `uncertainty` | confidence, error, quality, or missingness | p10–p90 |
| `status` | caller-supplied discrete state | online, delayed, P1 |
| `source` | evidence origin or supplied method | API, venue, TWAP |
| `time` | observation, event, or generation time | ISO 8601 time |
| `unit` | measurement unit | ms, km, USD |

Treat a label like `P1`, `high`, `safe`, or `cheap` as display data only when it already
exists in the script output. Never derive it from colors or thresholds.

Use labels and context to retain finer qualifiers:

```text
subject                    → headline/context, not an evidence role
current / previous         → scalar
absolute / percent change  → delta
range_low / range_high     → interval
ranked item                → category + scalar
event / step / frame       → sequence + time
node / edge                → network
method                     → source
```

## Relationship signatures

Convert atomic roles into one primary signature:

```text
scalar                                       → state
scalar(previous) + scalar(current)            → state_change
category[] + scalar[]                        → comparison
category[] + scalar[] + supplied/sorted order → ranking
series + time                                → trend
category(parts) + scalar(total)              → composition
scalar(current) + threshold                  → threshold_distance
scalar(current) + anchor                     → value_anchor
scalar(current) + anchor + delta             → discount_premium
scalar(estimate) + interval                  → uncertainty
sequence(events) + time                      → timeline
geo_point                                    → geo_location
geo_point + geo_region                       → geo_location
geo_path or geo_point(origin/destination)    → distance_route
network                                      → network
sequence(timestamped events)                 → timeline
sequence(initial/final states)               → before_after
category[] + independent evidence groups     → digest
```

Use a secondary signature only when it supports the primary question. Example: a
`value_anchor` card may include a short `trend` sparkline, but the ruler remains dominant.

## Allowed presentation transforms

Apply only deterministic transforms whose inputs are present:

- sort comparable items
- format numbers, units, timestamps, and signs
- calculate a display delta from two supplied compatible values
- normalize values to a supplied total
- calculate pixel positions from supplied values
- downsample a series while preserving first, last, extrema, and annotated events
- derive viewport bounds from supplied coordinates

Record every derived display field in `RenderSpec.source_bindings` with its input JSONPaths
and registered executable operation. Keep the source evidence items and their `source_path`
in `VisualSpec`; validation must recompute and compare the exact `verified_result`.

Do not:

- invent missing values
- choose an anchor or threshold
- turn a continuous value into severity without a supplied rule
- infer causality from temporal order
- hide outliers, missing periods, or negative values
- mix currencies, units, or incompatible time windows
- convert a script observation into a recommendation

## Missingness and uncertainty

Represent missingness explicitly:

| Input state | Visual treatment |
| --- | --- |
| field absent | omit the component; do not show zero |
| field unknown | show `Unknown` / `未知` |
| source unavailable | show a muted source-unavailable note |
| stale value | preserve the supplied timestamp and stale label |
| interval supplied | show the interval, not only its midpoint |
| estimated value | label `Estimate` / `估算` and show method if supplied |
| incomparable units | separate panels or text fallback |

Use visual confidence only if confidence is provided. Do not use opacity to imply
uncertainty unless a legend explains it.

## VisualSpec evidence

Compile semantic evidence into `VisualSpec`; do not treat it as renderer input:

```json
{
  "primary_question": "How far is current value from the stated anchor?",
  "intents": ["value_anchor"],
  "selected_modality": "image",
  "grammar": "value-band",
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
    }
  ]
}
```

`VisualSpec` is the semantic/medium intermediate representation. For text, the text
compiler/adapter consumes it directly and emits Rich Message plus HTML fallback. For image
or video, the AI/agent must compile it explicitly into a source-bound `RenderSpec`; the
pixel/frame renderer consumes only the latter. Package image/video work as
`{visual_spec, render_spec}` so validation can reproduce every displayed field.

## Binding rules

- Give every `VisualSpec.evidence[]` item a `source_path` into the original payload.
- Preserve those paths in text compiler output metadata/rows.
- Give every displayed image/video `RenderSpec` field a matching `source_bindings` entry.
- Use `{"jsonpath": "<evidence source_path>"}` or
  `{"source_path": "<evidence source_path>"}` for copied fields.
- Use `{inputs: [...], operation: "...", verified_result: ...}` for derived fields.
- The operation must exist in the audited renderer registry; prose/free-form formula strings
  are not executable provenance.
- Bind array/series/coordinate members, not only their container label.
- Reject a binding that resolves to a missing, differently typed, or incompatible-unit value.
- Never search for a “similar” key, infer a number from prose, or substitute zero.

Standalone unbound image/video `RenderSpec` files are acceptable only as explicitly marked
local/legacy fixtures. They cannot pass production or high-risk acceptance.

## Role-resolution checks

Before rendering, verify:

- every plotted value has a unit or is explicitly unitless
- comparison values share a unit and time basis
- every axis and legend maps back to source fields
- timestamps distinguish observation time from render time
- supplied uncertainty is visible
- derived deltas reproduce from the shown inputs
- every text field retains `VisualSpec.evidence.source_path`
- every displayed image/video field resolves through `RenderSpec.source_bindings`
- no color, icon, or title adds an unsupported judgment
