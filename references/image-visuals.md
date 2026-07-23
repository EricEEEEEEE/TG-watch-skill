# Static image visual system

Use a static image when spatial placement, a shared quantitative scale, or stable annotated
composition materially improves comprehension. The image must answer its primary question
without requiring the caption.

## Contents

- Image grammar and card anatomy
- VisualSpec/RenderSpec contract
- Quantitative, hierarchy, and export rules
- Small multiples, albums, and captions
- Anti-patterns

## Image grammar

| VisualIntent | Preferred encoding | Avoid |
| --- | --- | --- |
| `state` | hero metric plus short context | gauge without a meaningful scale |
| `state_change` | old/new pair, slopegraph, or delta bar | two unrelated KPI boxes |
| `comparison` | dot plot or aligned horizontal bars | pie chart |
| `ranking` | sorted horizontal bars | decorative podiums |
| `trend` | line with direct labels and event markers | smoothed line that changes evidence |
| `composition` | 100% stacked bar or small multiples | many-slice donut |
| `threshold_distance` | bullet chart with current and boundary | speedometer |
| `value_anchor` | common-axis ruler with current and anchor | isolated values in separate cards |
| `discount_premium` | value ruler plus signed absolute/percent gap | color-only `cheap/expensive` |
| `spread` | common-axis endpoints plus signed distance | two unrelated KPI boxes |
| `uncertainty` | interval, error bar, or fan band | unlabeled transparency |
| `timeline` | ordered event rail | prose scattered across panels |
| `geo_location` | point/region map when native map is insufficient | decorative basemap |
| `distance_route` | route map with supplied distance | straight line labeled as route |
| `network` | annotated topology; matrix for dense graphs | hairball graph |
| `before_after` | aligned bars or locked-scale panels | unmatched scales |
| `digest` | one overview plus aligned small multiples | unrelated card mosaic |

Read `map-visuals.md` for geographic encodings and `anchor-price-card.md` for the
anchor-specific recipe.

## Spec contract

Let `VisualSpec` decide modality and grammar. Let the AI/agent explicitly compile it into a
`RenderSpec` whose `kind`, `data`, `meta`, and `source_bindings` are complete before calling
the renderer. Bind every visible number, label, unit, timestamp, source, state, and plotted
series member to `VisualSpec` evidence or declare its input paths, registered executable
operation, and exact recomputed result.

The renderer may calculate pixels, ticks, wrapping, and viewport geometry. It may not guess
data values, substitute a nearby field, choose an anchor/threshold, or change the grammar.

## Card anatomy

Compose every card in three bands:

1. **Answer band:** eyebrow/context, headline, one hero value or state.
2. **Evidence band:** one dominant chart plus at most one supporting module.
3. **Provenance band:** units, time window, observation time, method, source, missingness.

Use a visual rail, chip, or accent only for a state supplied by the caller. Never derive
severity from palette choice.

## Quantitative rules

- Use a common scale for comparable values.
- Start bars at zero unless the visual explicitly communicates a bounded deviation scale.
- A line chart may use a non-zero domain; label the range and avoid exaggerating small moves.
- Show the threshold or anchor on the same axis as the current value.
- Preserve negative values and zero crossings.
- Direct-label short series; use a legend only when labels would collide.
- Show the observation window and sampling interval for trends.
- Mark gaps in time series; do not connect missing periods as continuous evidence.
- Display supplied uncertainty and distinguish it from the central estimate.
- Use only defensible significant digits from input.

## Visual hierarchy

- Give 35–50% of available attention to the dominant relationship.
- Use one hero metric; supporting metrics must be visibly secondary.
- Keep headings short enough to fit on two lines.
- Align numbers by decimal or right edge when comparison matters.
- Reserve accent color for one relationship or supplied state.
- Use whitespace and grouping before borders.
- Keep a maximum of three panel depths: canvas, group, component.

## Export geometry

Use a width-first responsive layout and compute height from content.

Recommended baselines:

- `1200 × auto` for portrait/compact Telegram cards
- `1200 × 675` for landscape charts and video posters
- split a card when height exceeds roughly `1.5 × width`
- keep critical content inside a 6% safe margin

Test the rendered file at 320, 375, 390, and 430 CSS-pixel-equivalent widths. Do not judge
legibility only at the source resolution.

At a 1200 px export width, use these starting ranges:

| Element | Source size |
| --- | ---: |
| hero number | 72–120 px |
| headline | 48–64 px |
| section/value | 36–48 px |
| body/axis | 34–42 px |
| metadata | at least 30 px |

Adjust for font metrics and CJK density; the mobile downsample, not the source file, is the
acceptance target.

## Small multiples and albums

Use small multiples when the same encoding repeats across comparable entities. Keep scales
shared unless independent scales are explicitly labeled.

Use an overview-plus-detail sequence when one card cannot remain readable:

1. overview with the answer and global comparison
2. detail chart/map
3. method or evidence frame only when needed

Keep each frame independently titled and timestamped. Do not depend on album order for the
only copy of a unit or source.

## Caption contract

Write a short native caption containing:

- an accessible one-line answer
- timestamp/source
- a caveat or uncertainty note when supplied

Do not duplicate the entire image. Do not hide the only unit, scale, or source in the
caption.

## Anti-patterns

Reject a static design that:

- imitates a desktop dashboard at phone scale
- contains more than one competing hero metric
- uses red/green as the only distinction
- uses decorative gauges, gradients, 3D effects, or stock imagery
- turns long prose into pixels
- truncates labels without a recoverable full form
- changes axis scale between comparable panels without warning
- places unrelated metrics into equal KPI tiles
- lacks source, timestamp, units, or missing-data disclosure
- presents an inferred recommendation or business judgment
