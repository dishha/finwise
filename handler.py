"""FinWise tools Lambda for AgentCore Gateway — matches the finwise-mvp customer JSON.

Gateway passes the tool name in the Lambda client context as bedrockAgentCoreToolName
(<target>___<tool>). The event is the tool input. For direct testing, pass {"tool": "..."}.

Env: SIGNALS_BUCKET (required)
     CLIENTS_PREFIX (optional, default "customers/")   -> customers/C-2001.json
     OUTCOMES_PREFIX (optional, default "outcomes/")
"""
import json
import os
from datetime import datetime, timezone

import boto3

BUCKET = os.environ["SIGNALS_BUCKET"]
CLIENTS_PREFIX = os.environ.get("CLIENTS_PREFIX", "clients/")
OUTCOMES_PREFIX = os.environ.get("OUTCOMES_PREFIX", "outcomes/")
s3 = boto3.client("s3")

STRESS_TEST_FLOOR, STRESS_TEST_BUFFER, CONTRACT_RATE = 5.25, 2.0, 4.6
GDS_LIMIT, TDS_LIMIT, AMORT_YEARS = 0.39, 0.44, 25
FHSA_LIFETIME_LIMIT, HBP_LIMIT = 40000, 60000


# ---------- data ----------

def load_client(cid):
    return json.loads(s3.get_object(Bucket=BUCKET, Key=f"{CLIENTS_PREFIX}{cid}.json")["Body"].read())


def _telemetry(c):
    t = {"calculator_viewed": False, "calculator_date": None, "preapproval_status": None,
         "heloc_inquiries_90d": 0}
    for item in c.get("product_telemetry") or []:
        p = item.get("product")
        if p == "mortgage_calculator":
            t["calculator_viewed"] = item.get("status") in ("VIEWED", "USED", "COMPLETED")
            t["calculator_date"] = item.get("date")
        elif p == "pre_approval":
            t["preapproval_status"] = item.get("status")
        elif p == "heloc_inquiries":
            t["heloc_inquiries_90d"] = item.get("count", 0)
    return t


def _monthly_debt(c):
    return sum((d.get("monthlyPayment") or d.get("minPayment") or 0) for d in c.get("debts") or [])


def _account_total(c, types):
    return sum(a.get("balance", 0) for a in c.get("accounts") or [] if a.get("type") in types)


def _mortgage(c):
    m = c.get("mortgage")
    if not m:
        return None
    renew = m.get("renewal_in_months")
    if renew is None and m.get("renewalDate"):
        try:
            renew = max(0, round((datetime.fromisoformat(m["renewalDate"]) - datetime.now()).days / 30))
        except ValueError:
            renew = None
    return {"balance": m.get("balance"), "rate": m.get("rate"), "renewal_in_months": renew,
            "penalty_estimate": m.get("penalty_estimate", m.get("penaltyEstimate", 0))}


def compute_signals(c):
    inc = c.get("income") or {}
    cf = c.get("cashflow") or {}
    cr = c.get("credit") or {}
    hs = c.get("housing") or {}
    eng = c.get("engagement") or {}
    tel = _telemetry(c)
    m = _mortgage(c)
    fhsa_bal = c.get("fhsa_balance", 0)
    rrsp = c.get("rrsp_balance", 0)
    liquid = c.get("liquidity_savings", _account_total(c, {"CHEQUING", "SAVINGS", "TFSA"}))
    home_goal = next((g for g in c.get("goals") or [] if g.get("type") == "HOME_OWNERSHIP"), None)

    s = {
        "monthly_net_income": cf.get("monthlyNetIncome"),
        "monthly_surplus": cf.get("surplus"),
        "cashflow_volatility": cf.get("volatility"),
        "income_stability": inc.get("stability"),
        "income_tenure_months": inc.get("tenureMonths"),
        "fhsa_balance": fhsa_bal,
        "fhsa_contribution_last_6m": c.get("fhsa_contribution_last_6m", 0),
        "fhsa_monthly_velocity": round(c.get("fhsa_contribution_last_6m", 0) / 6),
        "fhsa_room_remaining": max(0, FHSA_LIFETIME_LIMIT - fhsa_bal),
        "hbp_eligible": min(rrsp, HBP_LIMIT),
        "liquid_savings": liquid,
        "down_payment_available": fhsa_bal + min(rrsp, HBP_LIMIT) + liquid,
        "savings_monthly_contribution": sum(a.get("monthlyContribution", 0) for a in c.get("accounts") or []),
        "housing_intent": hs.get("intent"),
        "target_price": hs.get("targetPrice"),
        "target_down_payment_pct": hs.get("targetDownPaymentPct"),
        "home_goal_status": home_goal.get("status") if home_goal else None,
        "home_goal_target_date": home_goal.get("targetDate") if home_goal else None,
        "calculator_viewed": tel["calculator_viewed"],
        "preapproval_status": tel["preapproval_status"],
        "heloc_inquiries_90d": tel["heloc_inquiries_90d"],
        "credit_score": cr.get("score"),
        "credit_utilization": cr.get("utilization"),
        "missed_payments_12m": cr.get("missedPayments12m"),
        "credit_inquiries_6m": cr.get("inquiries6m"),
        "monthly_debt_payments": _monthly_debt(c),
        "last_contact_days_ago": c.get("last_contact_days_ago", eng.get("lastAdvisorContactDays")),
        "preferred_channel": eng.get("preferredChannel"),
        "do_not_contact": eng.get("doNotContact", False),
        "email_open_rate": eng.get("openRateEmail"),
        "rewards_tier": (c.get("rewards") or {}).get("blueRewardsTier"),
        "has_mortgage": m is not None,
    }
    if m:
        s.update({"mortgage_balance": m["balance"], "current_rate": m["rate"],
                  "renewal_in_months": m["renewal_in_months"],
                  "rate_gap_vs_market": round(CONTRACT_RATE - m["rate"], 2) if m["rate"] is not None else None,
                  "penalty_estimate": m["penalty_estimate"]})
    return s


