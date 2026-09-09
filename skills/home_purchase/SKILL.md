---
name: home_purchase
description: Detect readiness to buy a home (first purchase or next property) from FHSA, RRSP, cash flow and intent signals. Use when fhsa_monthly_velocity > 0 or preapproval_started is true or calculator_uses_90d >= 2.
---
# Home purchase skill (v1.0, default urgency: medium)

Emit opportunity `home_purchase` when the rules below fire. You MUST call `assess_savings` and `check_qualification` before emitting this card.

## Signals to weigh
- `fhsa_monthly_velocity` > 0 across the six months = active saving toward a home.
- `preapproval_started` true or `calculator_uses_90d` >= 2 = explicit intent.
- `assess_savings.gap` and `months_to_target` set readiness and timeline.
- `check_qualification.qualifies` must be true before confidence can exceed 0.7. This is rule-based; do not override it.
- `current_rent` close to `stress_test_payment` shows affordability already demonstrated.

## Timeline
`months_to_target` from assess_savings, or "ready now" if gap is 0.

## Product fit (options only)
BMO mortgage pre-approval; FHSA top-up if `fhsa_room_remaining` > 0; RRSP Home Buyers' Plan withdrawal.

## Why not yet
If savings are short, produce a card with the months to target and a recommended action of "keep saving, revisit at target", not a pitch.
