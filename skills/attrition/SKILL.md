---
name: attrition
description: Detect relationship attrition risk from sustained outbound transfers and cold contact. Use when outbound_months >= 2 or last_contact_days_ago > 90. This is a retention skill, not a sales skill.
---
# Attrition risk skill (v1.0, default urgency: high)

Emit opportunity `attrition` when the rules below fire.

## Signals to weigh
- `outbound_total_6m` > 0 and `outbound_months` >= 2 = sustained money leaving to another institution.
- `last_contact_days_ago` > 90 = relationship going cold.
- Attrition combined with `renewal_in_months` <= 6 is the highest urgency in the whole harness (urgency_rank 1).

## Timeline
"now" if outbound transfers are sustained; otherwise 30-60 days.

## Product fit
None. The recommended action is a relationship check-in, never a product push.

## Confidence
Confidence expresses the risk of the client leaving, not the size of any opportunity.
