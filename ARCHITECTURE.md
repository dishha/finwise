# FinWise Architecture

## Overview

FinWise is an agentic readiness harness for bank advisors. It processes client financial signals through three parallel Claude agents (planner, wellness, briefing) to detect life-event opportunities (home purchase, renewal, liquidity, attrition) and produces evidence-backed readiness cards that advisors review before outreach.

**Three Claude Agents + Deterministic Tools = Evidence-Driven Decisions**

---

## Core Agentic Flow

```
Request (client_id)
    ↓
Load client data + prior outcomes
    ↓
┌─────────────────────────────────┐
│  Parallel Execution (ThreadPool)│
├──────────┬──────────────────────┤
│ Planner  │ Wellness             │
│ • calls  │ • gets signal bundle │
│   tools  │ • assesses risk      │
│ • emits  │ • returns verdict    │
│   cards  │   (proceed|down|veto)│
└──────────┴──────────────────────┘
    ↓
Merge results
    ↓
Apply wellness override
• Veto: cap confidence ≤ 0.35
• Downgrade: confidence × 0.7
    ↓
Sort by urgency_rank, then confidence
    ↓
For each card: Briefing agent writes cited narrative
• [E1], [E2], etc. reference evidence items
• Grounding validator ensures every fact is cited
• Retry up to 2x if grounding fails
    ↓
Return JSON cards for advisor review
```

---

## AWS Architecture & Deployment

FinWise runs on **AWS using AgentCore**, a fully managed agentic platform. The architecture separates concerns across four layers: data, compute, application, and model.

### Deployment Layers

```
┌─────────────────────────────────────────────┐
│ Data Layer: Amazon S3                       │
│ • clients/ → client signals (JSON)          │
│ • skills/*/ → skill definitions (SKILL.md)  │
│ • Fallback resilience built in              │
└─────────────────────────────────────────────┘
                    ↕ (GetObject, PutObject)
┌──────────────────┬──────────────────────────┐
│ AWS Lambda       │ AgentCore Gateway        │
│ • handler.py     │ • Tool Router            │
│ • Python 3.13    │ • gateway_tools.json     │
│ • 30s timeout    │ • 5 tools listed         │
│ • S3 I/O         │                          │
└──────────────────┴──────────────────────────┘
                    ↕ (Tool calls & results)
┌─────────────────────────────────────────────┐
│ AgentCore Harness (Application)             │
│ • Instructions: harness_instructions.md     │
│ • Tools Config: Routes to Gateway           │
│ • Skills Manager: Progressive S3 loading    │
│ • Memory: Tracks outcomes                   │
└─────────────────────────────────────────────┘
                    ↕ (Prompts & model output)
┌─────────────────────────────────────────────┐
│ Amazon Bedrock (Model)                      │
│ • Claude Sonnet 4.6                         │
│ • Region: ca-central-1                      │
│ • Inference profile ARNs configured         │
└─────────────────────────────────────────────┘
```

### Layer Details

**Data Layer (S3)**
- Stores client signals in `clients/` as JSON files
- Stores skill definitions in `skills/*/SKILL.md` files
- Lambda reads signals; records outcomes on advisor action
- Fallback to local JSON if S3 unavailable

**Compute Layer (Lambda + Gateway)**
- **Lambda** (handler.py): Executes all deterministic tool logic
  - Python 3.13, 30-second timeout
  - IAM permissions: `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`
  - Environment variable: `SIGNALS_BUCKET`
- **Gateway**: Routes tool invocations from Harness to Lambda
  - Uses `gateway_tools.json` schema (defines 5 tools)
  - Returns tool results back to Harness

**Application Layer (AgentCore Harness)**
- Orchestrates the entire agentic flow
- **Instructions** (harness_instructions.md): Defines request flow (list_clients → get_signals → apply skills → apply wellness → generate briefs)
- **Tools Config**: Routes tool calls to Gateway
- **Skills Manager**: Progressively loads SKILL.md files from S3 (metadata upfront, full text on-demand)
- **Memory**: Persists advisor outcomes for next run (or falls back to `/tmp`)
- Max iterations: 20 (enough for full book processing)

**Model Layer (Bedrock)**
- Claude Sonnet 4.6 inference endpoint
- Region: ca-central-1
- Execution role has inference profile ARNs + destination-region model ARNs
- Runs planner, wellness, and briefing agents

