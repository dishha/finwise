# FinWise Frontend-Backend-Harness Integration Plan

## Overview

This document describes how to connect a frontend application and backend service with the deployed AWS AgentCore Harness. The harness is deployed on AWS (Bedrock, Lambda, Gateway, S3), so the backend acts as an orchestrator between the frontend and the harness infrastructure.

**Current State:**
- ✅ AgentCore Harness deployed on AWS (claude-sonnet-4-6)
- ✅ Lambda handler for tool execution
- ✅ Gateway for tool routing
- ✅ S3 for data persistence (clients, skills, outcomes)
- ⏳ Backend API layer needed
- ⏳ Frontend UI needed

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      FRONTEND (Browser)                         │
│  • React, Vue, Angular, or vanilla JS                          │
│  • Displays advisor dashboard                                  │
│  • Shows readiness cards, briefs, wellness verdicts            │
│  • Handles advisor interactions (review, accept, reject)       │
└───────────────────────┬─────────────────────────────────────────┘
                        │ HTTP/REST or WebSocket
                        │ (advisor reviews cards, marks outcomes)
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND API SERVICE                          │
│  (Node.js, Python Flask, Go, Java, etc.)                       │
│                                                                 │
│  • /api/harness/run                → calls harness              │
│  • /api/outcomes/record             → logs advisor decisions    │
│  • /api/clients/list                → fetches book              │
│  • /api/auth/login                  → handles auth             │
│  • /api/trace/details               → gets harness trace       │
│  • WebSocket server (optional)      → real-time updates        │
└───────────────────────┬─────────────────────────────────────────┘
                        │ Bedrock API
                        │ (invoke harness via ARN + runtime session ID)
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│              AWS AGENTCORE HARNESS (Deployed)                   │
│                                                                 │
│  • Model: Claude Sonnet 4.6                                    │
│  • Instructions: harness_instructions.md                       │
│  • Tools: Gateway invokes Lambda                               │
│  • Skills: Progressive load from S3                            │
│  • Memory: Persistent outcomes tracking                        │
└───────────────────────┬─────────────────────────────────────────┘
                        │ AWS Services
                        ├─ Lambda (handler.py)
                        ├─ Gateway (tool router)
                        ├─ S3 (data + skills)
                        └─ Bedrock (model inference)
