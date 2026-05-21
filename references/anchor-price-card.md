# Anchor Price Card Reference

## Purpose

Anchor-price alerts explain whether an asset is trading away from a defensible fair value and whether that gap is actionable after friction.

This differs from a price-move alert:

- price-move alert: "asset moved 12%"
- anchor-price alert: "asset trades 1.56% below fair anchor, redeem delay 10d, hedge available, estimated net $800/100K"

## Required Inputs

```json
{
  "pair": "rswETH / ETH",
  "severity": "P1",
  "timestamp": "05-21 15:41 SGT",
  "current_price": 3210.0,
  "fair_anchor_price": 3261.0,
  "fair_anchor_method": "7D p95",
  "discount_percent": 1.56,
  "net_per_100k": 800,
  "redeem_delay": "10d",
  "hedge": "YES",
  "venue": "Curve/Uniswap V3",
  "source_note": "Swell LRT, redeem 7-14d",
  "profit_ladder": [
    {"notional": "10k", "net": 76},
    {"notional": "50k", "net": 420},
    {"notional": "100k", "net": 800}
  ],
  "action": "Watch only; escalate if discount widens or liquidity thins"
}
```

## Severity Guidance

- `P0`: peg/anchor break with direct liquidation, solvency, or system-wide exposure risk.
- `P1`: large or widening gap with enough liquidity to matter.
- `P2`: small gap, uncertain source quality, or low-liquidity observation.
- `FYI`: informational spread with no action.

## Visual Anatomy

Top section:
- label: `DE WRAPPED ASSET ALERT`
- pair name
- severity and timestamp

Middle section:
- discount/premium
- net per notional
- current price
- fair anchor
- redemption window
- hedge flag

Bottom section:
- profit ladder
- venue/source note

## Caption Rules

Keep the caption under roughly 700 characters. The image should carry the dense numbers; the caption should say what changed and what action is allowed.

Use "Watch only" or "monitor signal" if the card is not an execution instruction.

Avoid:
- "buy now"
- "guaranteed"
- "risk-free"
- unlabeled fair-value methods
- numbers with no source or timestamp