### Request Flow Through AWS

1. **Request arrives** → Harness receives `advisor_id` or `client_id`
2. **Harness loads instructions** from its configuration
3. **Harness fetches skills progressively** from S3 (metadata + full text as needed)
4. **Claude makes tool calls** → Harness invokes Gateway with tool name + args
5. **Gateway routes to Lambda** → Lambda executes the tool (gets signals, assesses savings, checks qualification, etc.)
6. **Lambda fetches/writes S3** → Reads client data, writes outcomes
7. **Tool results return** → Gateway streams back to Harness
8. **Claude processes results** → Continues reasoning loop, may call more tools
9. **All agents complete** → Harness merges planner + wellness, applies overrides
10. **Briefs written** → Briefing agent generates cited narratives
11. **JSON returned** → Advisor receives ranked cards + briefs

### Configuration

| Component | Setting |
|---|---|
| **S3 Bucket** | Region: ca-central-1; env var `SIGNALS_BUCKET` |
| **Lambda** | Timeout: 30s; Runtime: Python 3.13; IAM: S3 read/write/list |
| **Gateway** | Tool schema: gateway_tools.json; 5 tools (get_signals, assess_savings, check_qualification, get_outcomes, record_outcome) |
| **Harness** | Model: us.anthropic.claude-sonnet-4-6; Max iterations: 20; Memory: enabled |
| **Execution Role** | Bedrock invoke (inference profile ARNs), Gateway invoke, S3 access (GetObject, PutObject, ListBucket) |

### Deployment Steps

1. **S3 (10 min):** Create bucket in ca-central-1; upload clients/ and skills/ folders
2. **Lambda (10 min):** Create function (Python 3.13), paste handler.py, set SIGNALS_BUCKET env var, configure IAM role
3. **Gateway (10 min):** Create Gateway, add Lambda target, upload gateway_tools.json schema
4. **Harness (10 min):** Create Harness (Advanced), point to Gateway, load skills from S3 sources, enable Memory
5. **Test (5 min):** Run "harness for advisor_id A-7" in Playground

---

## Agent 1: Planner Agent

### What It Does
- **Role**: Orchestrator & evidence gatherer
- **Execution**: Runs in parallel (Thread A)
- **Duration**: Blocks entire harness until complete

### Input Data

The planner receives:

```python
{
    "client_id": "C-1001",
    "prior_outcomes": [
        {
            "client_id": "C-1001",
            "card_id": "C-1001-home_purchase",
            "action": "not_now",
            "note": "Gap too large, revisit in Q2",
            "ts": "2024-09-01T10:30:00Z"
        },
        # ... more prior actions
    ]
}
```

**What the planner focuses on:**
1. **Client ID** - to fetch signals
2. **Prior outcomes** - to decide whether to re-surface or suppress cards
   - If advisor said "not_now", suppress unless a signal materially changed
   - If advisor said "already_handled", suppress
   - If advisor said "wrong_timing", re-evaluate
3. **Opportunity detection** - does this client show signals for:
   - home_purchase?
   - renewal_refi?
   - liquidity?
   - attrition?

### Tools Called

The planner has access to three tools:

#### 1. `get_signals(client_id)` → Returns Signal Bundle

```json
{
  "client_name": "Priya S.",
  "risk_profile": "balanced",
  "tenure_years": 6,
  "signals": {
    "cashflow_mean_surplus": 4150,
    "cashflow_stdev": 175,
    "cashflow_negative_months": 0,
    "fhsa_monthly_velocity": 1350,
    "fhsa_room_remaining": 15500,
    "hbp_eligible": 60000,
    "down_payment_available": 127500,
    "calculator_uses_90d": 3,
    "preapproval_started": true,
    "heloc_inquiries_90d": 0,
    "outbound_total_6m": 0,
    "outbound_months": 0,
    "last_contact_days_ago": 41,
    "has_mortgage": false,
    "renewal_in_months": null,
    "mortgage_balance": null,
    "current_rate": null,
    "rate_gap_vs_market": null,
    "penalty_estimate": null
  }
}
```

**What planner does with signals:**
- Detects home_purchase intent: `preapproval_started=true`, `calculator_uses_90d=3` → strong signal
- Checks cash flow: `cashflow_mean_surplus=4150` → stable
- Notes tenure: `tenure_years=6` → established client