```

---

## Integration Points

### 1. **Frontend ↔ Backend Communication**

**Endpoint: POST /api/harness/run**

Request:
```json
{
  "advisor_id": "A-7",
  "client_id": "C-1001",         // optional: run for single client
  "with_briefs": true,
  "session_id": "uuid-here"      // optional: correlate requests
}
```

Response:
```json
{
  "success": true,
  "status": "completed" | "in_progress" | "error",
  "client_id": "C-1001",
  "advisor_id": "A-7",
  "cards": [
    {
      "card_id": "C-1001-home_purchase",
      "opportunity": "home_purchase",
      "confidence": 0.85,
      "timeline": "Ready now",
      "urgency_rank": 2,
      "wellness_override": "none" | "veto" | "downgrade",
      "wellness_note": "...",
      "brief": { "brief": "...", "grounding": {...}, "evidence": [...] },
      "evidence": [...]
    }
  ],
  "wellness": { "verdict": "proceed", "risk_level": "low", "reasons": [...] },
  "planner_rationale": "...",
  "trace_id": "harness-trace-uuid",  // for observability
  "timestamp": "2026-09-09T15:22:00Z"
}
```

**Endpoint: POST /api/outcomes/record**

Request:
```json
{
  "advisor_id": "A-7",
  "client_id": "C-1001",
  "card_id": "C-1001-home_purchase",
  "action": "contacted" | "not_now" | "wrong_timing" | "already_handled" | "converted",
  "note": "Discussed pre-approval timeline",
  "timestamp": "2026-09-09T15:30:00Z"
}
```

Response:
```json
{
  "success": true,
  "recorded": true,
  "outcome_id": "outcome-uuid",
  "message": "Outcome recorded. Will influence next harness run."
}
```

**Endpoint: GET /api/clients/list**

Request Query:
```
GET /api/clients/list?advisor_id=A-7
```

Response:
```json
{
  "clients": [
    {
      "client_id": "C-1001",
      "client_name": "Priya S.",
      "tenure_years": 6,
      "last_contact_days_ago": 41
    }
  ]
}
```

**Endpoint: GET /api/trace/details**

Request Query:
```
GET /api/trace/details?trace_id=harness-trace-uuid
```

Response:
```json
{
  "trace_id": "harness-trace-uuid",
  "advisor_id": "A-7",
  "client_id": "C-1001",
  "status": "completed",
  "duration_ms": 3421,
  "steps": [
    {
      "step": 1,
      "action": "Load client data",
      "status": "completed",
      "duration_ms": 123
    },
    {
      "step": 2,
      "action": "Spawn planner agent",
      "status": "completed",
      "duration_ms": 2100
    },
    {
      "step": 3,
      "action": "Planner calls get_signals",
      "status": "completed",
      "tool": "get_signals",
      "duration_ms": 450
    }
  ],
  "errors": []
}
```

---

## Data Flow Patterns

### Pattern 1: Single Client Review (Advisor Drills Down)

```
Frontend                Backend                 Harness
   │                      │                        │
   │ POST /harness/run    │                        │
   ├─ advisor_id: A-7    │                        │
   ├─ client_id: C-1001  │                        │
   │────────────────────→ │                        │
   │                      │ invoke_harness()      │
   │                      │ (with runtime session)│
   │                      ├───────────────────────→
   │                      │                        │ Planner executes
   │                      │                        │ • Calls get_signals
   │                      │                        │ • Calls assess_savings
   │                      │                        │ Wellness executes
   │                      │                        │ • Returns verdict
   │                      │                        │ Briefing writes briefs
   │                      │                        │
   │                      │←───────────────────────┤
   │                      │ JSON cards + trace    │
   │                      │ (via boto3 stream)    │
   │                      │                        │
   │ 200 OK               │                        │
   │ { cards: [...] }    │                        │
   │←────────────────────│                        │
   │                      │                        │
   │ Display cards        │                        │
   │ (advisor reviews)    │                        │
   │                      │                        │
   │ POST /outcomes/record│                        │
   ├─ action: "contacted"│                        │
   │────────────────────→ │                        │
   │                      │ Lambda: record_outcome│
   │                      ├───────────────────────→
   │                      │                        │ Writes to S3
   │                      │                        │ (outcomes log)
   │                      │←───────────────────────┤
   │ 200 OK               │                        │
   │←────────────────────│                        │
```

### Pattern 2: Full Book Review (Advisor Runs All Clients)

```
Frontend                Backend                 Harness
   │                      │                        │
   │ POST /harness/run    │                        │
   ├─ advisor_id: A-7    │                        │
   │ (no client_id)       │                        │
   │────────────────────→ │                        │
   │                      │ invoke_harness()      │
   │                      │ (instructions say:    │
   │                      │  list all clients,    │
   │                      │  process each)        │
   │                      ├───────────────────────→
   │                      │                        │
   │ Polling or          │                        │ For each client:
   │ WebSocket stream    │                        │ • Load signals
   │ (real-time updates) │                        │ • Run planner
   │←────────────────────│                        │ • Run wellness
   │ (partial results    │                        │ • Write briefs
   │  as ready)          │                        │ • Record in trace
   │                      │←─ stream updates ─────┤
   │                      │ (or poll for status)  │
   │                      │                        │
   │ Final response       │                        │
   │ (all cards for       │                        │
   │  all clients)        │                        │
   │←────────────────────│                        │
```

### Pattern 3: Real-Time Observability (Advisor Watches Harness)

```
Frontend                Backend                 Harness
   │                      │                        │
   │ WebSocket: /ws/trace│                        │
   ├──────────────────────→ (opens connection)    │
   │                      │                        │
   │ POST /harness/run    │                        │
   ├─ advisor_id: A-7    │                        │
   ├─ trace_enabled: true│                        │
   │────────────────────→ │                        │
   │                      │ invoke_harness()      │
   │                      │ stream=True           │
   │                      ├───────────────────────→
   │◄─ WebSocket: skill  │                        │
   │   "loading renewal" │                        │ Loading skill:
   │                      │                        │ renewal_refi
   │◄─ WebSocket:        │                        │
   │   "tool call"        │                        │ Claude calls
   │   "get_signals"      │                        │ get_signals
   │                      │                        │
   │◄─ WebSocket:        │                        │
   │   "tool result"      │                        │ Tool returned
   │   "30 signals"       │                        │
   │                      │                        │
   │◄─ WebSocket:        │                        │
   │   "card emitted"     │                        │ Planner found
   │   "renewal_refi"     │                        │ renewal opportunity
   │                      │                        │
   │ ... more events ...  │                        │
   │                      │                        │
   │◄─ WebSocket:        │                        │
   │   "completed"        │                        │
   │   {...full cards...} │                        │
