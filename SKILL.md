---
name: renewal_refi
description: Detect an upcoming mortgage renewal or a refinance / equity-access moment for a BMO premium client. Use when signals show has_mortgage true.
---
# Renewal and refinance skill (v1.0, default urgency: high)

Emit opportunity `renewal_refi` when the rules below fire.

## Signals to weigh
- `renewal_in_months` <= 6 is a strong renewal trigger; <= 3 is urgent (urgency_rank 1).
- `rate_gap_vs_market` > 0 means the client's rate is below market: expect payment shock at renewal. Say so.
- `heloc_inquiries_90d` > 0 or `calculator_uses_90d` > 0 with `has_mortgage` = equity-access intent.
- `penalty_estimate` vs benefit: if breaking the term costs more than it saves, produce a "why not yet" card that says wait for renewal.
- `outbound_total_6m` > 0 together with an approaching renewal = retention risk. Raise urgency.

## Timeline
State the renewal window in months, e.g. "renewal in 3 months".

## Product fit (options only; the advisor decides)
BMO mortgage renewal; BMO Homeowner ReadiLine (HELOC) if equity intent is present.

## Never
Never recommend breaking a term to refinance without showing penalty versus benefit.
