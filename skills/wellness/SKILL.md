---
name: wellness
description: Financial risk and suitability check that can veto or downgrade any opportunity. ALWAYS apply after opportunity detection and before writing cards.
---
# Wellness and suitability skill (v1.1)

Run this after opportunity skills, before finalizing cards. It protects the client and the advisor.

## Assess
- `cashflow_volatility` HIGH, or `monthly_surplus` <= 0, or `income_stability` not SALARIED with a thin surplus = material cash-flow risk.
- `credit_utilization` > 0.5 or `missed_payments_12m` > 0 = credit stress; suitability concern for any new credit product.
- `monthly_debt_payments` above roughly 35% of `monthly_net_income` = debt load concern.
- `do_not_contact` = true = no outreach regardless of opportunity.

## Verdict
- `proceed`: no material risk.
- `downgrade`: multiply the card's confidence by 0.7 and add a wellness_note explaining why.
- `veto`: cap confidence at 0.35 and set recommended_action to "Hold outreach on this opportunity; check in on financial stability first."

## Rules
Every reason must point to a real signal key and value. Record the verdict on each card as `wellness_override`. This is the consumer-protection step: the advisor sees why an opportunity was held back.