```

---

## Backend Implementation Patterns

### Pattern A: Synchronous Request-Response

**When to use:** Single client review, advisor waits for results

```
Backend flow:
  1. Receive POST /harness/run
  2. Validate advisor_id, client_id
  3. Call boto3: bedrock_agentcore.invoke_harness(
       harnessArn=HARNESS_ARN,
       runtimeSessionId=uuid.uuid4(),
       messages=[{"role": "user", "content": [...]}]
     )
  4. Stream response, collect chunks
  5. Parse JSON from response
  6. Return to frontend immediately
  7. Frontend displays cards
  8. Optional: Poll /api/trace/details for observability
```

**Pros:** Simple, stateless, familiar request-response pattern
**Cons:** Long waits for full book (multiple clients × 3+ seconds each)

### Pattern B: Asynchronous with Polling

**When to use:** Full book review, advisor doesn't need to wait

```
Backend flow:
  1. Receive POST /harness/run
  2. Start async task (celery, APScheduler, or cloud task)
  3. Return { status: "queued", job_id: "..." }
  4. Background task calls invoke_harness()
  5. Streams results into database (track per-client progress)
  
Frontend flow:
  1. POST /harness/run → get job_id
  2. Poll GET /api/job/{job_id}/status
  3. Display partial results as they complete
  4. When done, fetch final results
```

**Pros:** No timeout issues, advisor sees partial progress
**Cons:** More infrastructure (task queue, database)

### Pattern C: WebSocket Real-Time Updates

**When to use:** Advisor wants to watch harness execution

```
Backend flow:
  1. Receive WebSocket connect: /ws/trace/{advisor_id}/{session_id}
  2. Store connection in active_sessions
  3. Receive HTTP POST /harness/run
  4. Call invoke_harness() with stream=True
  5. For each event in stream:
     - Parse event (skill loading, tool call, tool result, etc.)
     - Broadcast to WebSocket connections
  6. When complete, send final JSON
  7. WebSocket connection closes (or stays for next run)

Advisor sees:
  • "Loading skill: renewal_refi"
  • "Tool call: get_signals"
  • "Tool result: 30 signals"
  • "Card emitted: renewal_refi (0.95 confidence)"
  • ... etc ...
  • "Complete: 3 cards emitted"
```

**Pros:** Full visibility, advisor knows what's happening
**Cons:** More complex backend, WebSocket infrastructure needed

---

## API Contract: Harness Invocation

### Step 1: Backend Calls AWS Bedrock AgentCore

```python
import boto3
import json
import uuid

client = boto3.client("bedrock-agentcore", region_name="ca-central-1")

def invoke_harness(advisor_id, client_id=None):
    """Call the deployed harness."""
    
    # Construct message
    if client_id:
        message = f"Run harness for advisor_id {advisor_id}, client_id {client_id} only, with a full brief."
    else:
        message = f"Run harness for advisor_id {advisor_id}. Return cards for every client in the book."
    
    # Invoke harness
    response = client.invoke_harness(
        harnessArn="arn:aws:agentcore:ca-central-1:ACCOUNT:harness/HARNESS-ID",
        runtimeSessionId=f"session-{uuid.uuid4()}",  # unique per invocation
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "text": message
                    }
                ]
            }
        ],
        enableTrace=True  # get detailed trace for observability
    )
    
    return response
