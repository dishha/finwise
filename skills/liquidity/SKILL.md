---
name: liquidity
description: Detect idle cash, a liquidity event, or a retirement-transition planning window. Use when liquid_savings is large relative to monthly_net_income, or age >= 50 with a stable surplus.
---
# Liquidity and retirement skill (v1.1, default urgency: low)

Emit opportunity `liquidity` when the rules below fire.

## Signals to weigh
- `liquid_savings` greater than roughly 12 x `monthly_net_income` with `cashflow_volatility` LOW = idle cash. Exception: if a home_purchase card is also being emitted, that cash is a down payment, not idle. Do not double-count.
- `rrsp_balance` growing with surplus continuing = registered vs non-registered planning.
- `age` >= 50 with `income_stability` SALARIED and positive `monthly_surplus` = pre-retirement planning window.
- `rewards_tier` GOLD or higher indicates an engaged premium relationship; mention it as context only.

## Timeline
Usually 6-18 months. This is a planning conversation, not an urgent one.

## Product fit (options only)
BMO Nesbitt Burns / Private Wealth referral; TFSA or non-registered investing; insurance and estate review.

## Confidence
Keep confidence moderate unless idle cash is clearly large relative to income.
