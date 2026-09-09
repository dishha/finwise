---
name: renewal_refi
description: Detect an upcoming mortgage renewal or a refinance / equity-access moment. Use only when signals.has_mortgage is true.
---
# Renewal and refinance skill (v1.1, default urgency: high)

Emit opportunity `renewal_refi` only if `has_mortgage` is true. If false, this skill does not fire.

## Signals to weigh
- `renewal_in_months` <= 6 is a strong renewal trigger; <= 3 is urgent (urgency_rank 1).
- `rate_gap_vs_market` > 0 means the client's rate is below market: expect payment shock at renewal. Say so.
- `heloc_inquiries_90d` > 0 or `calculator_viewed` true together with `has_mortgage` = equity-access intent.
- `penalty_estimate` vs benefit: if breaking the term costs more than it saves, produce a "why not yet" card that says wait for renewal.
- `credit_inquiries_6m` >= 2 or `last_contact_days_ago` > 90 alongside a renewal = retention risk. Raise urgency.

## Timeline
State the renewal window in months.

## Product fit (options only; the advisor decides)
BMO mortgage renewal; BMO Homeowner ReadiLine (HELOC) if equity intent is present.

## Never
Never recommend breaking a term to refinance without showing penalty versus benefit.
