---
name: liquidity
description: Detect a liquidity event, idle cash, or a retirement-transition planning window for a premium client. Use when liquid_savings is large relative to income or age >= 50 with stable surplus.
---
# Liquidity and retirement skill (v1.0, default urgency: low)

Emit opportunity `liquidity` when the rules below fire.

## Signals to weigh
- High `cashflow_mean_surplus` with growing `liquid_savings` well above normal = idle cash.
- Large jumps in `liquid_savings` are a proxy for an inflow event (sale, inheritance, bonus).
- `rrsp_balance` near contribution limits with surplus continuing = non-registered opportunity.
- `age` >= 50 with stable surplus = pre-retirement planning window.

## Timeline
Usually 6-18 months. This is a planning conversation, not an urgent one.

## Product fit (options only)
BMO Nesbitt Burns / Private Wealth referral; TFSA or non-registered investing; insurance and estate review.

## Confidence
Keep confidence moderate unless idle cash is clearly large relative to income.