```

### Step 2: Parse Streaming Response

```python
def collect_harness_response(response):
    """Extract JSON from harness streaming response."""
    
    chunks = []
    trace_events = []
    
    # Response is a stream of events
    for event in response.get("stream", response.get("response", [])):
        if isinstance(event, dict):
            # Check for message content
            if "message" in event:
                for content_block in event["message"].get("content", []):
                    if "text" in content_block:
                        chunks.append(content_block["text"])
            
            # Check for trace events (if enableTrace=True)
            if "trace" in event:
                trace_events.append(event["trace"])
    
    # Combine all text chunks
    response_text = "".join(chunks)
    
    # Extract JSON from response
    # Harness may wrap JSON in prose, so extract just the object
    import re
    match = re.search(r"\{.*\}", response_text, re.DOTALL)
    
    if match:
        harness_json = json.loads(match.group(0))
    else:
        harness_json = {"raw": response_text}
    
    return {
        "cards": harness_json.get("cards", []),
        "wellness": harness_json.get("wellness", {}),
        "planner_rationale": harness_json.get("planner_rationale", ""),
        "trace_events": trace_events
    }
```

### Step 3: Backend Returns to Frontend

```python
@app.post("/api/harness/run")
def run_harness(request):
    """Endpoint: frontend calls backend, backend calls harness."""
    
    advisor_id = request.json.get("advisor_id")
    client_id = request.json.get("client_id")  # optional
    with_briefs = request.json.get("with_briefs", True)
    
    # Validate
    if not advisor_id:
        return {"error": "advisor_id required"}, 400
    
    # Call harness
    try:
        harness_response = invoke_harness(advisor_id, client_id)
        harness_data = collect_harness_response(harness_response)
    except Exception as e:
        return {"error": str(e)}, 500
    
    # Enrich with metadata
    return {
        "success": True,
        "status": "completed",
        "advisor_id": advisor_id,
        "client_id": client_id,
        "cards": harness_data["cards"],
        "wellness": harness_data["wellness"],
        "planner_rationale": harness_data["planner_rationale"],
        "trace_id": "trace-uuid-here",  # if enableTrace=True
        "timestamp": datetime.utcnow().isoformat()
    }
