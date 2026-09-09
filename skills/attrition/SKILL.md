---
name: attrition
description: Detect relationship attrition risk from cold contact, low engagement and external credit shopping. Use when last_contact_days_ago > 90, or credit_inquiries_6m >= 2, or email_open_rate < 0.3. This is a retention skill, not a sales skill.
---
# Attrition risk skill (v1.1, default urgency: high)

Emit opportunity `attrition` when the rules below fire.

## Signals to weigh
- `last_contact_days_ago` > 90 = relationship going cold; > 180 = strong.
- `credit_inquiries_6m` >= 2 = the client may be shopping for credit elsewhere.
- `email_open_rate` < 0.3 = disengagement from the advisor channel.
- `do_not_contact` = true: emit the card for advisor awareness but set recommended_action to "respect do-not-contact; no outreach" and product_fit to none.
- Attrition combined with `renewal_in_months` <= 6 is the highest urgency in the whole harness (urgency_rank 1).

## Timeline
"now" if two or more signals fire; otherwise 30-60 days.

## Product fit
None. The recommended action is a relationship check-in through `preferred_channel`, never a product push.

## Confidence
Confidence expresses the risk of the client leaving, not the size of any opportunity.
