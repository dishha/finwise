---
name: wellness
description: Financial risk and suitability check that can veto or downgrade any opportunity. ALWAYS apply after opportunity detection and before writing cards.
---
# Wellness and suitability skill (v1.0)

Run this after opportunity skills, before finalizing cards. It protects the client and the advisor.

## Assess
- `cashflow_negative_months` >= 2 or `cashflow_stdev` large relative to `cashflow_mean_surplus` = material risk.
- `monthly_debt_payments` high relative to income = suitability concern for new credit.
- `risk_profile` conservative with a growth-type product fit = mismatch.

## Verdict
- `proceed`: no material risk.
- `downgrade`: multiply the card's confidence by 0.7 and add a wellness note.
- `veto`: cap confidence at 0.35 and replace recommended_action with "Hold outreach on this opportunity; check in on cash-flow stability first."

## Rules
Every reason must point to a real signal key and value. Record the verdict on each card as `wellness_override`. This is the consumer-protection step: the advisor sees why an opportunity was held back.
