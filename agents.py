"""FinWise agents: planner (entrypoint), wellness (can veto), briefing (cited narrative).

Three model-backed agents, everything else deterministic. Planner and wellness run
in parallel; briefing runs last on the planner's structured output only.
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from strands import Agent
from strands.models import BedrockModel

from tools import assess_savings, check_qualification, get_signals, get_outcomes

MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-20250514")
FAST_MODEL_ID = os.environ.get("FAST_MODEL_ID", MODEL_ID)


def _json_from(text: str) -> dict:
    """Pulls the first JSON object out of a model reply."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"No JSON in model output: {text[:200]}")
    return json.loads(m.group(0))


# ---------- Wellness agent (financial risk + suitability, can veto) ----------

WELLNESS_PROMPT = """You are the Wellness agent inside a bank advisor tool. You assess
financial risk and suitability for a premium client. You never speak to the client.
You are allowed to veto or downgrade an opportunity.

Given the client's signals, return ONLY a JSON object:
{
  "risk_level": "low" | "medium" | "high",
  "verdict": "proceed" | "downgrade" | "veto",
  "reasons": [ {"claim": "...", "evidence_key": "<signal name>", "value": <value>} ],
  "advisor_note": "one sentence the advisor should keep in mind"
}
Rules: negative cash-flow months or high cash-flow variance relative to surplus are
material risk. A veto means: do not recommend the opportunity now. Every reason must
point to a real signal key you were given."""


def run_wellness(signal_bundle: dict) -> dict:
    agent = Agent(model=BedrockModel(model_id=FAST_MODEL_ID), system_prompt=WELLNESS_PROMPT)
    reply = agent(f"Client signals:\n{json.dumps(signal_bundle, indent=2)}")
    return _json_from(str(reply))


# ---------- Planner agent (orchestrator) ----------

PLANNER_PROMPT = """You are the Planner agent inside a bank advisor tool. You decide which
life-event opportunities a premium client is approaching and what the advisor should do.

Opportunities you may emit: home_purchase, renewal_refi, liquidity, attrition.
Use the tools to get evidence. Call get_signals first. For home_purchase you must
call assess_savings and check_qualification; qualification is rule-based and you
must not override it. Consider prior advisor outcomes: if the advisor marked a card
not_now or wrong_timing recently, only re-surface it if a signal has materially changed,
and say what changed.

Return ONLY a JSON object:
{
  "cards": [
    {
      "card_id": "<client_id>-<opportunity>",
      "opportunity": "...",
      "confidence": 0.0-1.0,
      "timeline": "e.g. 'renewal in 3 months' or '6-9 months to down payment'",
      "urgency_rank": 1,
      "key_signal": "one short phrase",
      "recommended_action": "one sentence for the advisor",
      "product_fit": ["at most two BMO product areas, or empty"],
      "evidence": [ {"claim": "...", "tool": "<tool name>", "key": "<field>", "value": <value>} ]
    }
  ],
  "rationale": "two sentences on how you ranked"
}
Every card needs at least three evidence items drawn from tool outputs. Do not invent
values. Urgency_rank 1 is most urgent. If nothing clears 0.5 confidence, return no cards."""


def run_planner(client_id: str) -> dict:
    outcomes = get_outcomes(client_id)
    agent = Agent(model=BedrockModel(model_id=MODEL_ID), system_prompt=PLANNER_PROMPT,
                  tools=[get_signals, assess_savings, check_qualification])
    reply = agent(f"client_id: {client_id}\nPrior advisor outcomes: {json.dumps(outcomes)}")
    return _json_from(str(reply))


# ---------- Briefing agent (cited narrative + grounding validator) ----------

BRIEFING_PROMPT = """You are the Briefing agent. Write a short readiness brief for a bank
advisor about one client card. Use ONLY the evidence items you are given. Every sentence
that states a fact must end with a citation in the form [E1], [E2] matching the evidence
list order. Do not add facts, products, or numbers that are not in the evidence.

Structure, in plain prose, no headers:
1. One-line summary of the opportunity and confidence.
2. Two or three supporting sentences, each cited.
3. One sentence on timing ("why now" or "why not yet").
4. One suggested opening line for the advisor, clearly marked as a suggestion.
5. If a wellness note is present, one sentence reflecting it."""


def _ground(brief: str, n_evidence: int) -> dict:
    """Deterministic grounding check: factual sentences must carry a valid citation."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", brief) if s.strip()]
    uncited, bad_refs = [], []
    for s in sentences:
        refs = [int(x) for x in re.findall(r"\[E(\d+)\]", s)]
        if not refs and not s.lower().startswith(("suggested", "you could open")):
            uncited.append(s)
        bad_refs += [r for r in refs if r < 1 or r > n_evidence]
    return {"passed": not uncited and not bad_refs, "uncited": uncited, "bad_refs": bad_refs}


def run_briefing(card: dict, wellness: dict, retries: int = 1) -> dict:
    evidence = card["evidence"] + [
        {"claim": r["claim"], "key": r["evidence_key"], "value": r["value"]} for r in wellness.get("reasons", [])
    ]
    numbered = "\n".join(f"E{i+1}: {json.dumps(e)}" for i, e in enumerate(evidence))
    agent = Agent(model=BedrockModel(model_id=MODEL_ID), system_prompt=BRIEFING_PROMPT)
    payload = (f"Card: {json.dumps({k: v for k, v in card.items() if k != 'evidence'})}\n"
               f"Wellness verdict: {wellness.get('verdict')} — {wellness.get('advisor_note')}\n"
               f"Evidence:\n{numbered}")
    for attempt in range(retries + 1):
        brief = str(agent(payload)).strip()
        check = _ground(brief, len(evidence))
        if check["passed"]:
            return {"brief": brief, "grounding": check, "evidence": evidence}
        payload += f"\n\nRewrite: these sentences lacked a valid citation: {check['uncited']}"
    return {"brief": brief, "grounding": check, "evidence": evidence, "warning": "grounding failed"}


# ---------- Harness run ----------

def apply_wellness(card: dict, wellness: dict) -> dict:
    """Wellness can veto or downgrade. Planner output is adjusted, not discarded."""
    v = wellness.get("verdict")
    if v == "veto":
        card["confidence"] = round(min(card["confidence"], 0.35), 2)
        card["recommended_action"] = ("Hold outreach on this opportunity; check in on cash-flow "
                                      "stability first. " + wellness.get("advisor_note", ""))
        card["wellness_override"] = "veto"
    elif v == "downgrade":
        card["confidence"] = round(card["confidence"] * 0.7, 2)
        card["wellness_override"] = "downgrade"
    else:
        card["wellness_override"] = "none"
    return card


def run_harness(client_id: str, advisor_id: str | None = None, with_briefs: bool = True) -> dict:
    with ThreadPoolExecutor(max_workers=2) as ex:
        planner_f = ex.submit(run_planner, client_id)
        wellness_f = ex.submit(lambda: run_wellness(get_signals(client_id)))
        plan, wellness = planner_f.result(), wellness_f.result()

    cards = [apply_wellness(c, wellness) for c in plan.get("cards", [])]
    cards.sort(key=lambda c: (c.get("urgency_rank", 99), -c.get("confidence", 0)))
    if with_briefs:
        for c in cards:
            c["brief"] = run_briefing(c, wellness)
    return {"client_id": client_id, "advisor_id": advisor_id, "cards": cards,
            "wellness": wellness, "planner_rationale": plan.get("rationale")}