```

---

## Authentication & Authorization

### Backend ↔ Harness

**Handled by:**
- IAM role attached to backend service (EC2, Lambda, ECS, etc.)
- Role has permission: `bedrock:InvokeAgent`
- Optional: session tokens, temporary credentials via STS

### Frontend ↔ Backend

**Options:**

1. **JWT (Stateless)**
   - Frontend: POST /login with advisor credentials
   - Backend: Generate JWT (exp: 1 hour)
   - Frontend: Include JWT in all requests (Authorization header)
   - Backend: Verify JWT signature before calling harness

2. **Session Cookies (Stateful)**
   - Frontend: POST /login
   - Backend: Create session, set httpOnly cookie
   - Frontend: Browser sends cookie automatically
   - Backend: Look up session in cache/database

3. **API Key (Simple)**
   - Each advisor gets a long-lived API key
   - Frontend: Include key in request header
   - Backend: Look up key, check permissions

**Recommended for FinWise:** JWT or Session + MFA for production

---

## Step-by-Step Implementation

### Phase 1: Synchronous Backend (2–3 days)

**Goal:** Basic backend that calls harness and returns results

**Tasks:**

1. **Create backend project**
   ```
   Backend structure:
   ├── main.py / app.js / etc.
   ├── routes/
   │   ├── harness.py (POST /harness/run)
   │   ├── outcomes.py (POST /outcomes/record)
   │   ├── clients.py (GET /clients/list)
   │   └── auth.py (POST /login)
   ├── services/
   │   ├── harness_client.py (AWS integration)
   │   ├── outcomes_service.py (S3 writes)
   │   └── auth_service.py (JWT/sessions)
   └── config.py (HARNESS_ARN, AWS_REGION, etc.)
   ```

2. **Set up AWS SDK**
   - Install boto3 (if Python) or AWS SDK for your language
   - Configure credentials (IAM role or env vars)
   - Test invoke_harness() in local environment

3. **Implement POST /api/harness/run**
   - Accept advisor_id, client_id (optional), with_briefs
   - Call invoke_harness()
   - Parse response (extract JSON)
   - Return cards + metadata

4. **Implement POST /api/outcomes/record**
   - Accept advisor_id, client_id, card_id, action, note
   - Call Lambda tool: record_outcome()
   - Return success/error

5. **Test end-to-end**
   - Call backend from curl/Postman
   - Verify harness returns cards
   - Verify outcomes are logged

**Deliverable:** Backend API running, accessible from frontend

---

### Phase 2: Frontend Dashboard (3–4 days)

**Goal:** Advisor sees cards, can review and mark outcomes

**Tasks:**

1. **Create frontend project**
   ```
   Frontend structure:
   ├── src/
   │   ├── pages/
   │   │   ├── Dashboard.tsx (main view)
   │   │   ├── ClientDetail.tsx (single client)
   │   │   ├── Login.tsx (auth)
   │   │   └── TraceDetail.tsx (observability)
   │   ├── components/
   │   │   ├── CardView.tsx (display a card)
   │   │   ├── WellnessVerdictBadge.tsx (veto/downgrade/proceed)
   │   │   └── BriefPanel.tsx (cited narrative)
   │   ├── services/
   │   │   └── api.ts (call backend)
   │   └── hooks/
   │       └── useHarness.ts (fetch + cache results)
   └── public/
   ```

2. **Implement Dashboard page**
   - Button: "Run Harness for My Book"
   - Display loading state
   - When ready: list all cards (all clients)
   - For each card:
     - Opportunity name + confidence
     - Urgency rank
     - Wellness override badge (if veto/downgrade)
     - Brief summary
     - Action buttons: "Contacted", "Not Now", "Already Handled", etc.

3. **Implement Card detail view**
   - Click card → see full brief
   - See evidence items [E1], [E2], etc.
   - See grounding status (passed/failed)
   - See wellness reason (if veto/downgrade)
   - Button: "Record outcome"

4. **Implement outcome recording**
   - When advisor clicks "Contacted", show dialog
   - Dialog: action + optional note
   - POST /outcomes/record
   - Show confirmation

5. **Test end-to-end**
   - Login (mock auth for MVP)
   - Run harness
   - See cards appear
   - Click card, see details
   - Mark as "Contacted"
   - Backend logs outcome

**Deliverable:** Frontend running, advisor can review and mark cards

---

### Phase 3: Async + Observability (2–3 days)

**Goal:** Full book runs don't timeout; advisor sees progress

**Tasks:**

1. **Add async task queue** (optional, for full book)
   - Background task runner (Celery, APScheduler, AWS Step Functions)
   - When /harness/run called with no client_id, start async task
   - Task calls invoke_harness()
   - Store progress in database or cache

2. **Add observability**
   - Capture trace from invoke_harness() response
   - Store trace in database
   - Endpoint: GET /api/trace/{trace_id}
   - Frontend polls to show progress

3. **Add progress polling**
   - Frontend: POST /harness/run → get job_id
   - Frontend: Poll GET /api/job/{job_id}/status
   - Display: "Processing 5 clients... Client 3 of 5 complete"
   - When done: fetch final results

4. **Optional: WebSocket for real-time updates**
   - Backend: Open WebSocket at /ws/trace/{session_id}
   - During harness invocation, broadcast trace events
   - Frontend listens and updates in real-time

**Deliverable:** Full book can run without timeout; advisor sees progress

---

### Phase 4: Authentication & Security (1–2 days)

**Goal:** Production-ready auth, data access control

**Tasks:**

1. **Implement JWT or session-based auth**
   - POST /auth/login (advisor email + password)
   - Verify credentials against your user database
   - Return JWT or set session cookie
   - Backend validates token on every request

2. **Add authorization checks**
   - Advisor can only see their own clients/cards
   - Manager/admin can see all advisors' books

3. **Audit logging**
   - Log who ran harness, when, for which clients
   - Log all outcome recordings
   - Store in database for compliance

4. **Rate limiting**
   - Prevent advisors from hammering harness API
   - Example: 1 run per 10 seconds per advisor

**Deliverable:** Production auth + audit trail

---

## Communication Protocols

### REST (Recommended for MVP)

```
POST /api/harness/run
Content-Type: application/json

{
  "advisor_id": "A-7",
  "client_id": "C-1001",
  "with_briefs": true
}

---

200 OK
Content-Type: application/json

{
  "success": true,
  "status": "completed",
  "cards": [...],
  "wellness": {...},
  "trace_id": "...",
  "timestamp": "..."
}
```

**Pros:**
- Stateless
- Simple to understand
- Works with any frontend framework
- Standard HTTP caching

**Cons:**
- No real-time updates (need polling for progress)
- Timeouts for long-running requests

### WebSocket (Optional, for real-time)

```javascript
// Frontend
const ws = new WebSocket("wss://backend.example.com/ws/trace/A-7/session-123");

