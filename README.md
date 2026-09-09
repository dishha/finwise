# FinWise harness — AgentCore Runtime

Three model-backed agents (planner, wellness, briefing) plus deterministic tools.
Deploy through the AgentCore console (Host Agent → Local Upload).

## Files
- `main.py` — Runtime entrypoint (`@app.entrypoint`)
- `agents.py` — planner, wellness (veto), briefing (grounding validator), harness run
- `tools.py` — signal engine, savings and qualification calculators, memory read/write
- `data/sample_clients.json` — three demo clients (ready, veto case, "not yet")
- `build.sh` — builds the arm64 ZIP for direct code deployment

## Environment variables (set on the agent in the console)
- `MODEL_ID` — Bedrock model id (default: Claude Sonnet cross-region id)
- `FAST_MODEL_ID` — optional cheaper model for wellness
- `SIGNALS_BUCKET` — S3 bucket with `clients/<id>.json`; omit to use local sample data
- `MEMORY_ID` — AgentCore Memory id; omit to use local /tmp outcomes

## Local test
```
uv sync
python main.py
curl -X POST localhost:8080/invocations -H 'Content-Type: application/json' \
  -d '{"client_id":"C-1001","advisor_id":"A-7"}'
```

## Demo clients
- C-1001 Priya — clear home_purchase, stable cash flow, pre-approval started
- C-1002 Marcus — renewal in 3 months + attrition signals, negative cash-flow months (wellness veto/downgrade)
- C-1003 Dana — saving steadily, short of down payment ("why not yet")
