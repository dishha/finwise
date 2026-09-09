---
name: home_purchase
description: Detect readiness to buy a home from FHSA, savings, cash flow, credit and intent signals. Use when housing_intent is FIRST_TIME_BUYER or home_goal_status is ACTIVE or preapproval_status is set or calculator_viewed is true.
---
# Home purchase skill (v1.1, default urgency: medium)

Emit opportunity `home_purchase` when the rules below fire. You MUST call `assess_savings` and `check_qualification` before emitting this card.

## Signals to weigh
- `housing_intent` = FIRST_TIME_BUYER, `home_goal_status` = ACTIVE, `preapproval_status` = COMPLETED, `calculator_viewed` = true are explicit intent. Two or more = strong.
- `fhsa_monthly_velocity` > 0 and `savings_monthly_contribution` > 0 = actively saving.
- `assess_savings.gap` and `months_to_target` set readiness and timeline. `target_price` and `target_down_payment_pct` come from the client's own plan.
- `check_qualification.qualifies` must be true before confidence can exceed 0.7. This is rule-based (GDS/TDS at the stress-test rate plus credit score); never override it.
- `income_stability` = SALARIED and `cashflow_volatility` = LOW support confidence; `missed_payments_12m` > 0 lowers it.

## Timeline
`months_to_target` from assess_savings, or "ready now" if gap is 0 and qualifies is true.

## Product fit (options only)
BMO mortgage pre-approval; FHSA top-up if `fhsa_room_remaining` > 0; RRSP Home Buyers' Plan withdrawal.

## Why not yet
- Savings short: card with months to target, action "keep saving, revisit at target".
- Savings sufficient but `qualifies` is false (GDS/TDS over limit): this is the most useful card of all. Say the client is ready on savings but not on affordability at the target price, quote the gds/tds vs limits, and recommend a conversation about a lower target price or debt reduction. Never a pitch.