# ---------- tools ----------

def get_signals(client_id, **_):
    c = load_client(client_id)
    return {"client_id": client_id, "client_name": c.get("name", client_id),
            "advisor_id": c.get("advisor_id"), "age": c.get("age"), "segment": c.get("segment"),
            "province": c.get("province"), "tenure_years": c.get("tenure_years"),
            "signals": compute_signals(c), "prior_outcomes": get_outcomes(client_id)}


def list_clients(advisor_id, **_):
    ids = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=CLIENTS_PREFIX):
        for o in page.get("Contents", []):
            key = o["Key"]
            if not key.endswith(".json"):
                continue
            cid = key.split("/")[-1].removesuffix(".json")
            if load_client(cid).get("advisor_id") == advisor_id:
                ids.append(cid)
    return {"advisor_id": advisor_id, "client_ids": ids}


def _target(c, target_price):
    hs = c.get("housing") or {}
    return (target_price or hs.get("targetPrice") or 900000), hs.get("targetDownPaymentPct")


def assess_savings(client_id, target_price=None, **_):
    c = load_client(client_id)
    s = compute_signals(c)
    price, pct = _target(c, target_price)
    if pct:
        needed = price * pct
    elif price > 1_000_000:
        needed = price * 0.20
    else:
        needed = 0.05 * min(price, 500000) + 0.10 * max(0, price - 500000)
    available = s["down_payment_available"]
    gap = max(0, needed - available)
    monthly_add = s["fhsa_monthly_velocity"] + s["savings_monthly_contribution"] + max(0, s["monthly_surplus"] or 0) * 0.5
    months = 0 if gap == 0 else (round(gap / monthly_add) if monthly_add > 0 else None)
    return {"target_price": price, "down_payment_pct_used": pct, "down_payment_needed": round(needed),
            "down_payment_available": round(available), "gap": round(gap),
            "months_to_target": months, "sufficient": gap == 0}


def check_qualification(client_id, target_price=None, **_):
    c = load_client(client_id)
    s = compute_signals(c)
    price, _ = _target(c, target_price)
    principal = max(0, price - s["down_payment_available"])
    qual_rate = max(STRESS_TEST_FLOOR, CONTRACT_RATE + STRESS_TEST_BUFFER)
    r = qual_rate / 100 / 12
    n = AMORT_YEARS * 12
    payment = principal * r / (1 - (1 + r) ** -n) if principal > 0 else 0
    housing = payment + 500
    gross_monthly = ((c.get("income") or {}).get("grossAnnual") or 1) / 12
    gds = housing / gross_monthly
    tds = (housing + s["monthly_debt_payments"]) / gross_monthly
    return {"principal": round(principal), "stress_test_rate": qual_rate,
            "stress_test_payment": round(payment), "gds": round(gds, 3), "tds": round(tds, 3),
            "gds_limit": GDS_LIMIT, "tds_limit": TDS_LIMIT,
            "credit_score": s["credit_score"], "missed_payments_12m": s["missed_payments_12m"],
            "qualifies": gds <= GDS_LIMIT and tds <= TDS_LIMIT and (s["credit_score"] or 0) >= 650,
            "rule_based": True}


def get_outcomes(client_id):
    try:
        return json.loads(s3.get_object(Bucket=BUCKET, Key=f"{OUTCOMES_PREFIX}{client_id}.json")["Body"].read())
    except s3.exceptions.NoSuchKey:
        return []


def record_outcome(client_id, card_id, action, note="", **_):
    ev = {"client_id": client_id, "card_id": card_id, "action": action, "note": note,
          "ts": datetime.now(timezone.utc).isoformat()}
    events = get_outcomes(client_id) + [ev]
    s3.put_object(Bucket=BUCKET, Key=f"{OUTCOMES_PREFIX}{client_id}.json", Body=json.dumps(events).encode())
    return {"recorded": True, **ev}


TOOLS = {"get_signals": get_signals, "list_clients": list_clients, "assess_savings": assess_savings,
         "check_qualification": check_qualification, "record_outcome": record_outcome}


def lambda_handler(event, context):
    name = ""
    try:
        name = context.client_context.custom.get("bedrockAgentCoreToolName", "")
    except Exception:
        pass
    name = (name or event.get("tool", "")).split("___")[-1]
    if name not in TOOLS:
        return {"error": f"unknown tool '{name}'", "available": list(TOOLS)}
    args = {k: v for k, v in event.items() if k != "tool"}
    try:
        return TOOLS[name](**args)
    except Exception as exc:
        return {"error": str(exc), "tool": name, "partial_evidence": True}
