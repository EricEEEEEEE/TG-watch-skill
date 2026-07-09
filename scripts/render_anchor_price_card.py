#!/usr/bin/env python3
"""Render a Telegram anchor-price alert card.

Rendering is driven by the zero-dependency Pillow layout layer in ``layout.py``
(no browser, no Node, no system libraries). The card is described as a tree of
nodes; positions are computed, not hand-written. Light theme by default to match
the FAB card visual language; pass ``--theme dark`` for the original dark look.
"""
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from PIL import Image  # noqa: F401  (fail fast with a friendly message)
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow is required: python3 -m pip install pillow") from exc

import layout as L


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

    ladder = [
        ("10k", args.net_100k * 0.095),
        ("50k", args.net_100k * 0.525),
        ("100k", args.net_100k),
    ]
    max_net = max((v for _, v in ladder), default=1) or 1

    ladder_nodes: list = []
    for i, (tag, net) in enumerate(ladder):
        if i:
            ladder_nodes.append(L.Gap(14))
        ladder_nodes.append(L.bar_row(pal, tag, net / max_net, f"${net:,.0f}", fill=pal.good))

    return [
        L.Text("DE WRAPPED ASSET ALERT", 24, pal.muted, bold=True, tracking=2),
        L.Gap(14),
        L.Text(args.pair, 54, pal.text, bold=True),
        L.Gap(8),
        L.Text(f"#{args.sequence} · {args.severity} · {args.timestamp}", 21, pal.muted, bold=True),
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
                L.stat_box(pal, "CURRENT", money(args.current), value_size=27, big=False),
                L.stat_box(pal, f"FAIR {args.method}", money(args.fair), value_size=27, big=False),
                L.stat_box(pal, "REDEEM", str(args.redeem), value_size=27, big=False),
                L.stat_box(pal, "HEDGE", str(args.hedge), value_size=27, big=False,
                           value_color=_hedge_color(pal, args.hedge)),
            ],
            gap=16,
        ),
        L.Gap(30),
        L.Text("Profit ladder", 30, pal.text, bold=True),
        L.Gap(18),
        *ladder_nodes,
        L.Gap(26),
        L.Divider(pal.line),
        L.Gap(18),
        L.Text(f"{args.venue} · {args.source_note}", 20, pal.muted, max_lines=1),
        L.Gap(6),
        L.Text("Monitor signal · watch only · not an execution instruction", 18, pal.muted, max_lines=2),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a Telegram anchor-price alert card.")
    parser.add_argument("--out", required=True)
    parser.add_argument("--pair", default="rswETH / ETH")
    parser.add_argument("--sequence", default="2/3")
    parser.add_argument("--severity", default="P1")
    parser.add_argument("--timestamp", default="05-21 15:41 SGT")
    parser.add_argument("--discount", type=float, default=1.56)
    parser.add_argument("--current", type=float, default=3210.0)
    parser.add_argument("--fair", type=float, default=3261.0)
    parser.add_argument("--method", default="7D P95")
    parser.add_argument("--net-100k", type=float, default=800.0)
    parser.add_argument("--redeem", default="10d")
    parser.add_argument("--hedge", default="YES")
    parser.add_argument("--venue", default="Curve/Uniswap V3")
    parser.add_argument("--source-note", default="Swell LRT redeem 7-14d")
    parser.add_argument("--theme", choices=["light", "dark"], default="light")
    parser.add_argument("--width", type=int, default=1200)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pal = L.dark_palette() if args.theme == "dark" else L.light_palette()
    L.render_card(args.out, children=build_card(args, pal), palette=pal,
                  width=args.width, rail_color=L.severity_color(pal, args.severity))


if __name__ == "__main__":
    main()
