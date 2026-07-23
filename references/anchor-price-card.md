# Anchor/value reference recipe

Use this recipe when a script already supplies a current value and a defensible reference
value. The visual explains their relationship. It never chooses the anchor, judges whether
the gap is actionable, or recommends an action.

Although the bundled legacy renderer retains finance-oriented field names for compatibility,
it has no business defaults: callers must supply every displayed fact, or pass the explicit
`--demo` flag for a visibly labeled fixture. The preferred production path is the
source-bound `RenderSpec.kind="anchor"` renderer. The visual grammar applies to prices,
targets, budgets, capacity, benchmarks, estimates, and other same-unit value/reference
pairs.

## Contents

- Admission requirements and compatibility payload
- Semantic mapping and visual anatomy
- Scale, caption, rendering, and scope rules

## Admission requirements

Require:

- `current` and `anchor` values
- compatible units and time basis
- an anchor/reference label or method
- observation time
- source when supplied by the host script

Optional:

- signed absolute or percentage delta
- supplied range/uncertainty
- prior values or a short trend
- contextual friction or constraints
- a caller-supplied state/severity label

If units or reference meaning are ambiguous, use structured text rather than implying a
common quantitative scale.

## Compatibility payload

The existing renderer accepts:

```json
{
  "pair": "rswETH / ETH",
  "severity": "P1",
  "timestamp": "05-21 15:41 SGT",
  "unit": "USD",
  "current_price": 3210.0,
  "fair_anchor_price": 3261.0,
  "fair_anchor_method": "7D p95",
  "discount_percent": 1.56,
  "net_per_100k": 800,
  "redeem_delay": "10d",
  "hedge": "YES",
  "venue": "Curve/Uniswap V3",
  "source_note": "caller-supplied context",
  "profit_ladder": [
    {"notional": "10k", "net": 76},
    {"notional": "50k", "net": 420},
    {"notional": "100k", "net": 800}
  ],
  "action": "caller-supplied text only"
}
```

Treat `severity`, `hedge`, `action`, and all numeric values as display inputs. Do not create,
reclassify, or reinterpret them.

Compile the recipe as a `{visual_spec, render_spec}` bundle. `VisualSpec` owns the
`value_anchor` decision and canonical `value-band` grammar. `RenderSpec.kind` is `anchor` and every
visible field must be bound:

```json
{
  "source_bindings": {
    "title": {
      "inputs": ["$.pair"],
      "operation": "copy",
      "verified_result": "rswETH / ETH"
    },
    "data.current": {"jsonpath": "$.current_price"},
    "data.anchors[0].value": {"jsonpath": "$.fair_anchor_price"},
    "data.unit": {"jsonpath": "$.unit"},
    "data.delta_pct": {
      "inputs": ["$.current_price", "$.fair_anchor_price"],
      "operation": "percent_delta",
      "verified_result": "-1.563937442502299908003679853"
    }
  }
}
```

This is the minimum binding excerpt for the common ruler. If the artifact also displays
pair, method, timestamp, source, state, context, or ladder rows, bind each of those fields and
each ladder item as well.

Never let the anchor renderer search the compatibility payload for likely field names or
guess a missing numeric value.

## Normalized semantic mapping

```text
pair                    → headline/context (not an evidence role)
current_price           → scalar (current qualifier)
fair_anchor_price       → anchor
unit                    → unit
fair_anchor_method      → source
discount_percent        → delta
timestamp               → time
redeem_delay            → interval
venue/source_note       → source
profit_ladder           → category + scalar
severity/hedge          → status
action                  → caller-supplied context
```

## Visual anatomy

### Answer band

- subject/pair
- current relationship to reference
- one hero signed gap

### Evidence band

- current and anchor on one aligned value ruler
- direct labels at both markers
- optional range or short trend if supplied
- optional ladder as aligned bars, not isolated KPI boxes

### Provenance band

- anchor method
- unit and time basis
- observation time
- source/context and supplied uncertainty

The shared-axis ruler is the defining encoding. If the renderer shows current and anchor only
as separate stat boxes, it has not fully expressed the relationship.

## Scale rules

- Put current and anchor on the same axis.
- Include enough surrounding range to show distance without exaggeration.
- Show both absolute and percentage delta only when both are useful and reproducible.
- Keep the sign convention explicit: negative/below and positive/above.
- Do not use green/red alone to imply discount/premium quality.
- If a meaningful supplied range exists, show it as a labeled band.
- Keep anchor method next to the anchor label.

## Caption

Use native text for:

- one-sentence accessible answer
- observation time and source
- supplied uncertainty or missing-data caveat

Do not repeat every card field. Do not add `buy`, `sell`, `safe`, `risk-free`, `escalate`, or
similar judgment unless the exact text is already supplied and the host script intends it
to be displayed.

## Rendering

`scripts/render_anchor_price_card.py` composes nodes from `scripts/layout.py`; read
`rendering.md` for the node system.

- pass every displayed business field explicitly; bare `--out` must fail
- use `--demo` only for the bundled, visibly labeled fixture
- keep height content-driven
- use CJK-aware fonts
- treat caller-supplied state color as secondary encoding and pair it with text
- preserve a light and dark theme without changing semantic color meaning
- validate at 320, 375, 390, and 430 px, not only at source resolution
- fail to structured text on incompatible/missing core values

## Boundary

This recipe does not fetch market data, select fair value, define severity, calculate a
business threshold, decide whether to alert, or control execution. It only visualizes values
and labels already present in the script's output.