ws.onopen = () => {
  // Backend opened connection
  fetch("/api/harness/run", { /* ... */ });
};

ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  // update = { type: "skill_loading", skill: "renewal_refi" }
  // update = { type: "tool_call", tool: "get_signals" }
  // update = { type: "card_emitted", opportunity: "renewal_refi", confidence: 0.95 }
  // etc.
};

ws.onclose = () => {
  // Harness completed
};
```

**Pros:**
- Real-time updates
- Advisor sees harness progress
- Low latency

**Cons:**
- Stateful (harder to scale)
- More complex backend
- Requires WebSocket infrastructure

---

## Environment Variables

**Backend needs:**

```bash
# AWS
AWS_REGION=ca-central-1
HARNESS_ARN=arn:aws:agentcore:ca-central-1:ACCOUNT:harness/HARNESS-ID

# Auth (if not using IAM role)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...

# Frontend
FRONTEND_URL=http://localhost:3000

# Database (if using async + polling)
DATABASE_URL=postgresql://user:pass@host/dbname

# Cache (if storing job progress)
REDIS_URL=redis://host:6379

# Logging
LOG_LEVEL=INFO
```

**Frontend needs:**

```bash
# Backend
REACT_APP_API_URL=http://localhost:5000/api
REACT_APP_WS_URL=ws://localhost:5000/ws
```

---

## Error Handling & Resilience

### Backend Error Cases

| Error | Cause | Recovery |
|---|---|---|
| Harness timeout | Full book takes >5 min | Use async task queue + polling |
| Lambda error (tool fail) | Tool code fails | Harness retries; check Lambda logs |
| S3 error (data fetch) | S3 unavailable | Harness falls back to local data; add retry logic |
| Bedrock throttle | Too many concurrent calls | Add backend queue, limit concurrent harness runs to 5 |
| Invalid JSON response | Harness output malformed | Parse with error handling; return raw response to advisor |

### Frontend Error Cases

| Error | Cause | Recovery |
|---|---|---|
| Network timeout | Harness didn't respond in 30s | Show spinner; offer "Cancel" or "Wait"; poll status |
| 500 backend error | Backend crashed | Show error; ask advisor to refresh |
| Card display fails | Missing fields in response | Add defensive checks; show minimal fallback |
| WebSocket disconnect | Network blip | Auto-reconnect with exponential backoff |

---

## Database Schema (If Needed)

### Outcomes Table

```sql
CREATE TABLE outcomes (
  outcome_id UUID PRIMARY KEY,
  advisor_id VARCHAR(50) NOT NULL,
  client_id VARCHAR(50) NOT NULL,
  card_id VARCHAR(100) NOT NULL,
  action VARCHAR(50) NOT NULL,  -- "contacted", "not_now", etc.
  note TEXT,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  INDEX (advisor_id, client_id),
  INDEX (created_at)
);
```

### Harness Runs (If Using Async)

```sql
CREATE TABLE harness_runs (
  job_id UUID PRIMARY KEY,
  advisor_id VARCHAR(50) NOT NULL,
  client_id VARCHAR(50),  -- NULL = full book
  status VARCHAR(50),  -- "queued", "processing", "completed", "error"
  result JSON,  -- full harness response
  error_message TEXT,
  created_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP,
  trace_id VARCHAR(100),
  INDEX (advisor_id, created_at),
  INDEX (status)
);
```

---

## Deployment Architecture

### Option A: Backend + Frontend Separate (Recommended)

```
┌──────────────────────────────────────────────────┐
│ AWS                                              │
├──────────────────────────────────────────────────┤
│                                                  │
│  ┌──────────────┐   ┌─────────────┐             │
│  │ Frontend     │   │ Backend     │             │
│  │ (S3 + CF)    │ ↔ │ (ECS/Lambda)│             │
│  └──────────────┘   └──────┬──────┘             │
│                            │                    │
│                    ┌────────┼────────┐           │
│                    │        │        │           │
│              ┌─────▼─┐  ┌───▼────┐  │           │
│              │Harness│  │Database│  │           │
│              └───────┘  └────────┘  │           │
│                                     │           │
│                        (RDS, DynamoDB)         │
└──────────────────────────────────────────────────┘
```

**Frontend:** S3 bucket + CloudFront (static assets)
**Backend:** ECS (Fargate), Lambda, or EC2
**Database:** RDS (PostgreSQL) or DynamoDB

### Option B: Monolithic (Simpler)

```
┌────────────────┐
│ Backend + UI   │
│ (Node/Python   │
│  monolith)     │
└────────┬───────┘
         │
    ┌────▼─────┐
    │ Harness   │
    └───────────┘
