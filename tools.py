"""Deterministic tools for the FinWise harness.

Everything here is plain Python. No model calls. The planner agent calls these
as tools; their outputs become the evidence items that briefs must cite.
"""
import json
import os
import statistics
from datetime import datetime, timezone

import boto3
from strands import tool

SIGNALS_BUCKET = os.environ.get("SIGNALS_BUCKET")
MEMORY_ID = os.environ.get("MEMORY_ID")
LOCAL_DATA = os.path.join(os.path.dirname(__file__), "data", "sample_clients.json")

# Canadian qualification assumptions (demo values; make configurable in prod)
STRESS_TEST_FLOOR = 5.25
STRESS_TEST_BUFFER = 2.0
CONTRACT_RATE = 4.6
GDS_LIMIT = 0.39
TDS_LIMIT = 0.44
AMORTIZATION_YEARS = 25
FHSA_LIFETIME_LIMIT = 40000
HBP_LIMIT = 60000


# ---------- data access ----------

def load_client(client_id: str) -> dict:
    """Reads a client record from S3 if configured, else from the local sample file."""
    if SIGNALS_BUCKET:
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=SIGNALS_BUCKET, Key=f"clients/{client_id}.json")
        return json.loads(obj["Body"].read())
    with open(LOCAL_DATA) as f:
        return json.load(f)[client_id]


# ---------- signal engine ----------

def compute_signals(c: dict) -> dict:
    """Derives the signals the agents reason over. Every value here is citable evidence."""
    surplus = c["monthly_surplus_last6"]
    fhsa = c["fhsa_contrib_last6"]
    out = c["outbound_transfers_last6"]
    tel = c["product_telemetry"]
    m = c.get("mortgage")

    signals = {
        "cashflow_mean_surplus": round(statistics.mean(surplus)),
        "cashflow_stdev": round(statistics.pstdev(surplus)),
        "cashflow_negative_months": sum(1 for s in surplus if s < 0),
        "fhsa_monthly_velocity": round(statistics.mean(fhsa)),
        "fhsa_room_remaining": max(0, FHSA_LIFETIME_LIMIT - c["fhsa_balance"]),
        "hbp_eligible": min(c["rrsp_balance"], HBP_LIMIT),
        "down_payment_available": c["fhsa_balance"] + min(c["rrsp_balance"], HBP_LIMIT) + c["liquid_savings"],
        "calculator_uses_90d": tel["mortgage_calculator_uses_90d"],
        "preapproval_started": tel["preapproval_started"],
        "heloc_inquiries_90d": tel["heloc_inquiries_90d"],
        "outbound_total_6m": sum(out),
        "outbound_months": sum(1 for o in out if o > 0),
        "last_contact_days_ago": c["last_contact_days_ago"],
        "has_mortgage": m is not None,
    }
    if m:
        signals.update({
            "renewal_in_months": m["renewal_in_months"],
            "mortgage_balance": m["balance"],
            "current_rate": m["rate"],
            "rate_gap_vs_market": round(CONTRACT_RATE - m["rate"], 2),
            "penalty_estimate": m.get("penalty_estimate", 0),
        })
    return signals


# ---------- calculators exposed as tools ----------

@tool
def assess_savings(client_id: str, target_price: float = 900000.0) -> dict:
    """Checks whether the client's FHSA, HBP-eligible RRSP and liquid savings cover a
    down payment for the target price, and how many months until they do."""
    c = load_client(client_id)
    s = compute_signals(c)
    needed = target_price * 0.20 if target_price > 1_000_000 else min(
        0.05 * 500000 + 0.10 * max(0, target_price - 500000), target_price * 0.20)
    available = s["down_payment_available"]
    gap = max(0, needed - available)
    monthly_add = s["fhsa_monthly_velocity"] + max(0, s["cashflow_mean_surplus"]) * 0.5
    months_to_target = 0 if gap == 0 else (round(gap / monthly_add) if monthly_add > 0 else None)
    return {
        "target_price": target_price,
        "down_payment_needed": round(needed),
        "down_payment_available": round(available),
        "gap": round(gap),
        "months_to_target": months_to_target,
        "sufficient": gap == 0,
    }


@tool
def check_qualification(client_id: str, target_price: float = 900000.0) -> dict:
    """Rule-based mortgage qualification using GDS/TDS limits and the stress-test rate.
    This is deterministic on purpose: qualification is not a model judgment."""
    c = load_client(client_id)
    s = compute_signals(c)
    principal = target_price - s["down_payment_available"]
    qual_rate = max(STRESS_TEST_FLOOR, CONTRACT_RATE + STRESS_TEST_BUFFER) / 100 / 12
    n = AMORTIZATION_YEARS * 12
    payment = principal * qual_rate / (1 - (1 + qual_rate) ** -n) if principal > 0 else 0
    housing = payment + 350 + 150  # taxes + heat placeholders
    gross_monthly = c["annual_income"] / 12
    gds = housing / gross_monthly
    tds = (housing + c["monthly_debt_payments"]) / gross_monthly
    return {
        "principal": round(principal),
        "stress_test_payment": round(payment),
        "gds": round(gds, 3),
        "tds": round(tds, 3),
        "gds_limit": GDS_LIMIT,
        "tds_limit": TDS_LIMIT,
        "qualifies": gds <= GDS_LIMIT and tds <= TDS_LIMIT,
    }


@tool
def get_signals(client_id: str) -> dict:
    """Returns the derived signal bundle and relationship context for a client."""
    c = load_client(client_id)
    return {
        "client_name": c["name"],
        "risk_profile": c["risk_profile"],
        "tenure_years": c["tenure_years"],
        "signals": compute_signals(c),
    }


# ---------- memory (advisor outcomes) ----------

def get_outcomes(client_id: str) -> list:
    """Reads prior advisor outcomes. Uses AgentCore Memory when MEMORY_ID is set,
    otherwise a local JSON file so the demo works without it."""
    if MEMORY_ID:
        try:
            from bedrock_agentcore.memory import MemoryClient
            mc = MemoryClient()
            events = mc.list_events(memory_id=MEMORY_ID, actor_id=client_id,
                                    session_id="outcomes", max_results=20)
            return [json.loads(e["payload"][0]["conversational"]["content"]["text"])
                    for e in events if e.get("payload")]
        except Exception as exc:  # keep the harness running if memory is unavailable
            return [{"memory_error": str(exc)}]
    path = f"/tmp/outcomes_{client_id}.json"
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


@tool
def record_outcome(client_id: str, card_id: str, action: str, note: str = "") -> dict:
    """Advisor-gated write. Records what the advisor did with a card so the planner
    can suppress or re-surface it next run. Valid actions: contacted, not_now,
    wrong_opportunity, wrong_timing, already_handled, converted."""
    event = {"client_id": client_id, "card_id": card_id, "action": action,
             "note": note, "ts": datetime.now(timezone.utc).isoformat()}
    if MEMORY_ID:
        from bedrock_agentcore.memory import MemoryClient
        MemoryClient().create_event(memory_id=MEMORY_ID, actor_id=client_id,
                                    session_id="outcomes",
                                    messages=[(json.dumps(event), "USER")])
    else:
        path = f"/tmp/outcomes_{client_id}.json"
        existing = get_outcomes(client_id)
        existing.append(event)
        with open(path, "w") as f:
            json.dump(existing, f)
    return {"recorded": True, **event}
