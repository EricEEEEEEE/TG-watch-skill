# Declarative raster rendering

`scripts/layout.py` is a thin declarative layer over Pillow. Describe a card as a tree of
nodes; the engine measures and positions content instead of relying on handwritten absolute
coordinates.

Use it for cards, compact comparisons, text-led evidence panels, and shared layout
primitives. Use a purpose-built chart, map, or motion renderer when the dominant relationship
requires axes, geographic projection, or frame sequencing.

## Contents

- Rendering boundary, themes, and fonts
- VisualSpec/RenderSpec contract, nodes, and recipe workflow
- Layout invariants and renderer selection

## Rendering boundary

The image/video renderer:

- receives `RenderSpec`, normally inside `{visual_spec, render_spec}`
- validates every displayed field against `source_bindings`
- formats and positions supplied values
- derives pixel geometry deterministically
- produces previews and validation evidence

It does not fetch data, create thresholds/anchors/severity, decide business actions, or
change scheduling, routing, retries, deduplication, or notification behavior.

## VisualSpec and RenderSpec

Keep the two IR layers distinct:

| Layer | Owner | Contains | Must not contain/do |
| --- | --- | --- | --- |
| `VisualSpec` | semantic inspector / AI agent | question, roles, intents, evidence with `source_path`, modality scores, selected modality, grammar, feature gates, fallbacks | renderer coordinates or guessed display values |
| text compiler/adapter | deterministic text path | `VisualSpec` evidence → Rich Message representation + HTML fallback | create/consume `RenderSpec` or guess copy/numbers |
| `RenderSpec` | explicit image/video compiler step | `version`, `kind`, `title`, `subtitle`, `theme`, optional `width`/`accent`, exact `data`, `meta`, and `source_bindings` | semantic reclassification or automatic fact inference |
| image/video renderer | deterministic code | validated `RenderSpec` only | choose grammar, search source payload, guess numbers |

For image/video, package them as:

```json
{"visual_spec": {}, "render_spec": {}}
```

For direct fields, map each render path to an original payload JSONPath that is present in
`VisualSpec.evidence[].source_path`:

```json
{"data.current": {"jsonpath": "$.current_price"}}
```

For derived fields, declare source inputs, a registered executable operation, and its exact
result:

```json
{
  "data.delta_pct": {
    "inputs": ["$.current_price", "$.fair_anchor_price"],
    "operation": "percent_delta",
    "verified_result": "-1.563937442502299908003679853"
  }
}
```

The renderer recomputes `verified_result` from evidence and then compares the target value.
Supported audited operations are `copy`, `delta`, `ratio`, `percent_delta`, `sum`,
`zip_items`, `indexed_points`, `sequence_frames`, `endpoint_points`, `node_objects`,
`edge_objects`, `timeline_events`, `interval_band`, `before_after_items`, and
`format_value_unit`. Reject unknown/free-form operations. Embed digests of both specs and
source-binding validation in artifact metadata. Do not allow fallback key search, numeric
guessing, self-reported derived values, or silent zero/default substitution.

A standalone image/video `RenderSpec` may omit `source_bindings` for a clearly marked local
fixture or legacy exploration only. Production and high-risk gates require the validated
bundle.

## Themes

- `light_palette(accent=...)` — default light visual language
- `dark_palette(accent=...)` — dark variant
- `severity_color(palette, value)` — visualizes a caller-supplied state

A `Palette` exposes:
`bg card panel line text muted accent good warn bad on_accent`.

Keep semantic meaning consistent across themes. Pair every state color with text, shape, or
position.

## Fonts

`pick_font(text, size, bold)` selects a CJK-capable font for CJK strings and a Latin font for
Latin-only strings.

Required behavior:

- provide deterministic fallback order
- validate mixed CJK/Latin/numeric strings
- fail on tofu/replacement glyphs
- materialize and test final output at 320, 375, 390, and 430 px
- use the source-size ranges in `image-visuals.md`

## Nodes

Every node implements:

```text
measure(draw, width) -> height
render(draw, x, y, width)
```

| Node | Purpose |
| --- | --- |
| `Text(...)` | wrapped, CJK-aware text with alignment and line limits |
| `Gap(h)` | vertical rhythm |
| `Divider(...)` | structural separator |
| `Bar(...)` | normalized one-dimensional magnitude |
| `Column(...)` | content-driven vertical stack/panel |
| `Row(...)` | horizontal fixed/flexible layout |

Semantic builders:

- `stat_box(...)` — label, value, optional context
- `bar_row(...)` — label, normalized bar, direct value

Do not use stat boxes for every field. Select nodes from the dominant relationship:

```text
state             → one hero stat + context
comparison/rank   → aligned bar rows
threshold         → bar + explicit threshold marker
anchor            → common-axis current/reference markers
timeline          → ordered rail
digest            → grouped sections or aligned small multiples
```

## Card frame

```python
import layout as L

pal = L.light_palette()
L.render_card(
    "out.png",
    palette=pal,
    width=1200,
    rail_color=pal.accent,
    children=[
        L.Text("CONTEXT", 32, pal.muted, bold=True, tracking=2),
        L.Gap(14),
        L.Text("One primary answer", 56, pal.text, bold=True),
        L.Row([
            L.stat_box(pal, "CURRENT", "98.2", value_size=72),
            L.stat_box(pal, "REFERENCE", "100.0", value_size=52),
        ], gap=22),
    ],
)
```

The rail is decorative unless the caller supplies a state with documented meaning. Never
let color create a state.

## Add a visual recipe

1. Generate/inspect `VisualSpec` using `decision-engine.md`.
2. Verify evidence and `source_path` using `semantic-roles.md`.
3. For text, pass `VisualSpec` to the text compiler/adapter and inspect both rich and HTML
   paths.
4. For image/video, explicitly compile `VisualSpec` into a source-bound `RenderSpec`.
5. Validate the `{visual_spec, render_spec}` image/video bundle.
6. Dispatch `RenderSpec.kind` to a renderer.
7. Render normal, missing, extreme, and long-CJK fixtures.
8. Inspect source plus 320, 375, 390, and 430 px outputs.
9. Run the gates in `acceptance-gates.md`.

Split an overloaded card rather than adding more equal-weight panels.

## Layout invariants

- compute height from content
- keep a 6% safe margin
- use one hero metric and one dominant evidence component
- allow no silent truncation
- keep units and values together
- align comparable numbers
- preserve missing/unknown states
- include timestamp/source in the artifact
- keep caption values generated from the same payload

## Grammar to renderer kind

`VisualSpec.grammar` controls the compilation target. `RenderSpec.kind` controls deterministic
dispatch:

| Visual grammar | `RenderSpec.kind` | Renderer |
| --- | --- | --- |
| `verdict-key-values` | none — text path | `render_rich_message.py` consumes `VisualSpec` |
| `rich-digest` / `html-digest` | none — text path | `render_rich_message.py` rich/HTML output |
| `native-location` | none — native/text path | runtime-verified Telegram carrier or text fallback |
| `hero-card` | `hero` | `render_visual.py` → `render_chart.py` |
| `value-band` | `anchor` | `render_visual.py` → `render_chart.py` |
| `threshold-bullet` | `threshold` | `render_visual.py` → `render_chart.py` |
| `aligned-bars` | `comparison` | `render_visual.py` → `render_chart.py` |
| `ranked-bars` | `ranking` | `render_visual.py` → `render_chart.py` |
| `annotated-line` | `trend` | `render_visual.py` → `render_chart.py` |
| `stacked-composition` | `composition` | `render_visual.py` → `render_chart.py` |
| `range-band` | `uncertainty` | `render_visual.py` → `render_chart.py` |
| `node-link` | `network` | `render_visual.py` → `render_chart.py` |
| `point-map` | `point` | `render_visual.py` → `render_map.py` |
| `route-map` | `route` | `render_visual.py` → `render_map.py` |
| `event-timeline` | `timeline` | `render_visual.py` → `render_chart.py` |
| `sequence-replay` | `sequence` | `render_visual.py` → `render_motion.py` |

Any other unmatched image intent requires a new canonical grammar plus a semantically
matching registered renderer. Until then, use the declared text/native fallback. Do not
alias it to a different visualization merely to make dispatch succeed.

Legacy aliases may be normalized at input boundaries for compatibility, but `VisualSpec`
must store only the canonical grammar shown above.

## Renderer selection

```text
declarative Pillow nodes → cards and compact comparisons
chart renderer           → axes, trends, distributions, uncertainty
map renderer             → projection, routes, regions, geographic layers
motion renderer          → admitted time/transition sequences
text compiler/adapter    → short text and structured report from VisualSpec
native Telegram          → runtime-verified carrier for compiled text or simple point map
```

The lightest sufficient renderer wins. Do not rasterize native text without a visual reason.
