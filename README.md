# FinWise harness — AgentCore Runtime

Three Claude agents (planner, wellness, briefing) orchestrate financial readiness detection. All tools are deterministic (no model calls).

## Agentic Flow

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

**Key mechanisms:**
- **Planner** receives client_id + prior outcomes. Calls tools: `get_signals`, `assess_savings`, `check_qualification`.
- **Wellness** receives signal bundle independently. Can veto/downgrade based on cash-flow risk, credit stress, debt load.
- **Briefing** writes narratives grounded by deterministic citation validator.
- **Qualification gate** is rule-based (GDS/TDS stress-test). Planner cannot override.

## Files
- `main.py` — Runtime entrypoint (`@app.entrypoint`)
- `agents.py` — Three Claude agents (planner, wellness, briefing) + parallel harness orchestration
- `tools.py` — Deterministic tools: signal engine, savings & qualification calculators, outcomes memory
- `handler.py` — Lambda Gateway tool layer (alternative deployment)
- `backend.py` — Flask dashboard (optional UI layer)
- `data/sample_clients.json` — Three demo clients
- `skills/` — Opportunity definitions (home_purchase, renewal_refi, liquidity, attrition, wellness)
- `build.sh` — Builds arm64 ZIP for AgentCore deployment

## Environment variables (set on the agent in the console)
- `MODEL_ID` — Bedrock model id (default: Claude Sonnet cross-region)
- `FAST_MODEL_ID` — Optional cheaper model for wellness agent
- `SIGNALS_BUCKET` — S3 bucket with `clients/<id>.json`; omit to use local sample data
- `MEMORY_ID` — AgentCore Memory id for persistent outcomes; omit to use local /tmp

## Local test
```
uv sync
python main.py
curl -X POST localhost:8080/invocations -H 'Content-Type: application/json' \
  -d '{"client_id":"C-1001","advisor_id":"A-7"}'
```

## Demo clients
- **C-1001 Priya** — Clear home purchase readiness. Stable $4.2k/mo surplus, FHSA $24.5k, pre-approval started.
- **C-1002 Marcus** — Renewal urgent (3 months) but wellness veto (volatile surplus -$1.1k to +$1.2k, $2.1k debt).
- **C-1003 Dana** — Saving steadily but gap remains. 6–9 months to down payment target ("why not yet").

## Design Patterns
1. **Evidence-grounded briefs** — Every fact ends with [E#] citing tool outputs. Deterministic grounding validator.
2. **Rule-based qualification** — GDS/TDS stress-test gate. Planner cannot override. Protects client & advisor.
3. **Independent wellness veto** — Runs in parallel. Consumer protection: can reject opportunity even if planner sees it.
4. **Prior outcomes shape decisions** — If advisor said "not_now", planner only re-surfaces if signal materially changed.
5. **Parallel execution** — Planner & wellness run simultaneously via ThreadPoolExecutor. Reduces latency.
