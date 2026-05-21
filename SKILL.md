---
name: tg-watch-anchor-price-card
description: Create Telegram photo-card alerts for anchor-priced assets such as stablecoins, wrapped assets, LST/LRT tokens, and LP shares when the user needs a visual card showing current price, fair anchor, discount/premium, redemption delay, hedge availability, and profit ladder.
---

# TG Watch Anchor Price Card

Use this skill when a Telegram monitoring bot needs a **photo + caption** alert for an asset whose risk is measured against an anchor price, not just a raw price move.

Good fits:
- stablecoin peg deviation
- wrapped asset discount or premium
- LST/LRT secondary-market discount
- LP share fair-value gap
- redeemable asset vs market price spread

Do not use it for generic uptime, cron heartbeat, news digest, or non-price system alerts.

## Output Contract

Every alert should produce:

1. A rendered image card used as the Telegram `sendPhoto` payload.
2. A short caption used as the Telegram `caption`.
3. A clear non-trading disclaimer when the card is only a monitor signal.

The card must answer, at a glance:

- what asset pair is being compared
- current price
- fair anchor price
- discount or premium
- estimated net profit per notional size
- redemption delay
- hedge availability
- liquidity/source venue
- profit ladder by notional

## Visual Pattern

Use a dark evidence card with an accent severity rail.

Primary fields:
- `pair`: e.g. `rswETH / ETH`
- `severity`: `P0`, `P1`, `P2`, or `FYI`
- `discount_percent` or `premium_percent`
- `current_price`
- `fair_anchor_price`
- `fair_anchor_method`: e.g. `7D p95`, `oracle`, `NAV`, `TWAP`
- `net_per_100k`
- `redeem_delay`
- `hedge`: `YES`, `PARTIAL`, or `NO`
- `venue`: e.g. `Curve/Uniswap V3`

Profit ladder:
- show at least 3 notional points, typically `10k`, `50k`, `100k`
- show estimated net value after fees/slippage/hedge cost
- never imply execution certainty

## Caption Pattern

Keep captions compact and mobile-readable.

```text
[SECURITY-P1] rswETH / ETH anchor alert
ANCHOR - discount 1.56% - net $800/100K

Pair: rswETH / ETH - Curve/Uniswap V3
Anchor: current $3,210 vs fair 7D p95 $3,261
Window: redeem 10d - hedge available
Action: Watch only; escalate if discount widens or liquidity thins
```

## Data Discipline

- Use live market, oracle, protocol, or pool data for prices.
- Label the fair-anchor method.
- If the card is for DeFi or real-money monitoring, state whether it is a monitor signal or an execution signal.
- Do not generate financial numbers from memory.
- If a required data source is unavailable, send a text fallback explaining what is missing instead of fabricating the image.

## Script

Use `scripts/render_anchor_price_card.py` to render a PNG card.

Example:

```bash
python3 scripts/render_anchor_price_card.py \
  --out /tmp/anchor-card.png \
  --pair "rswETH / ETH" \
  --discount 1.56 \
  --current 3210 \
  --fair 3261 \
  --net-100k 800 \
  --redeem "10d" \
  --hedge "YES" \
  --venue "Curve/Uniswap V3" \
  --method "7D p95"
```

Then send `/tmp/anchor-card.png` with the caption generated from the same inputs.

## Reference

For the field schema and example card anatomy, read `references/anchor-price-card.md`.
