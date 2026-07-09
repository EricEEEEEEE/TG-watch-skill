# Rendering engine: `scripts/layout.py`

A thin declarative layout layer over Pillow. **Only Pillow is required** — no
browser, no Node, no system libraries. You describe a card as a tree of nodes;
the layer measures and positions everything, so you never write pixel
coordinates by hand.

## Why this exists

The first version placed every element with absolute coordinates
(`draw.text((70, 128), ...)`, `y = 575 + i * 34`). Adding a field meant
recomputing every position below it. The layout layer replaces that with
composable nodes that compute their own size and position.

## Themes

- `light_palette(accent=...)` — default, matches the FAB card visual language.
- `dark_palette(accent=...)` — the original dark look.
- `severity_color(palette, "P0"|"P1"|"P2"|...)` — red / amber / blue.

A `Palette` exposes: `bg card panel line text muted accent good warn bad on_accent`.

## Fonts (content-aware, CJK-safe)

`pick_font(text, size, bold)` chooses a **CJK** font (Hiragino / STHeiti / Noto)
for any string containing CJK characters and a **Latin** font (Helvetica / Arial)
otherwise, so mixed English/Chinese cards render correctly without tofu boxes.

## Nodes

Every node implements `measure(draw, width) -> height` and
`render(draw, x, y, width)`.

| Node | Purpose |
| --- | --- |
| `Text(text, size, color, bold=, max_lines=, align=, tracking=)` | Wrapped, CJK-aware text; `align` left/center/right; `tracking` for small-caps labels. |
| `Gap(h)` | Vertical spacer. |
| `Divider(color, pad=)` | Hairline separator. |
| `Bar(ratio, track, fill, height=)` | Rounded progress bar (0–1). |
| `Column(children, gap=, pad=, bg=, radius=, border=)` | Vertical stack; optional rounded panel background. |
| `Row(children, gap=, widths=, valign=)` | Horizontal layout; `widths` entries are px (fixed) or `None` (flex/equal). |

## Semantic builders

- `stat_box(pal, label, value, value_color=, value_size=, sub=, big=)` — a rounded
  metric panel (label + big value + optional sub-line).
- `bar_row(pal, label, ratio, value, fill=)` — a labeled progress row for ladders.

## Card frame

```python
import layout as L

pal = L.light_palette()
L.render_card(
    "out.png",
    palette=pal,
    width=1200,                 # height is auto-computed from content
    rail_color=L.severity_color(pal, "P1"),
    children=[
        L.Text("SECTION LABEL", 24, pal.muted, bold=True, tracking=2),
        L.Gap(14),
        L.Text("Headline", 54, pal.text, bold=True),
        L.Row([
            L.stat_box(pal, "DISCOUNT", "1.56%", value_color=pal.accent),
            L.stat_box(pal, "NET / 100K", "$800", value_color=pal.good),
        ], gap=22),
    ],
)
```

## Adding a new card type

1. Write a builder that returns a `list` of nodes (see
   `render_anchor_price_card.py: build_card`).
2. Call `render_card(out, children=..., palette=..., rail_color=...)`.
3. Keep numbers sourced and labeled; keep the "monitor signal / watch only"
   disclaimer when the card is not an execution instruction.
