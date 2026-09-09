"""FinWise tools Lambda for AgentCore Gateway.

One function, four tools. Gateway passes the tool name in the Lambda client context
as bedrockAgentCoreToolName (format: <target>___<tool>). The event is the tool input.

Env: SIGNALS_BUCKET (required), MEMORY_ID (optional; falls back to S3 outcomes/ prefix)
"""
import json
import os
import statistics
from datetime import datetime, timezone

import boto3

BUCKET = os.environ["SIGNALS_BUCKET"]
MEMORY_ID = os.environ.get("MEMORY_ID")
s3 = boto3.client("s3")

STRESS_TEST_FLOOR, STRESS_TEST_BUFFER, CONTRACT_RATE = 5.25, 2.0, 4.6
GDS_LIMIT, TDS_LIMIT, AMORT_YEARS = 0.39, 0.44, 25
FHSA_LIFETIME_LIMIT, HBP_LIMIT = 40000, 60000


def load_client(cid):
    return json.loads(s3.get_object(Bucket=BUCKET, Key=f"clients/{cid}.json")["Body"].read())


def compute_signals(c):
    surplus, fhsa, out, tel, m = (c["monthly_surplus_last6"], c["fhsa_contrib_last6"],
                                  c["outbound_transfers_last6"], c["product_telemetry"], c.get("mortgage"))
    s = {
        "cashflow_mean_surplus": round(statistics.mean(surplus)),
        "cashflow_stdev": round(statistics.pstdev(surplus)),
        "cashflow_negative_months": sum(1 for x in surplus if x < 0),
        "fhsa_monthly_velocity": round(statistics.mean(fhsa)),
        "fhsa_room_remaining": max(0, FHSA_LIFETIME_LIMIT - c["fhsa_balance"]),
        "hbp_eligible": min(c["rrsp_balance"], HBP_LIMIT),
        "down_payment_available": c["fhsa_balance"] + min(c["rrsp_balance"], HBP_LIMIT) + c["liquid_savings"],
        "calculator_uses_90d": tel["mortgage_calculator_uses_90d"],
        "preapproval_started": tel["preapproval_started"],
        "heloc_inquiries_90d": tel["heloc_inquiries_90d"],
        "outbound_total_6m": sum(out),
        "outbound_months": sum(1 for x in out if x > 0),
        "last_contact_days_ago": c["last_contact_days_ago"],
        "has_mortgage": m is not None,
    }
    if m:
        s.update({"renewal_in_months": m["renewal_in_months"], "mortgage_balance": m["balance"],
                  "current_rate": m["rate"], "rate_gap_vs_market": round(CONTRACT_RATE - m["rate"], 2),
                  "penalty_estimate": m.get("penalty_estimate", 0)})
    return s


# ---------- tools ----------

def get_signals(client_id, **_):
    c = load_client(client_id)
    return {"client_id": client_id, "client_name": c["name"], "advisor_id": c["advisor_id"],
            "age": c["age"], "risk_profile": c["risk_profile"], "tenure_years": c["tenure_years"],
            "signals": compute_signals(c), "prior_outcomes": get_outcomes(client_id)}


def list_clients(advisor_id, **_):
    ids = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix="clients/"):
        for o in page.get("Contents", []):
            cid = o["Key"].split("/")[-1].removesuffix(".json")
            if load_client(cid).get("advisor_id") == advisor_id:
                ids.append(cid)
    return {"advisor_id": advisor_id, "client_ids": ids}


def assess_savings(client_id, target_price=900000.0, **_):
    s = compute_signals(load_client(client_id))
    needed = target_price * 0.20 if target_price > 1_000_000 else min(
        0.05 * 500000 + 0.10 * max(0, target_price - 500000), target_price * 0.20)
    available, gap = s["down_payment_available"], 0
    gap = max(0, needed - available)
    monthly_add = s["fhsa_monthly_velocity"] + max(0, s["cashflow_mean_surplus"]) * 0.5
    months = 0 if gap == 0 else (round(gap / monthly_add) if monthly_add > 0 else None)
    return {"target_price": target_price, "down_payment_needed": round(needed),
            "down_payment_available": round(available), "gap": round(gap),
            "months_to_target": months, "sufficient": gap == 0}


def check_qualification(client_id, target_price=900000.0, **_):
    c = load_client(client_id); s = compute_signals(c)
    principal = target_price - s["down_payment_available"]
    r = max(STRESS_TEST_FLOOR, CONTRACT_RATE + STRESS_TEST_BUFFER) / 100 / 12
    n = AMORT_YEARS * 12
    payment = principal * r / (1 - (1 + r) ** -n) if principal > 0 else 0
    housing = payment + 500
    gm = c["annual_income"] / 12
    gds, tds = housing / gm, (housing + c["monthly_debt_payments"]) / gm
    return {"principal": round(principal), "stress_test_payment": round(payment),
            "gds": round(gds, 3), "tds": round(tds, 3), "gds_limit": GDS_LIMIT, "tds_limit": TDS_LIMIT,
            "qualifies": gds <= GDS_LIMIT and tds <= TDS_LIMIT, "rule_based": True}


def get_outcomes(client_id):
    try:
        return json.loads(s3.get_object(Bucket=BUCKET, Key=f"outcomes/{client_id}.json")["Body"].read())
    except s3.exceptions.NoSuchKey:
        return []


def record_outcome(client_id, card_id, action, note="", **_):
    ev = {"client_id": client_id, "card_id": card_id, "action": action, "note": note,
          "ts": datetime.now(timezone.utc).isoformat()}
    events = get_outcomes(client_id) + [ev]
    s3.put_object(Bucket=BUCKET, Key=f"outcomes/{client_id}.json", Body=json.dumps(events).encode())
    return {"recorded": True, **ev}


TOOLS = {"get_signals": get_signals, "list_clients": list_clients, "assess_savings": assess_savings,
         "check_qualification": check_qualification, "record_outcome": record_outcome}


def lambda_handler(event, context):
    name = None
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