#### 2. `assess_savings(client_id, target_price=900000)` → Down Payment Analysis

```json
{
  "target_price": 900000,
  "down_payment_needed": 90000,
  "down_payment_available": 127500,
  "gap": 0,
  "months_to_target": 0,
  "sufficient": true
}
```

**What planner uses this for:**
- `sufficient=true` → Client has enough down payment NOW
- `gap=0` → No gap to cover
- `months_to_target=0` → Timeline: "Ready now"
- Feeds into evidence: "Down payment available: $127.5k" [E2]

#### 3. `check_qualification(client_id, target_price=900000)` → Mortgage Qualification Gate

```json
{
  "principal": 810000,
  "stress_test_payment": 4891,
  "gds": 0.385,
  "tds": 0.467,
  "gds_limit": 0.39,
  "tds_limit": 0.44,
  "qualifies": false,
  "rule_based": true
}
```

**CRITICAL**: This is **rule-based, deterministic**. Planner CANNOT override.

**What planner uses this for:**
- `qualifies=false` → GDS (38.5%) is BELOW limit (39%) but TDS (46.7%) is ABOVE limit (44%)
- Planner CANNOT emit home_purchase card with confidence > 0.7 if `qualifies=false`
- Example output: "Qualification status: Needs debt reduction. TDS at 46.7% exceeds regulatory limit of 44%." [E3]

### Output: Cards Array

```json
{
  "cards": [
    {
      "card_id": "C-1001-home_purchase",
      "opportunity": "home_purchase",
      "confidence": 0.85,
      "timeline": "Ready now",
      "urgency_rank": 2,
      "key_signal": "Pre-approval started + stable cash flow",
      "recommended_action": "Discuss mortgage options. Client is ready on savings and has shown clear intent.",
      "product_fit": ["BMO mortgage pre-approval", "FHSA top-up"],
      "evidence": [
        {
          "claim": "Pre-approval process already started",
          "tool": "get_signals",
          "key": "preapproval_started",
          "value": true
        },
        {
          "claim": "Down payment sufficient at $127.5k",
          "tool": "assess_savings",
          "key": "down_payment_available",
          "value": 127500
        },
        {
          "claim": "Stable monthly surplus averaging $4.15k",
          "tool": "get_signals",
          "key": "cashflow_mean_surplus",
          "value": 4150
        },
        {
          "claim": "Mortgage calculator used 3 times in 90 days",
          "tool": "get_signals",
          "key": "calculator_uses_90d",
          "value": 3
        }
      ]
    }
  ],
  "rationale": "Priya shows three strong home purchase signals: pre-approval started, sufficient down payment, and active shopping (calculator views). Confidence is high due to evidence and stability."
}
```

**What planner focuses on:**
1. **Evidence gathering** - every card MUST have ≥3 evidence items
2. **Confidence scoring** - 0.0 to 1.0 based on signal strength
3. **Timeline** - months to readiness or "ready now"
4. **Urgency ranking** - 1 (most urgent), 2, 3, etc.
5. **Qualification gate** - NEVER emit home_purchase with conf > 0.7 if `qualifies=false`
6. **Prior outcomes** - suppress "not_now" unless signal changed materially

---

## Agent 2: Wellness Agent

### What It Does
- **Role**: Independent risk gatekeeper
- **Execution**: Runs in parallel (Thread B)
- **Duration**: Blocks entire harness until complete
- **Can Override**: YES - veto or downgrade any card from planner

### Input Data

The wellness agent receives **ONLY the signal bundle** (no client_id, no prior outcomes, no cards):

```json
{
  "client_name": "Priya S.",
  "risk_profile": "balanced",
  "tenure_years": 6,
  "signals": {
    "cashflow_mean_surplus": 4150,
    "cashflow_stdev": 175,
    "cashflow_negative_months": 0,
    "fhsa_monthly_velocity": 1350,
    "fhsa_room_remaining": 15500,
    "hbp_eligible": 60000,
    "down_payment_available": 127500,
    "calculator_uses_90d": 3,
    "preapproval_started": true,
    "heloc_inquiries_90d": 0,
    "outbound_total_6m": 0,
    "outbound_months": 0,
    "last_contact_days_ago": 41,
    "has_mortgage": false,
    "monthly_debt_payments": 650,
    "credit_utilization": 0.18,
    "missed_payments_12m": 0,
    "income_stability": "SALARIED"
  }
}
```