```

**Single service handles both API and frontend**
Simpler to deploy, harder to scale independently.

---

## Security Checklist

- [ ] JWT or session tokens for auth
- [ ] HTTPS/TLS for all communication (backend ↔ frontend, backend ↔ harness)
- [ ] IAM role for backend (not hardcoded AWS keys)
- [ ] Rate limiting on /harness/run endpoint
- [ ] Audit logging of all harness invocations
- [ ] CORS enabled only for frontend domain
- [ ] Input validation on advisor_id, client_id, etc.
- [ ] SQL injection protection (use parameterized queries)
- [ ] OWASP top 10 review
- [ ] Regular backups of outcomes database

---

## Testing Strategy

### Unit Tests

- Backend: Test API routes, harness client, outcomes service
- Frontend: Test components, API calls, card rendering

### Integration Tests

- Backend calls mock harness → verify JSON parsing
- Backend records outcome → verify S3/database write
- Frontend → backend → harness flow (end-to-end with test data)

### Load Tests

- Simulate 10 advisors running harness simultaneously
- Measure latency, trace performance bottlenecks
- Target: <5 seconds per single-client run, <30 seconds per full book

### Security Tests

- Attempt to access another advisor's data → denied
- Send malformed JSON → error handling works
- SQL injection attempts → parameterized queries protect

---

## Summary: Integration Checklist

### Backend Implementation

- [ ] Create backend project (Node/Python/Go)
- [ ] Install AWS SDK, configure credentials
- [ ] Implement `invoke_harness()` function (call AWS Bedrock)
- [ ] Implement `POST /api/harness/run` endpoint
- [ ] Implement `POST /api/outcomes/record` endpoint
- [ ] Implement `GET /api/clients/list` endpoint
- [ ] Add auth (JWT or sessions)
- [ ] Add error handling + logging
- [ ] Deploy to AWS (ECS/Lambda/EC2)

### Frontend Implementation

- [ ] Create frontend project (React/Vue/etc.)
- [ ] Implement Dashboard page
- [ ] Implement Card detail view
- [ ] Add API client service
- [ ] Add outcome recording flow
- [ ] Add loading states + error handling
- [ ] Deploy to S3 + CloudFront or backend server

### Integration Testing

- [ ] Backend can call harness → returns cards
- [ ] Frontend can POST /harness/run → sees cards
- [ ] Advisor can mark outcome → backend logs it
- [ ] Full end-to-end flow works

### Production Checklist

- [ ] Auth working (JWT/sessions)
- [ ] Rate limiting enabled
- [ ] Audit logging enabled
- [ ] Error handling + retry logic
- [ ] Monitoring + alerting set up
- [ ] Database backups configured
- [ ] Documentation complete
- [ ] Security review passed

---

## Next Steps

1. **Choose backend framework:** Flask/FastAPI (Python), Express (Node), Go, etc.
2. **Set up local development:** Backend + frontend running locally
3. **Test harness integration:** Verify AWS SDK can invoke harness
4. **Build Phase 1:** Synchronous API + basic frontend
5. **User feedback:** Get advisors to test early
6. **Build Phase 2:** Async + observability
7. **Go live:** Monitor, iterate

---

## Questions to Discuss

1. **Tech stack:** What languages/frameworks does your team prefer?
2. **Scale:** How many advisors? How many clients per advisor?
3. **Real-time:** Do advisors need to see harness progress in real-time, or is eventual consistency OK?
4. **Database:** Should outcomes be persisted locally, or only in S3?
5. **Auth:** Use existing enterprise auth (LDAP, Okta) or build new?
6. **Timeline:** When do you want Phase 1 ready? Phase 2?
