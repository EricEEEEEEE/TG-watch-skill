#!/usr/bin/env python3
"""Render a Telegram anchor/value-band visual card.

Rendering is driven by the zero-dependency Pillow layout layer in ``layout.py``
(no browser, no Node, no system libraries). The card is described as a tree of
nodes; positions are computed, not hand-written. Light theme by default to match
the FAB card visual language; pass ``--theme dark`` for the original dark look.

The renderer visualizes values supplied by its caller. It does not decide alert
severity, trading action, fair value, or delivery policy.
"""
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from PIL import Image  # noqa: F401  (fail fast with a friendly message)
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow is required: python3 -m pip install pillow") from exc

import layout as L


DEMO_VALUES = {
    "pair": "DEMO ASSET / REFERENCE",
    "sequence": "fixture",
    "severity": "SUPPLIED STATE",
    "timestamp": "2026-07-23 10:00 SGT",
    "discount": 1.5,
    "current": 98.5,
    "fair": 100.0,
    "method": "CALLER REFERENCE",
    "net_100k": 750.0,
    "ladder_10k": 75.0,
    "ladder_50k": 375.0,
    "ladder_100k": 750.0,
    "redeem": "CALLER VALUE",
    "hedge": "CALLER VALUE",
    "venue": "DEMO SOURCE",
    "source_note": "Explicit --demo fixture; not real data",
}

REQUIRED_INPUTS = (
    "pair",
    "timestamp",
    "discount",
    "current",
    "fair",
    "method",
    "net_100k",
    "ladder_10k",
    "ladder_50k",
    "ladder_100k",
    "redeem",
    "hedge",
    "venue",
    "source_note",
)


def money(value: float) -> str:
    return f"${value:,.2f}"


def _hedge_color(pal: L.Palette, hedge: str) -> "tuple":
    key = str(hedge).strip().upper()
    if key in ("YES", "FULL", "OK"):
        return pal.good
    if key in ("PARTIAL", "SOME"):
        return pal.warn
    if key in ("NO", "NONE"):
        return pal.bad
    return pal.text


def build_card(args: argparse.Namespace, pal: L.Palette) -> list:
    sev = L.severity_color(pal, args.severity)
    disc_label = "DISCOUNT" if args.discount >= 0 else "PREMIUM"

    # These are display inputs, not estimates derived by the renderer.  The
    # calling script remains responsible for any domain calculation.
    ladder = [
        ("10k", args.ladder_10k),
        ("50k", args.ladder_50k),
        ("100k", args.ladder_100k),
    ]
    max_net = max((v for _, v in ladder), default=1) or 1

    ladder_nodes: list = []
    for i, (tag, net) in enumerate(ladder):
        if i:
            ladder_nodes.append(L.Gap(14))
        ladder_nodes.append(L.bar_row(pal, tag, net / max_net, f"${net:,.0f}", fill=pal.good))

    return [
        L.Text(args.eyebrow, 32, pal.muted, bold=True, tracking=2),
        L.Gap(14),
        L.Text(args.pair, 60, pal.text, bold=True, max_lines=2),
        L.Gap(8),
        L.Text(
            " · ".join(part for part in (f"#{args.sequence}" if args.sequence else "",
                                         args.severity, args.timestamp) if part),
            30,
            pal.muted,
            bold=True,
        ),
        L.Gap(30),
        L.Row(
            [
                L.stat_box(pal, disc_label, f"{abs(args.discount):.2f}%", value_color=sev),
                L.stat_box(pal, "NET / 100K", f"${args.net_100k:,.0f}", value_color=pal.good),
            ],
            gap=22,
        ),
        L.Gap(20),
        L.Row(
            [
                L.stat_box(pal, "CURRENT", money(args.current), value_size=42, big=False),
                L.stat_box(pal, f"FAIR {args.method}", money(args.fair), value_size=42, big=False),
            ],
            gap=16,
        ),
        L.Gap(16),
        L.Row(
            [
                L.stat_box(pal, "REDEEM", str(args.redeem), value_size=42, big=False),
                L.stat_box(
                    pal,
                    "HEDGE",
                    str(args.hedge),
                    value_size=42,
                    big=False,
                    value_color=_hedge_color(pal, args.hedge),
                ),
            ],
            gap=16,
        ),
        L.Gap(30),
        L.Text("Profit ladder", 40, pal.text, bold=True),
        L.Gap(18),
        *ladder_nodes,
        L.Gap(26),
        L.Divider(pal.line),
        L.Gap(18),
        L.Text(f"{args.venue} · {args.source_note}", 30, pal.muted, max_lines=2),
        L.Gap(6),
        L.Text(args.footer, 30, pal.muted, max_lines=2),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render caller-supplied anchor/reference values as a visual card."
    )
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="use an explicit, visibly labeled fixture instead of production inputs",
    )
    parser.add_argument("--eyebrow", default="ANCHOR VALUE WATCH")
    parser.add_argument("--pair")
    parser.add_argument("--sequence", default="")
    parser.add_argument("--severity", default="")
    parser.add_argument("--timestamp")
    parser.add_argument("--discount", type=float)
    parser.add_argument("--current", type=float)
    parser.add_argument("--fair", type=float)
    parser.add_argument("--method")
    parser.add_argument("--net-100k", type=float)
    parser.add_argument("--ladder-10k", type=float)
    parser.add_argument("--ladder-50k", type=float)
    parser.add_argument("--ladder-100k", type=float)
    parser.add_argument("--redeem")
    parser.add_argument("--hedge")
    parser.add_argument("--venue")
    parser.add_argument("--source-note")
    parser.add_argument(
        "--footer",
        default="Values supplied by the calling script · visual output only",
    )
    parser.add_argument("--theme", choices=["light", "dark"], default="light")
    parser.add_argument("--width", type=int, default=1200)
    args = parser.parse_args()
    if args.demo:
        for field, value in DEMO_VALUES.items():
            if getattr(args, field) in (None, ""):
                setattr(args, field, value)
    missing = [field.replace("_", "-") for field in REQUIRED_INPUTS if getattr(args, field) is None]
    if missing:
        parser.error(
            "missing caller-supplied visual inputs: %s (or pass --demo)"
            % ", ".join("--" + field for field in missing)
        )
    return args


def main() -> None:
    args = parse_args()
    pal = L.dark_palette() if args.theme == "dark" else L.light_palette()
    L.render_card(args.out, children=build_card(args, pal), palette=pal,
                  width=args.width, rail_color=L.severity_color(pal, args.severity))


if __name__ == "__main__":
    main()