**Key point**: Wellness does NOT know what cards planner found. It evaluates the client holistically.

### What Wellness Focuses On

**Veto triggers:**
1. **Negative cash-flow months**: `cashflow_negative_months > 0` → Client had months where surplus < 0
2. **High cash-flow variance**: `cashflow_stdev` too high relative to mean
3. **Credit stress**: `credit_utilization > 0.5` OR `missed_payments_12m > 0`
4. **Debt load**: `monthly_debt_payments > ~35% of net_income`

**Downgrade triggers:**
- Moderate risk on one or more factors above

**Proceed triggers:**
- Stable cash flow, low credit stress, manageable debt

### Output: Wellness Verdict

```json
{
  "risk_level": "low",
  "verdict": "proceed",
  "reasons": [
    {
      "claim": "Stable cash flow with no negative months",
      "evidence_key": "cashflow_negative_months",
      "value": 0
    },
    {
      "claim": "Low credit utilization at 18%",
      "evidence_key": "credit_utilization",
      "value": 0.18
    },
    {
      "claim": "Manageable debt at 5.8% of net income",
      "evidence_key": "monthly_debt_payments",
      "value": 650
    }
  ],
  "advisor_note": "No material financial risk factors. Client is in good standing."
}
```

### Example: Wellness Veto

For Marcus (C-1002):

```json
{
  "risk_level": "high",
  "verdict": "veto",
  "reasons": [
    {
      "claim": "Negative cash-flow months (-$1.1k, -$600)",
      "evidence_key": "cashflow_negative_months",
      "value": 2
    },
    {
      "claim": "High cash-flow variance (std dev $1300)",
      "evidence_key": "cashflow_stdev",
      "value": 1300
    },
    {
      "claim": "High debt load at 51% of net income",
      "evidence_key": "monthly_debt_payments",
      "value": 2100
    }
  ],
  "advisor_note": "Significant cash-flow instability and high debt load. Recommend addressing financial stability before any new product recommendations."
}
```

**What happens next:**
- Planner may have emitted: `renewal_refi` with confidence 0.95
- Wellness applies veto: confidence capped at 0.35
- Card is still shown to advisor but with disclaimer: "wellness_override: veto"

---

## Agent 3: Briefing Agent

### What It Does
- **Role**: Narrative writer + evidence validator
- **Execution**: Runs SEQUENTIALLY after planner & wellness complete
- **Runs once per card** (not in parallel)
- **Has grounding validator**: Ensures every fact has a citation

### Input Data

Briefing receives the **merged card + wellness verdict + evidence list**:

```json
{
  "card_id": "C-1001-home_purchase",
  "opportunity": "home_purchase",
  "confidence": 0.85,
  "timeline": "Ready now",
  "urgency_rank": 2,
  "key_signal": "Pre-approval started + stable cash flow",
  "recommended_action": "Discuss mortgage options. Client is ready on savings and has shown clear intent.",
  "product_fit": ["BMO mortgage pre-approval", "FHSA top-up"],
  "evidence": [
    {
      "claim": "Pre-approval process already started",
      "tool": "get_signals",
      "key": "preapproval_started",
      "value": true
    },
    {
      "claim": "Down payment sufficient at $127.5k",
      "tool": "assess_savings",
      "key": "down_payment_available",
      "value": 127500
    },
    {
      "claim": "Stable monthly surplus averaging $4.15k",
      "tool": "get_signals",
      "key": "cashflow_mean_surplus",
      "value": 4150
    },
    {
      "claim": "Mortgage calculator used 3 times in 90 days",
      "tool": "get_signals",
      "key": "calculator_uses_90d",
      "value": 3
    }
  ],
  "wellness": {
    "verdict": "proceed",
    "advisor_note": "No material financial risk factors. Client is in good standing."
  }
}
```

### What Briefing Focuses On

1. **Every factual sentence MUST have a citation [E#]**
   - [E1], [E2], [E3], [E4], etc. matching the evidence list
2. **4–6 sentences total**:
   - Line 1: One-line summary of opportunity + confidence
   - Lines 2–4: Supporting sentences, each cited
   - Line 5: Timing ("why now" or "why not yet")
   - Line 6: Suggested opening line for advisor
   - If wellness note: One sentence reflecting it
3. **Grounding check**: Deterministic validator ensures all citations are valid
   - If grounding fails, retry up to 2x
4. **No invented facts**: Every number and claim must trace to evidence

### Output: Cited Brief + Grounding Check

```json
{
  "brief": "Priya is clearing a significant milestone: pre-approval started and down payment fully ready [E2, E4]. Her steady surplus of $4.15k monthly [E3] paired with active calculator engagement (3 uses in 90 days) [E5] signals strong intent. Timing is immediate—she has the capital and the approvals in motion. Consider opening with: \"Your pre-approval is a great step. Let's talk through mortgage options that fit your timeline.\" No suitability concerns identified.",
  "grounding": {
    "passed": true,
    "uncited": [],
    "bad_refs": []
  },
  "evidence": [
    {
      "claim": "Pre-approval process already started",
      "key": "preapproval_started",
      "value": true
    },
    {
      "claim": "Down payment sufficient at $127.5k",
      "key": "down_payment_available",
      "value": 127500
    },
    {
      "claim": "Stable monthly surplus averaging $4.15k",
      "key": "cashflow_mean_surplus",
      "value": 4150
    },
    {
      "claim": "Mortgage calculator used 3 times in 90 days",
      "key": "calculator_uses_90d",
      "value": 3
    }
  ]
}
```

**Grounding validator checks:**
- ✓ "Priya is clearing..." → starts with fact, has [E2, E4]
- ✓ "Her steady surplus of $4.15k..." → cited [E3]
- ✓ "3 uses in 90 days" → cited [E5]
- ✓ "Timing is immediate" → logical statement, no citation needed
- ✓ "Consider opening with..." → suggestion, marked as such
- ✓ Every [E#] reference is 1 ≤ E# ≤ 4

---

## Deterministic Tool Layer

All tools are **Python, no model calls**. They return evidence that feeds into agent decisions.

### Tool 1: `get_signals(client_id)`

**Input:**
```python
client_id: "C-1001"
```

**Output:**
```json
{
  "client_name": "Priya S.",
  "risk_profile": "balanced",
  "tenure_years": 6,
  "signals": {
    "cashflow_mean_surplus": 4150,
    "cashflow_stdev": 175,
    "cashflow_negative_months": 0,
    "fhsa_monthly_velocity": 1350,
    "fhsa_room_remaining": 15500,
    "hbp_eligible": 60000,
    "down_payment_available": 127500,
    "calculator_uses_90d": 3,
    "preapproval_started": true,
    "heloc_inquiries_90d": 0,
    "outbound_total_6m": 0,
    "outbound_months": 0,
    "last_contact_days_ago": 41,
    "has_mortgage": false
  }
}
```

**Role:** Foundation for all analysis. Derived from raw client data (monthly surplus, FHSA balance, RRSP, mortgage, telemetry, etc.).

---

### Tool 2: `assess_savings(client_id, target_price=900000)`

**Input:**
```python
client_id: "C-1001"
target_price: 900000  # default
```

**Output:**
```json
{
  "target_price": 900000,
  "down_payment_needed": 90000,
  "down_payment_available": 127500,
  "gap": 0,
  "months_to_target": 0,
  "sufficient": true
}
```

**Role:** Down payment readiness. Calculates:
- `gap = needed - available` (max 0)
- `months_to_target = gap / (fhsa_velocity + savings_rate)`
- `sufficient = (gap == 0)`

**Used by:** Planner for home_purchase cards. Feeds into evidence and timeline.

---

### Tool 3: `check_qualification(client_id, target_price=900000)`

**Input:**
```python
client_id: "C-1001"
target_price: 900000
```

**Output:**
```json
{
  "principal": 810000,
  "stress_test_payment": 4891,
  "gds": 0.385,
  "tds": 0.467,
  "gds_limit": 0.39,
  "tds_limit": 0.44,
  "qualifies": false,
  "rule_based": true
}
```

**Role:** **RULE-BASED, DETERMINISTIC QUALIFICATION GATE**

Applies Canadian mortgage stress-test rules:
- Stress-test rate: `max(5.25%, contract_rate + 2.0%)`
- GDS (housing / gross income) ≤ 39%
- TDS (housing + debt / gross income) ≤ 44%

**Critical constraint:** Planner CANNOT emit home_purchase card with confidence > 0.7 if `qualifies = false`.

**Used by:** Planner's home_purchase decision. If `qualifies=false`, confidence capped at 0.7 max.

---

### Tool 4: `get_outcomes(client_id)`

**Input:**
```python
client_id: "C-1001"
```

**Output:**
```json
[
  {
    "client_id": "C-1001",
    "card_id": "C-1001-home_purchase",
    "action": "not_now",
    "note": "Gap was $85k, revisit in Q2",
    "ts": "2024-09-01T10:30:00Z"
  },
  {
    "client_id": "C-1001",
    "card_id": "C-1001-liquidity",
    "action": "already_handled",
    "note": "Discussed HELOC options",
    "ts": "2024-08-15T14:00:00Z"
  }
]
```

**Role:** Prior advisor actions. Planner uses this to decide:
- If "not_now" and gap hasn't materially changed → suppress
- If "already_handled" → suppress
- If "wrong_timing" → re-evaluate timing

---

### Tool 5: `record_outcome(client_id, card_id, action, note="")`

**Input:**
```python
client_id: "C-1001"
card_id: "C-1001-home_purchase"
action: "contacted"  # or "not_now", "wrong_timing", "already_handled", "converted"
note: "Discussed pre-approval timeline"
```

**Output:**
```json
{
  "recorded": true,
  "client_id": "C-1001",
  "card_id": "C-1001-home_purchase",
  "action": "contacted",
  "note": "Discussed pre-approval timeline",
  "ts": "2024-09-09T15:22:00Z"
}
```

**Role:** Advisor-gated feedback loop. Logs advisor actions for next harness run.

---

## Request Flow: 10 Steps

### Step 1: Receive Request
```
POST /invocations
{"client_id": "C-1001", "advisor_id": "A-7"}
```
→ `main.py` entrypoint receives request

### Step 2: Load & Prepare
```python
load_client("C-1001")      # → raw client data from S3 or local JSON
get_outcomes("C-1001")     # → prior advisor actions from Memory or /tmp
```

### Step 3: Spawn Parallel Agents
```python
ThreadPoolExecutor(max_workers=2) starts:
  Thread A: run_planner(client_id) with prior outcomes
  Thread B: run_wellness(get_signals(client_id))
```
Both run **simultaneously**

### Step 4: Planner Executes
```python
# Planner receives:
{
  "client_id": "C-1001",
  "prior_outcomes": [...]
}

# Planner calls:
get_signals("C-1001")                      # → signal bundle
assess_savings("C-1001", target_price)     # → savings gap
check_qualification("C-1001", target_price) # → qualifies (bool)

# Planner emits:
{
  "cards": [
    {
      "card_id": "C-1001-home_purchase",
      "confidence": 0.85,
      "timeline": "Ready now",
      "urgency_rank": 2,
      "evidence": [...],
      ...
    }
  ],
  "rationale": "Priya shows three strong signals..."
}
```

### Step 5: Wellness Executes
```python
# Wellness receives:
get_signals("C-1001")

# Wellness analyzes:
- cashflow_negative_months: 0 ✓
- cashflow_stdev: 175 (stable) ✓
- credit_utilization: 0.18 (low) ✓
- monthly_debt_payments: 650 (manageable) ✓

# Wellness emits:
{
  "verdict": "proceed",
  "risk_level": "low",
  "reasons": [...],
  "advisor_note": "No material financial risk factors."
}
```

### Step 6: Wait for Both to Complete
```python
planner_f.result()    # blocks here until planner finishes
wellness_f.result()   # blocks here until wellness finishes
```

### Step 7: Apply Wellness Override
```python
for card in planner_cards:
  if wellness.verdict == "veto":
    card["confidence"] = min(card["confidence"], 0.35)
    card["recommended_action"] = "Hold outreach ... check in on stability first."
  elif wellness.verdict == "downgrade":
    card["confidence"] = card["confidence"] * 0.7
  
  card["wellness_override"] = wellness.verdict
  card["wellness_note"] = wellness["advisor_note"]
```

### Step 8: Sort Cards
```python
cards.sort(key=lambda c: (c["urgency_rank"], -c["confidence"]))
# Drop cards with confidence < 0.5 unless marked "why not yet"
```

### Step 9: Generate Briefs (if requested)
```python
for card in cards:
  brief_result = run_briefing(card, wellness)
  # Briefing agent writes 4-6 sentence narrative
  # Grounding check ensures every fact has [E#] citation
  # Retry up to 2x if grounding fails
  card["brief"] = brief_result
```

### Step 10: Return JSON
```json
{
  "client_id": "C-1001",
  "advisor_id": "A-7",
  "cards": [
    {
      "card_id": "C-1001-home_purchase",
      "opportunity": "home_purchase",
      "confidence": 0.85,
      "timeline": "Ready now",
      "urgency_rank": 2,
      "key_signal": "Pre-approval started + stable cash flow",
      "recommended_action": "Discuss mortgage options...",
      "wellness_override": "none",
      "wellness_note": "No material financial risk factors.",
      "evidence": [...],
      "brief": {
        "brief": "Priya is clearing a significant milestone...",
        "grounding": {"passed": true},
        "evidence": [...]
      }
    }
  ],
  "wellness": {
    "verdict": "proceed",
    "risk_level": "low",
    "reasons": [...],
    "advisor_note": "..."
  },
  "planner_rationale": "Priya shows three strong signals..."
}
```

---

## The Qualification Gate (Most Critical)

**Rule-based, non-negotiable:**

The `check_qualification` tool applies Canadian mortgage stress-test rules. It calculates:
- **GDS** (housing payment / gross income)
- **TDS** (housing + debt / gross income)
- At stress-test rate: `max(5.25%, contract_rate + 2.0%)`

**The constraint:**

Planner **CANNOT** emit a home_purchase card with confidence > 0.7 if `qualifies = false`.

**Why:**

Mortgage qualification is not a judgment call. It is a legal and prudential gate set by CMHC/regulators. The model can say "ready on savings" or "not yet on savings," but it cannot override the math.

**Example:**

Client: Priya (C-1001)
- GDS: 38.5% (limit: 39%) ✓
- TDS: 46.7% (limit: 44%) ✗
- Result: `qualifies = false`

Planner's card: "Qualification status: Needs debt reduction. TDS at 46.7% exceeds regulatory limit of 44%." Confidence capped at max 0.7.

---

## The Wellness Veto (Consumer Protection)

Wellness independently assesses financial risk. It vetoes when:

1. **Negative cash-flow months**: Any month with surplus < 0
2. **High cash-flow variance**: Std dev too high relative to mean
3. **Credit stress**: Credit utilization > 50% OR missed payments in last 12 months
4. **Debt load**: Monthly debt payments > ~35% of net income

**Example: Marcus (C-1002)**

Signals:
- `cashflow_negative_months`: 2 (months with -$1.1k, -$600)
- `cashflow_stdev`: 1300
- `monthly_debt_payments`: 2100 (51% of net income)
- `renewal_in_months`: 3

Planner would emit: `renewal_refi` with confidence 0.95 (urgent, rate gap, renewal soon)

Wellness evaluates: "HIGH RISK" → veto

Result: Card still shown to advisor, but:
- Confidence capped at 0.35
- Recommended action: "Hold outreach. Check in on cash-flow stability first."
- Wellness override: "veto"

---

## Opportunities (What the Planner Detects)

| Opportunity | Trigger Signals | Tools Required | Key Output |
|---|---|---|---|
| **home_purchase** | housing_intent, preapproval_started, calculator_viewed, fhsa_velocity > 0 | assess_savings, check_qualification | months_to_target, qualifies (must be true for conf > 0.7) |
| **renewal_refi** | renewal_in_months ≤ 6 (urgent if ≤ 3), rate_gap_vs_market > 0 | get_signals | renewal window, payment shock estimate |
| **liquidity** | heloc_inquiries_90d > 0, outbound_transfers pattern, income_stable | get_signals | cash need indicator, borrowing capacity |
| **attrition** | last_contact_days_ago > 90, low tenure_years, disengagement signals | get_signals | relationship risk score, retention urgency |

---

## Demo Clients

### C-1001: Priya S.

**Profile:** 34, $168k/year, 6-year tenure, balanced risk

**Key Signals:**
- Stable surplus: $4.2k/month (no negative months)
- FHSA: $24.5k, contributing $1.35k/month
- Pre-approval: Started
- Calculator: Used 3 times in 90 days
- Debt: $650/month (manageable)

**Expected Card:**
- **home_purchase** (high confidence 0.85, ready now)

**Wellness Verdict:** Proceed (no risk factors)

---

### C-1002: Marcus T.

**Profile:** 46, $245k/year, 11-year tenure, growth risk

**Key Signals:**
- Volatile surplus: -$1.1k to +$1.2k (2 negative months)
- FHSA: $0 (not contributing)
- Mortgage: Renewing in 3 months at 2.19%
- Rate gap: 2.41% (payment shock coming)
- Debt: $2.1k/month (51% of income) ⚠️
- Heloc inquiries: 1 (equity access intent)

**Expected Cards:**
- **renewal_refi** (urgent, urgency_rank=1, confidence 0.9)
  - BUT wellness veto applied: confidence capped at 0.35
- **liquidity** (lower confidence due to debt load)

**Wellness Verdict:** Veto (negative cash-flow months, high debt, cash-flow volatility)

---

### C-1003: Dana W.

**Profile:** 39, $190k/year, 4-year tenure, balanced risk

**Key Signals:**
- Stable surplus: $3k/month
- FHSA: $16k, contributing $1k/month
- Mortgage: None (renting $3.4k/month)
- Calculator: Used 4 times in 90 days
- Liquid savings: $60k

**Expected Card:**
- **home_purchase** ("why not yet", confidence 0.65, timeline "6–9 months")
  - Down payment gap: $38.5k
  - Months to target: 8 months at current savings rate
  - Savings sufficient but timeline means "not ready yet"

**Wellness Verdict:** Proceed (stable, low risk)

---

## Key Design Patterns

### 1. Evidence-Driven Briefs
Every narrative fact must trace back to a tool output. Briefs cite evidence items by index [E1], [E2], etc.

Example:
```
Brief: "Priya is clearing a significant milestone: pre-approval started and down payment fully ready [E2, E4]."
Evidence:
  E2: {"claim": "Down payment sufficient at $127.5k", "value": 127500}
  E4: {"claim": "Mortgage calculator used 3 times in 90 days", "value": 3}
```

### 2. Rule-Based Qualification Gate
`check_qualification` is deterministic. Planner cannot override. Protects both client and advisor.

### 3. Independent Wellness Veto
Runs in parallel, receives only signals (not cards). Can reject any opportunity. Consumer protection.

### 4. Prior Outcomes Shape Decisions
If advisor marked "not_now", planner suppresses unless signal materially changed. Prevents noise.

### 5. Parallel Execution
Planner & wellness run simultaneously via ThreadPoolExecutor. Reduces latency.

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `MODEL_ID` | us.anthropic.claude-sonnet-4-20250514 | Primary model for planner & briefing agents |
| `FAST_MODEL_ID` | Same as MODEL_ID | Optional cheaper model for wellness agent |
| `SIGNALS_BUCKET` | (none — use local) | S3 bucket with clients/ and outcomes/ prefixes |
| `MEMORY_ID` | (none — use /tmp) | AgentCore Memory ID for persistent outcomes |

---

## Summary

A request arrives with a client_id. The system:

1. **Loads** raw client data and prior outcomes
2. **Spawns** two Claude agents in parallel:
   - **Planner** analyzes signals + calls tools (assess_savings, check_qualification) → detects opportunities → emits cards with evidence
   - **Wellness** assesses financial risk independently → returns verdict (proceed, downgrade, veto)
3. **Merges** results: wellness overrides applied (veto caps confidence ≤ 0.35, downgrade × 0.7)
4. **Sorts** cards by urgency_rank and confidence
5. **Briefs** each card: briefing agent writes 4–6 sentence narrative with [E#] citations validated by deterministic grounding checker
6. **Returns** JSON cards ready for advisor review

Advisor records actions (contacted, not_now, already_handled), which feed back into the next run to suppress or re-surface opportunities based on signal change.

**Everything is:**
- **Rule-based** (qualification gate)
- **Evidence-backed** (briefs)
- **Consumer-protective** (wellness veto)
